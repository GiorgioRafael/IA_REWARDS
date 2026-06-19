import copy
import threading
import uuid
from datetime import datetime
from tkinter import messagebox

import pyautogui as pa
from pynput import keyboard

from automacao_edge import (
    limpar_cache_execucao,
    obter_cache_painel_rewards,
    obter_coordenada_alvo_visual,
)
from dashboard_rewards import (
    DashboardRewardsClient,
    agora_iso_utc,
    normalizar_pontos_texto,
    validar_leitura_pontos,
)
from deteccao_imagem import obter_bbox_virtual


class DashboardMixin:
    def ponto_dentro_da_tela_atual(self, x, y, margem=0):
        try:
            virtual_x, virtual_y, virtual_width, virtual_height = obter_bbox_virtual()
        except Exception:
            return True

        return (
            virtual_x - margem
            <= int(x)
            <= virtual_x + virtual_width + margem
            and virtual_y - margem
            <= int(y)
            <= virtual_y + virtual_height + margem
        )

    def dashboard_ativo(self):
        return bool(self.config.get("dashboard", {}).get("ativada", False))

    def log_id_atual(self):
        if self.exec_logger.log_path is None:
            return None
        return self.exec_logger.log_path.name

    def obter_anchor_pontos_rewards(
        self,
        abrir_edge_primeiro=False,
        reabrir_se_nao_encontrar=True,
    ):
        if not abrir_edge_primeiro:
            limpar_cache_execucao(self.config)
            x, y, _cache = obter_coordenada_alvo_visual(
                self.config,
                "exibir_painel",
                status_callback=self.status_com_log,
                stop_event=self.stop_automation,
            )
            if x is not None and y is not None:
                return int(x), int(y)

            if not reabrir_se_nao_encontrar:
                self.status_com_log(
                    "Painel Rewards atual nao localizado para leitura direta dos pontos.",
                    "orange",
                )
                return None

        return self.abrir_painel_rewards_sessao(tentativas=2)

    def montar_candidatos_leitura_pontos(
        self,
        anchor_x,
        anchor_y,
        leitura,
    ):
        candidatos = []
        usados = set()

        def adicionar(nome, x, y):
            try:
                x = int(x)
                y = int(y)
            except (TypeError, ValueError):
                return

            chave = (x, y)
            if chave in usados:
                return
            usados.add(chave)
            candidatos.append({"origem": nome, "x": x, "y": y})

        double_click_x = leitura.get("double_click_x")
        double_click_y = leitura.get("double_click_y")
        if double_click_x is not None and double_click_y is not None:
            try:
                x_capturado = int(double_click_x)
                y_capturado = int(double_click_y)
                if self.ponto_dentro_da_tela_atual(x_capturado, y_capturado):
                    adicionar("posicao_capturada", x_capturado, y_capturado)
                else:
                    self.log_execucao(
                        "Dashboard: posicao capturada dos pontos fica fora da tela atual "
                        f"(x={x_capturado}, y={y_capturado}). Vou tentar candidatos dinamicos."
                    )
            except (TypeError, ValueError):
                self.log_execucao(
                    "Dashboard: posicao capturada dos pontos esta invalida. Vou tentar candidatos dinamicos."
                )

        painel = obter_cache_painel_rewards(self.config)
        if painel is None and hasattr(self, "detectar_estado_rewards"):
            try:
                estado = self.detectar_estado_rewards()
                painel = estado.get("painel") if isinstance(estado, dict) else None
            except Exception as exc:
                self.log_execucao(
                    f"Dashboard: nao consegui atualizar regiao do painel para leitura de pontos: {exc}"
                )

        if painel is not None:
            painel_x = int(painel["x"])
            painel_y = int(painel["y"])
            painel_w = int(painel["width"])
            # O numero de pontos fica no cabecalho fixo do popup, perto do canto esquerdo.
            adicionar(
                "painel_detectado",
                painel_x + max(70, min(115, painel_w // 4)),
                painel_y + 82,
            )
            adicionar(
                "painel_detectado_ajuste",
                painel_x + max(70, min(115, painel_w // 4)),
                painel_y + 94,
            )

        offset_x = int(leitura.get("click_offset_x", -245))
        offset_y = int(leitura.get("click_offset_y", -38))
        adicionar("offset_exibir_painel", int(anchor_x) + offset_x, int(anchor_y) + offset_y)

        return candidatos

    def copiar_pontos_rewards_clipboard(
        self,
        abrir_edge_primeiro=False,
        fechar_painel=True,
        reabrir_se_nao_encontrar=True,
    ):
        try:
            import pyperclip
        except Exception as exc:
            return {
                "ok": False,
                "erro": f"pyperclip_indisponivel: {exc}",
            }

        dashboard = self.config.get("dashboard", {})
        leitura = dashboard.get("leitura_pontos", {})
        tentativas = max(1, int(leitura.get("tentativas", 3)))
        restaurar_clipboard = bool(leitura.get("restaurar_clipboard", True))

        anchor = self.obter_anchor_pontos_rewards(
            abrir_edge_primeiro=abrir_edge_primeiro,
            reabrir_se_nao_encontrar=reabrir_se_nao_encontrar,
        )
        if anchor is None:
            return {
                "ok": False,
                "erro": "anchor_exibir_painel_nao_encontrado",
            }

        anchor_x, anchor_y = anchor
        candidatos = self.montar_candidatos_leitura_pontos(anchor_x, anchor_y, leitura)
        if not candidatos:
            return {
                "ok": False,
                "erro": "sem_candidato_leitura_pontos",
                "anchor": {"x": anchor_x, "y": anchor_y},
            }

        texto_anterior = None
        try:
            texto_anterior = pyperclip.paste()
        except Exception:
            texto_anterior = None

        sentinel = f"__AI_REWARDS_CLIPBOARD_{uuid.uuid4().hex}__"

        try:
            ultimo_texto = None
            ultimo_click = None
            ultima_origem = None
            for candidato in candidatos:
                x = candidato["x"]
                y = candidato["y"]
                origem_posicao = candidato["origem"]
                for tentativa in range(1, tentativas + 1):
                    if not self.esperar_se_pausado():
                        return {"ok": False, "erro": "interrompido"}

                    self.log_execucao(
                        f"Lendo pontos Rewards via clipboard tentativa {tentativa}/{tentativas}: "
                        f"x={x}, y={y}, origem={origem_posicao}."
                    )
                    pyperclip.copy(sentinel)
                    pa.moveTo(x, y, duration=0.12)
                    pa.click(x=x, y=y, clicks=2, interval=0.08)
                    if not self.sleep_interruptivel(0.15):
                        return {"ok": False, "erro": "interrompido"}
                    pa.hotkey("ctrl", "c")
                    if not self.sleep_interruptivel(0.2):
                        return {"ok": False, "erro": "interrompido"}

                    texto = pyperclip.paste()
                    ultimo_texto = texto
                    ultimo_click = {"x": x, "y": y}
                    ultima_origem = origem_posicao
                    pontos = normalizar_pontos_texto(texto)
                    valido, motivo_validacao = validar_leitura_pontos(
                        texto,
                        pontos,
                        leitura,
                        self.ultimo_pontos_lidos,
                    )
                    if valido and texto != sentinel:
                        return {
                            "ok": True,
                            "pontos": pontos,
                            "texto": texto,
                            "metodo": "double_click_clipboard",
                            "origem_posicao": origem_posicao,
                            "anchor": {"x": anchor_x, "y": anchor_y},
                            "click": {"x": x, "y": y},
                            "candidatos": candidatos,
                        }

                    if texto != sentinel:
                        self.log_execucao(
                            "Dashboard: leitura_rejeitada "
                            f"({motivo_validacao}); texto={texto!r}; pontos={pontos}; "
                            f"origem={origem_posicao}."
                        )

            return {
                "ok": False,
                "erro": "clipboard_sem_numero_valido_ou_rejeitado",
                "texto": ultimo_texto if ultimo_texto is not None else pyperclip.paste(),
                "origem_posicao": ultima_origem,
                "anchor": {"x": anchor_x, "y": anchor_y},
                "click": ultimo_click,
                "candidatos": candidatos,
            }
        finally:
            if restaurar_clipboard and texto_anterior is not None:
                try:
                    pyperclip.copy(texto_anterior)
                except Exception:
                    pass
            if fechar_painel:
                self.pressionar_esc_interno()

    def start_captura_posicao_pontos_dashboard(self):
        if self.automation_running:
            messagebox.showwarning(
                "Automacao em execucao",
                "Pare ou aguarde a automacao terminar antes de capturar a posicao dos pontos.",
                parent=self.root,
            )
            return

        messagebox.showinfo(
            "Capturar posicao dos pontos",
            "Coloque o mouse exatamente sobre o numero grande de pontos do Rewards.\n\n"
            "Depois pressione F9 para salvar a posicao.\n"
            "Pressione ESC para cancelar.",
            parent=self.root,
        )
        self.update_status("Aguardando F9 para capturar posicao do double click dos pontos...")
        thread = threading.Thread(
            target=self._captura_posicao_pontos_dashboard_worker,
            daemon=True,
        )
        thread.start()

    def _captura_posicao_pontos_dashboard_worker(self):
        concluido = threading.Event()
        resultado = {"ok": False}

        def on_press(key):
            if key == keyboard.Key.f9:
                try:
                    pos = pa.position()
                    resultado.update({"ok": True, "x": int(pos.x), "y": int(pos.y)})
                except Exception as exc:
                    resultado.update({"ok": False, "erro": str(exc)})
                concluido.set()
                return False

            if key == keyboard.Key.esc:
                resultado.update({"ok": False, "cancelado": True})
                concluido.set()
                return False

            return None

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()
        concluido.wait()
        try:
            listener.stop()
        except Exception:
            pass

        self.root.after(
            0,
            lambda resultado=resultado: self._finalizar_captura_posicao_pontos_dashboard(resultado),
        )

    def _finalizar_captura_posicao_pontos_dashboard(self, resultado):
        if resultado.get("ok"):
            x = resultado["x"]
            y = resultado["y"]
            self.dashboard_pontos_double_click_x_var.set(str(x))
            self.dashboard_pontos_double_click_y_var.set(str(y))
            self.update_status(f"Posicao dos pontos capturada: x={x}, y={y}.", "green")
            messagebox.showinfo(
                "Posicao capturada",
                f"Posicao do double click salva na interface:\n\nX={x}\nY={y}\n\n"
                "Clique em Salvar configuracoes para persistir no config.json.",
                parent=self.root,
            )
            return

        if resultado.get("cancelado"):
            self.update_status("Captura de posicao cancelada.", "orange")
            return

        self.update_status("Erro ao capturar posicao dos pontos.", "red")
        messagebox.showerror(
            "Erro",
            f"Nao foi possivel capturar a posicao: {resultado.get('erro')}",
            parent=self.root,
        )

    def start_teste_offset_pontos_dashboard(self):
        if self.automation_running:
            messagebox.showwarning(
                "Automacao em execucao",
                "Pare ou aguarde a automacao terminar antes de testar o offset dos pontos.",
                parent=self.root,
            )
            return

        if not self.save_config():
            return

        self.stop_automation.clear()
        self.pause_automation.clear()
        self.status_com_log("Dashboard: testando double click/leitura dos pontos...")
        thread = threading.Thread(
            target=self._teste_offset_pontos_dashboard_worker,
            daemon=True,
        )
        thread.start()

    def _teste_offset_pontos_dashboard_worker(self):
        resultado = {}
        try:
            resultado = self.copiar_pontos_rewards_clipboard(
                abrir_edge_primeiro=True,
                fechar_painel=False,
            )
            if resultado.get("ok"):
                self.status_com_log(
                    f"Dashboard: teste leu {resultado.get('pontos')} ponto(s).",
                    "green",
                )
            else:
                self.status_com_log(
                    f"Dashboard: teste nao conseguiu ler pontos ({resultado.get('erro')}).",
                    "orange",
                )
        except Exception as exc:
            resultado = {"ok": False, "erro": str(exc)}
            self.status_com_log(f"Dashboard: erro no teste de leitura dos pontos: {exc}", "red")

        self.root.after(
            0,
            lambda resultado=resultado: self._finalizar_teste_offset_pontos_dashboard(resultado),
        )

    def _finalizar_teste_offset_pontos_dashboard(self, resultado):
        anchor = resultado.get("anchor") or {}
        click = resultado.get("click") or {}
        texto = resultado.get("texto")
        origem = resultado.get("origem_posicao")
        candidatos = resultado.get("candidatos") or []
        candidatos_texto = "\n".join(
            f"- {item.get('origem')}: x={item.get('x')}, y={item.get('y')}"
            for item in candidatos
        ) or "nenhum"

        if resultado.get("ok"):
            mensagem = (
                f"Pontos detectados: {resultado.get('pontos')}\n"
                f"Texto copiado: {texto!r}\n"
                f"Metodo: {resultado.get('metodo')}\n\n"
                f"Origem da posicao: {origem}\n"
                f"Ancora Exibir painel: x={anchor.get('x')}, y={anchor.get('y')}\n"
                f"Coordenada do double click: x={click.get('x')}, y={click.get('y')}\n\n"
                f"Candidatos testados:\n{candidatos_texto}\n\n"
                "Se o valor estiver errado, capture novamente a posicao com F9 e teste outra vez."
            )
        else:
            mensagem = (
                f"Nao consegui ler os pontos.\n\n"
                f"Erro: {resultado.get('erro')}\n"
                f"Texto copiado: {texto!r}\n\n"
                f"Origem da posicao: {origem}\n"
                f"Ancora Exibir painel: x={anchor.get('x')}, y={anchor.get('y')}\n"
                f"Coordenada do double click: x={click.get('x')}, y={click.get('y')}\n\n"
                f"Candidatos testados:\n{candidatos_texto}\n\n"
                "O painel ficara aberto para voce conferir visualmente onde o double click aconteceu."
            )

        messagebox.showinfo("Teste leitura pontos", mensagem, parent=self.root)

    def registrar_pontos_dashboard(
        self,
        stage,
        phase,
        status="ok",
        notes=None,
        abrir_edge_primeiro=False,
        fechar_painel=True,
        reabrir_se_nao_encontrar=True,
        reutilizar_ultima_leitura=False,
    ):
        try:
            if not self.dashboard_ativo():
                return None

            if not self.run_id:
                self.iniciar_run_id()

            self.status_com_log(f"Dashboard: lendo pontos '{stage}/{phase}'.")
            if reutilizar_ultima_leitura and self.ultima_leitura_pontos is not None:
                leitura_origem = self.ultima_leitura_pontos
                leitura = copy.deepcopy(leitura_origem.get("leitura") or {})
                leitura.update(
                    {
                        "ok": True,
                        "pontos": int(leitura_origem["pontos"]),
                        "metodo": "reused_previous_read",
                        "reused_from": {
                            "stage": leitura_origem.get("stage"),
                            "phase": leitura_origem.get("phase"),
                            "status": leitura_origem.get("status"),
                        },
                    }
                )
                self.status_com_log(
                    "Dashboard: reutilizando ultima leitura valida de pontos "
                    f"({leitura['pontos']}) para '{stage}/{phase}'.",
                    "green",
                )
            elif abrir_edge_primeiro:
                leitura = self.copiar_pontos_rewards_clipboard(
                    abrir_edge_primeiro=True,
                    fechar_painel=fechar_painel,
                )
            else:
                self.status_com_log("Dashboard: tentando ler pontos no painel Rewards ja aberto.")
                leitura = self.copiar_pontos_rewards_clipboard(
                    abrir_edge_primeiro=False,
                    fechar_painel=fechar_painel,
                    reabrir_se_nao_encontrar=False,
                )
                if (
                    not leitura.get("ok")
                    and reabrir_se_nao_encontrar
                    and not self.stop_automation.is_set()
                ):
                    self.status_com_log(
                        "Dashboard: leitura direta falhou. Vou reabrir apenas o painel Rewards como fallback.",
                        "orange",
                    )
                    leitura = self.copiar_pontos_rewards_clipboard(
                        abrir_edge_primeiro=True,
                        fechar_painel=fechar_painel,
                    )
            if not leitura.get("ok"):
                self.status_com_log(
                    f"Dashboard: nao consegui ler pontos ({leitura.get('erro')}).",
                    "orange",
                )
                return leitura

            pontos = int(leitura["pontos"])
            delta_anterior = (
                pontos - self.ultimo_pontos_lidos
                if self.ultimo_pontos_lidos is not None
                else None
            )
            self.ultimo_pontos_lidos = pontos

            payload = {
                "schemaVersion": 1,
                "points": pontos,
                "createdAt": agora_iso_utc(),
                "localTime": datetime.now().isoformat(timespec="seconds"),
                "source": self.config.get("dashboard", {}).get("source", "python_app"),
                "stage": stage,
                "phase": phase,
                "status": status,
                "runId": self.run_id,
                "logId": self.log_id_atual(),
                "notes": notes,
                "rawText": leitura.get("texto"),
                "readMethod": leitura.get("metodo"),
                "readPositionSource": leitura.get("origem_posicao"),
                "deltaFromPreviousRead": delta_anterior,
                "readAnchor": leitura.get("anchor"),
                "readClick": leitura.get("click"),
                "reusedFrom": leitura.get("reused_from"),
            }

            cliente = DashboardRewardsClient(self.config.get("dashboard", {}))
            resultado_envio = cliente.enviar_evento(payload)
            if resultado_envio.get("ok"):
                self.status_com_log(
                    f"Dashboard: enviado {pontos} ponto(s) para '{stage}/{phase}'.",
                    "green",
                )
            else:
                self.status_com_log(
                    "Dashboard: leitura feita, mas envio falhou "
                    f"({resultado_envio.get('reason') or resultado_envio.get('status_code')}).",
                    "orange",
                )
                detalhe = resultado_envio.get("response")
                if detalhe:
                    self.log_execucao(f"Dashboard resposta: {detalhe}")

            self.ultima_leitura_pontos = {
                "pontos": pontos,
                "leitura": copy.deepcopy(leitura),
                "stage": stage,
                "phase": phase,
                "status": status,
            }
            return {
                "ok": bool(resultado_envio.get("ok")),
                "pontos": pontos,
                "leitura": leitura,
                "envio": resultado_envio,
            }
        except Exception as exc:
            self.status_com_log(f"Dashboard: erro nao critico ao registrar pontos: {exc}", "orange")
            return {"ok": False, "erro": str(exc)}

    def registrar_pontos_etapa(
        self,
        stage,
        phase,
        status="ok",
        notes=None,
        abrir_edge_primeiro=True,
        fechar_painel=True,
        reabrir_se_nao_encontrar=True,
        reutilizar_ultima_leitura=False,
    ):
        return self.registrar_pontos_dashboard(
            stage,
            phase,
            status=status,
            notes=notes,
            abrir_edge_primeiro=abrir_edge_primeiro,
            fechar_painel=fechar_painel,
            reabrir_se_nao_encontrar=reabrir_se_nao_encontrar,
            reutilizar_ultima_leitura=reutilizar_ultima_leitura,
        )

