import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

from pynput import keyboard

from app_config import BASE_DIR, LOGS_DIR, VISUAL_TARGET_LABELS
from automacao_edge import (
    abrir_ver_tudo_e_detectar_tracker_edge,
    detectar_estado_tracker_edge,
    listar_templates_alvo_visual,
    listar_templates_plus_10,
    listar_templates_plus_5,
    localizar_alvo_visual,
    obter_confianca_flexivel,
    obter_escalas_flexiveis,
    usar_variacoes_deteccao,
)
from deteccao_imagem import (
    capturar_tela,
    capturar_template_em_coordenada,
    get_mouse_position,
    get_mouse_position_debug,
    localizar_templates,
    mover_mouse,
)


class TrainingDetectionMixin:
    def obter_offset_captura_alvo_visual(self, nome):
        alvo_config = self.config.get("alvos_visuais", {}).get(nome, {})
        return (
            int(alvo_config.get("capture_offset_x", 0) or 0),
            int(alvo_config.get("capture_offset_y", 0) or 0),
        )

    def obter_offset_captura_tracker(self):
        tracker = self.config.get("edge_tracker", {})
        return (
            int(tracker.get("capture_offset_x", 0) or 0),
            int(tracker.get("capture_offset_y", 0) or 0),
        )

    def caminho_template_plus_10(self):
        caminho = Path(self.template_plus_10_var.get().strip() or "assets/plus_10.png")
        if caminho.is_absolute():
            return caminho

        return BASE_DIR / caminho

    def caminho_template_plus_5(self):
        caminho = Path(self.template_plus_5_var.get().strip() or "assets/plus_5.png")
        if caminho.is_absolute():
            return caminho

        return BASE_DIR / caminho

    def caminho_treino_plus_10(self):
        caminho = Path(self.treino_dir_var.get().strip() or "assets/treino_plus_10")
        if caminho.is_absolute():
            return caminho

        return BASE_DIR / caminho

    def caminho_treino_plus_5(self):
        caminho = Path(self.treino_dir_plus_5_var.get().strip() or "assets/treino_plus_5")
        if caminho.is_absolute():
            return caminho

        return BASE_DIR / caminho

    def caminho_treino_alvo_visual(self, nome):
        alvo = self.config.get("alvos_visuais", {}).get(nome, {})
        caminho = Path(alvo.get("treino_dir", f"assets/treino_{nome}"))
        if caminho.is_absolute():
            return caminho

        return BASE_DIR / caminho

    def caminho_treino_tracker_estado(self, minutos):
        tracker = self.config.get("edge_tracker", {})
        caminho = Path(tracker.get("treino_dir", "assets/treino_edge_tracker_estados"))
        caminho = caminho / str(int(minutos))
        if caminho.is_absolute():
            return caminho

        return BASE_DIR / caminho

    def nome_alvo_visual(self, nome):
        return VISUAL_TARGET_LABELS.get(nome, nome)

    def salvar_diagnostico_teste_deteccao(self, nome, templates, erro):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        agora = datetime.now().strftime("%Y%m%d_%H%M%S")
        caminho = LOGS_DIR / f"diagnostico_deteccao_{nome}_{agora}.txt"
        alvo_config = self.config.get("alvos_visuais", {}).get(nome, {})

        linhas = [
            f"Alvo: {nome}",
            f"BASE_DIR: {BASE_DIR}",
            f"Treino dir configurado: {alvo_config.get('treino_dir')}",
            f"Treino dir resolvido: {self.caminho_treino_alvo_visual(nome)}",
            f"Template principal: {alvo_config.get('template')}",
            f"Confianca: {alvo_config.get('confianca')}",
            f"Regiao configurada: {alvo_config.get('regiao')}",
            f"Erro: {type(erro).__name__}: {erro}",
            "",
            f"Templates carregados: {len(templates)}",
        ]

        for template in templates[:25]:
            template_path = Path(template)
            try:
                tamanho = template_path.stat().st_size
            except OSError:
                tamanho = "erro ao ler tamanho"
            linhas.append(f"- {template_path} | existe={template_path.exists()} | bytes={tamanho}")

        try:
            imagem, offset_x, offset_y = capturar_tela()
            linhas.extend(
                [
                    "",
                    "Captura de tela: OK",
                    f"Tamanho: {imagem.size[0]}x{imagem.size[1]}",
                    f"Offset: x={offset_x}, y={offset_y}",
                ]
            )
        except Exception as captura_erro:
            linhas.extend(
                [
                    "",
                    "Captura de tela: FALHOU",
                    f"Erro captura: {type(captura_erro).__name__}: {captura_erro}",
                ]
            )

        linhas.extend(["", "Traceback:", traceback.format_exc()])
        caminho.write_text("\n".join(linhas), encoding="utf-8")
        return caminho

    def mover_mouse_para_resultado(self, resultado):
        try:
            mover_mouse(resultado["x"], resultado["y"])
            return None
        except Exception as exc:
            return exc

    def capturar_template_plus_10(self):
        if not self.save_config():
            return

        messagebox.showinfo(
            "Capturar template +10",
            "A janela vai sumir.\n\n"
            "Coloque o mouse no centro do selo +10 e pressione F9.\n"
            "Pressione ESC para cancelar.",
        )
        self.root.withdraw()
        self.update_status("Aguardando F9 para capturar o template +10...")
        thread = threading.Thread(target=self._capturar_template_plus_10_worker, daemon=True)
        thread.start()

    def _capturar_template_plus_10_worker(self):
        resultado = {"cancelado": False, "erro": None, "destino": None, "x": None, "y": None}
        concluido = threading.Event()

        def on_press(key):
            if key == keyboard.Key.f9:
                try:
                    debug_mouse = get_mouse_position_debug()
                    mouse_x, mouse_y = get_mouse_position()
                    deteccao = self.config["deteccao_imagem"]
                    captura_x = mouse_x + int(deteccao["capture_offset_x"])
                    captura_y = mouse_y + int(deteccao["capture_offset_y"])
                    destino = capturar_template_em_coordenada(
                        self.caminho_template_plus_10(),
                        captura_x,
                        captura_y,
                    )
                    resultado.update(
                        {
                            "destino": destino,
                            "x": mouse_x,
                            "y": mouse_y,
                            "captura_x": captura_x,
                            "captura_y": captura_y,
                            "debug_mouse": debug_mouse,
                        }
                    )
                except Exception as exc:
                    resultado["erro"] = exc

                concluido.set()
                return False

            if key == keyboard.Key.esc:
                resultado["cancelado"] = True
                concluido.set()
                return False

            return True

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        concluido.wait()
        listener.stop()

        self.root.after(0, lambda: self._finalizar_captura_template_plus_10(resultado))

    def _finalizar_captura_template_plus_10(self, resultado):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        if resultado["cancelado"]:
            self.update_status("Captura do template cancelada.", "orange")
            return

        if resultado["erro"] is not None:
            self.update_status("Erro ao capturar template +10.", "red")
            messagebox.showerror(
                "Erro",
                f"Nao foi possivel capturar o template: {resultado['erro']}",
                parent=self.root,
            )
            return

        destino = resultado["destino"]
        debug_mouse = resultado.get("debug_mouse") or {}
        logico = debug_mouse.get("logico")
        fisico = debug_mouse.get("fisico")
        self.update_status(f"Template +10 salvo em {destino.name}.", "green")
        messagebox.showinfo(
            "Template capturado",
            f"Template +10 salvo em:\n{destino}\n\n"
            f"Mouse: x={resultado['x']}, y={resultado['y']}\n"
            f"Captura corrigida: x={resultado['captura_x']}, y={resultado['captura_y']}\n"
            f"Mouse logico: {logico}\n"
            f"Mouse fisico: {fisico}",
            parent=self.root,
        )

    def iniciar_modo_treino_plus_10(self):
        if not self.save_config():
            return

        messagebox.showinfo(
            "Modo treino +10",
            "A janela vai sumir.\n\n"
            "Coloque o mouse no centro de cada selo +10 e pressione F9.\n"
            "Cada F9 salva uma nova amostra.\n\n"
            "Pressione ESC para finalizar o treino.",
            parent=self.root,
        )
        self.root.withdraw()
        self.update_status("Modo treino ativo: F9 salva amostra, ESC finaliza.")
        thread = threading.Thread(target=self._modo_treino_plus_10_worker, daemon=True)
        thread.start()

    def _modo_treino_plus_10_worker(self):
        resultado = {"cancelado": False, "erro": None, "arquivos": []}
        concluido = threading.Event()

        def on_press(key):
            if key == keyboard.Key.f9:
                try:
                    mouse_x, mouse_y = get_mouse_position()
                    deteccao = self.config["deteccao_imagem"]
                    captura_x = mouse_x + int(deteccao["capture_offset_x"])
                    captura_y = mouse_y + int(deteccao["capture_offset_y"])
                    treino_dir = self.caminho_treino_plus_10()
                    treino_dir.mkdir(parents=True, exist_ok=True)
                    nome = datetime.now().strftime("plus_10_%Y%m%d_%H%M%S_%f.png")
                    destino = treino_dir / nome
                    capturar_template_em_coordenada(destino, captura_x, captura_y)
                    resultado["arquivos"].append(
                        {
                            "destino": destino,
                            "mouse_x": mouse_x,
                            "mouse_y": mouse_y,
                            "captura_x": captura_x,
                            "captura_y": captura_y,
                        }
                    )
                except Exception as exc:
                    resultado["erro"] = exc
                    concluido.set()
                    return False

                return True

            if key == keyboard.Key.esc:
                resultado["cancelado"] = True
                concluido.set()
                return False

            return True

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        concluido.wait()
        listener.stop()

        self.root.after(0, lambda: self._finalizar_modo_treino_plus_10(resultado))

    def _finalizar_modo_treino_plus_10(self, resultado):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        if resultado["erro"] is not None:
            self.update_status("Erro no modo treino +10.", "red")
            messagebox.showerror(
                "Erro",
                f"Nao foi possivel salvar a amostra: {resultado['erro']}",
                parent=self.root,
            )
            return

        total = len(resultado["arquivos"])
        if total == 0:
            self.update_status("Modo treino encerrado sem novas amostras.", "orange")
            return

        ultimo = resultado["arquivos"][-1]
        self.update_status(f"Modo treino finalizado: {total} amostra(s) salvas.", "green")
        messagebox.showinfo(
            "Modo treino finalizado",
            f"{total} amostra(s) salvas em:\n{self.caminho_treino_plus_10()}\n\n"
            f"Ultima captura corrigida: x={ultimo['captura_x']}, y={ultimo['captura_y']}",
            parent=self.root,
        )

    def capturar_template_plus_5(self):
        if not self.save_config():
            return

        messagebox.showinfo(
            "Capturar template +5",
            "A janela vai sumir.\n\n"
            "Coloque o mouse no centro do selo +5 e pressione F9.\n"
            "Pressione ESC para cancelar.",
        )
        self.root.withdraw()
        self.update_status("Aguardando F9 para capturar o template +5...")
        thread = threading.Thread(target=self._capturar_template_plus_5_worker, daemon=True)
        thread.start()

    def _capturar_template_plus_5_worker(self):
        resultado = {"cancelado": False, "erro": None, "destino": None, "x": None, "y": None}
        concluido = threading.Event()

        def on_press(key):
            if key == keyboard.Key.f9:
                try:
                    debug_mouse = get_mouse_position_debug()
                    mouse_x, mouse_y = get_mouse_position()
                    deteccao = self.config["deteccao_imagem"]
                    captura_x = mouse_x + int(deteccao["capture_offset_x"])
                    captura_y = mouse_y + int(deteccao["capture_offset_y"])
                    destino = capturar_template_em_coordenada(
                        self.caminho_template_plus_5(),
                        captura_x,
                        captura_y,
                    )
                    resultado.update(
                        {
                            "destino": destino,
                            "x": mouse_x,
                            "y": mouse_y,
                            "captura_x": captura_x,
                            "captura_y": captura_y,
                            "debug_mouse": debug_mouse,
                        }
                    )
                except Exception as exc:
                    resultado["erro"] = exc

                concluido.set()
                return False

            if key == keyboard.Key.esc:
                resultado["cancelado"] = True
                concluido.set()
                return False

            return True

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        concluido.wait()
        listener.stop()

        self.root.after(0, lambda: self._finalizar_captura_template_plus_5(resultado))

    def _finalizar_captura_template_plus_5(self, resultado):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        if resultado["cancelado"]:
            self.update_status("Captura do template +5 cancelada.", "orange")
            return

        if resultado["erro"] is not None:
            self.update_status("Erro ao capturar template +5.", "red")
            messagebox.showerror(
                "Erro",
                f"Nao foi possivel capturar o template +5: {resultado['erro']}",
                parent=self.root,
            )
            return

        destino = resultado["destino"]
        debug_mouse = resultado.get("debug_mouse") or {}
        self.update_status(f"Template +5 salvo em {destino.name}.", "green")
        messagebox.showinfo(
            "Template +5 capturado",
            f"Template +5 salvo em:\n{destino}\n\n"
            f"Mouse: x={resultado['x']}, y={resultado['y']}\n"
            f"Captura corrigida: x={resultado['captura_x']}, y={resultado['captura_y']}\n"
            f"Mouse logico: {debug_mouse.get('logico')}\n"
            f"Mouse fisico: {debug_mouse.get('fisico')}",
            parent=self.root,
        )

    def iniciar_modo_treino_plus_5(self):
        if not self.save_config():
            return

        messagebox.showinfo(
            "Modo treino +5",
            "A janela vai sumir.\n\n"
            "Coloque o mouse no centro de cada selo +5 e pressione F9.\n"
            "Cada F9 salva uma nova amostra.\n\n"
            "Pressione ESC para finalizar o treino.",
            parent=self.root,
        )
        self.root.withdraw()
        self.update_status("Modo treino +5 ativo: F9 salva amostra, ESC finaliza.")
        thread = threading.Thread(target=self._modo_treino_plus_5_worker, daemon=True)
        thread.start()

    def _modo_treino_plus_5_worker(self):
        resultado = {"cancelado": False, "erro": None, "arquivos": []}
        concluido = threading.Event()

        def on_press(key):
            if key == keyboard.Key.f9:
                try:
                    mouse_x, mouse_y = get_mouse_position()
                    deteccao = self.config["deteccao_imagem"]
                    captura_x = mouse_x + int(deteccao["capture_offset_x"])
                    captura_y = mouse_y + int(deteccao["capture_offset_y"])
                    treino_dir = self.caminho_treino_plus_5()
                    treino_dir.mkdir(parents=True, exist_ok=True)
                    nome = datetime.now().strftime("plus_5_%Y%m%d_%H%M%S_%f.png")
                    destino = treino_dir / nome
                    capturar_template_em_coordenada(destino, captura_x, captura_y)
                    resultado["arquivos"].append(
                        {
                            "destino": destino,
                            "mouse_x": mouse_x,
                            "mouse_y": mouse_y,
                            "captura_x": captura_x,
                            "captura_y": captura_y,
                        }
                    )
                except Exception as exc:
                    resultado["erro"] = exc
                    concluido.set()
                    return False

                return True

            if key == keyboard.Key.esc:
                resultado["cancelado"] = True
                concluido.set()
                return False

            return True

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        concluido.wait()
        listener.stop()

        self.root.after(0, lambda: self._finalizar_modo_treino_plus_5(resultado))

    def _finalizar_modo_treino_plus_5(self, resultado):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        if resultado["erro"] is not None:
            self.update_status("Erro no modo treino +5.", "red")
            messagebox.showerror(
                "Erro",
                f"Nao foi possivel salvar a amostra +5: {resultado['erro']}",
                parent=self.root,
            )
            return

        total = len(resultado["arquivos"])
        if total == 0:
            self.update_status("Modo treino +5 encerrado sem novas amostras.", "orange")
            return

        ultimo = resultado["arquivos"][-1]
        self.update_status(f"Modo treino +5 finalizado: {total} amostra(s) salvas.", "green")
        messagebox.showinfo(
            "Modo treino +5 finalizado",
            f"{total} amostra(s) salvas em:\n{self.caminho_treino_plus_5()}\n\n"
            f"Ultima captura corrigida: x={ultimo['captura_x']}, y={ultimo['captura_y']}",
            parent=self.root,
        )

    def iniciar_modo_treino_alvo_visual(self, nome):
        if not self.save_config():
            return

        label = self.nome_alvo_visual(nome)
        messagebox.showinfo(
            f"Treino - {label}",
            "A janela vai sumir.\n\n"
            f"Coloque o mouse no centro de '{label}' e pressione F9.\n"
            "Cada F9 salva uma nova amostra.\n\n"
            "Dica: no tracker, mire no texto estavel 'Navegar com Edge', nao no numero.\n\n"
            "Pressione ESC para finalizar o treino.",
            parent=self.root,
        )
        self.root.withdraw()
        self.update_status(f"Treino de {label} ativo: F9 salva amostra, ESC finaliza.")
        thread = threading.Thread(
            target=lambda: self._modo_treino_alvo_visual_worker(nome),
            daemon=True,
        )
        thread.start()

    def _modo_treino_alvo_visual_worker(self, nome):
        resultado = {"erro": None, "arquivos": [], "nome": nome}
        concluido = threading.Event()

        def on_press(key):
            if key == keyboard.Key.f9:
                try:
                    mouse_x, mouse_y = get_mouse_position()
                    alvo_config = self.config.get("alvos_visuais", {}).get(nome, {})
                    offset_x, offset_y = self.obter_offset_captura_alvo_visual(nome)
                    captura_x = mouse_x + offset_x
                    captura_y = mouse_y + offset_y
                    largura = int(alvo_config.get("capture_width", 70))
                    altura = int(alvo_config.get("capture_height", 50))
                    treino_dir = self.caminho_treino_alvo_visual(nome)
                    treino_dir.mkdir(parents=True, exist_ok=True)
                    arquivo_nome = datetime.now().strftime(f"{nome}_%Y%m%d_%H%M%S_%f.png")
                    destino = treino_dir / arquivo_nome
                    capturar_template_em_coordenada(
                        destino,
                        captura_x,
                        captura_y,
                        largura=largura,
                        altura=altura,
                    )
                    resultado["arquivos"].append(
                        {
                            "destino": destino,
                            "mouse_x": mouse_x,
                            "mouse_y": mouse_y,
                            "captura_x": captura_x,
                            "captura_y": captura_y,
                        }
                    )
                except Exception as exc:
                    resultado["erro"] = exc
                    concluido.set()
                    return False

                return True

            if key == keyboard.Key.esc:
                concluido.set()
                return False

            return True

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        concluido.wait()
        listener.stop()

        self.root.after(0, lambda: self._finalizar_modo_treino_alvo_visual(resultado))

    def _finalizar_modo_treino_alvo_visual(self, resultado):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        nome = resultado["nome"]
        label = self.nome_alvo_visual(nome)
        if resultado["erro"] is not None:
            self.update_status(f"Erro no treino de {label}.", "red")
            messagebox.showerror(
                "Erro",
                f"Nao foi possivel salvar a amostra de {label}: {resultado['erro']}",
                parent=self.root,
            )
            return

        total = len(resultado["arquivos"])
        if total == 0:
            self.update_status(f"Treino de {label} encerrado sem novas amostras.", "orange")
            return

        ultimo = resultado["arquivos"][-1]
        self.update_status(f"Treino de {label} finalizado: {total} amostra(s) salvas.", "green")
        messagebox.showinfo(
            f"Treino - {label}",
            f"{total} amostra(s) salvas em:\n{self.caminho_treino_alvo_visual(nome)}\n\n"
            f"Ultima captura corrigida: x={ultimo['captura_x']}, y={ultimo['captura_y']}",
            parent=self.root,
        )

    def testar_deteccao_alvo_visual(self, nome):
        if not self.save_config():
            return

        label = self.nome_alvo_visual(nome)
        self.update_status(f"Testando deteccao de {label}...")
        self.root.withdraw()
        thread = threading.Thread(
            target=lambda: self._testar_deteccao_alvo_visual_worker(nome),
            daemon=True,
        )
        thread.start()

    def _testar_deteccao_alvo_visual_worker(self, nome):
        time.sleep(0.7)
        templates = []
        resultado = {
            "nome": nome,
            "erro": None,
            "detectados": [],
            "total_templates": 0,
            "diagnostico": None,
        }

        try:
            templates = listar_templates_alvo_visual(self.config, nome)
            resultado["total_templates"] = len(templates)
            if not templates:
                raise FileNotFoundError(f"Nenhum template treinado para {nome}.")

            alvo = localizar_alvo_visual(
                self.config,
                nome,
                status_callback=self.status_com_log,
                stop_event=self.stop_automation,
            )
            resultado["detectados"] = [] if alvo is None else [alvo]
        except FileNotFoundError as exc:
            resultado["diagnostico"] = self.salvar_diagnostico_teste_deteccao(
                nome,
                templates,
                exc,
            )
            resultado["erro"] = (
                "Template nao encontrado",
                "Use Iniciar treino para salvar pelo menos uma amostra desse alvo.\n\n"
                f"Diagnostico salvo em:\n{resultado['diagnostico']}",
            )
        except Exception as exc:
            resultado["diagnostico"] = self.salvar_diagnostico_teste_deteccao(
                nome,
                templates,
                exc,
            )
            resultado["erro"] = (
                "Erro",
                f"Nao foi possivel testar a deteccao: {type(exc).__name__}: {exc}\n\n"
                f"Diagnostico salvo em:\n{resultado['diagnostico']}",
            )

        self.root.after(
            0,
            lambda: self._finalizar_teste_deteccao_alvo_visual(resultado),
        )

    def _finalizar_teste_deteccao_alvo_visual(self, resultado):
        detectados = resultado["detectados"]
        mover_erro = None
        if resultado["erro"] is None and detectados:
            mover_erro = self.mover_mouse_para_resultado(detectados[0])

        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        nome = resultado["nome"]
        label = self.nome_alvo_visual(nome)
        if resultado["erro"] is not None:
            titulo, mensagem = resultado["erro"]
            self.update_status(mensagem, "red")
            messagebox.showerror(titulo, mensagem, parent=self.root)
            return

        if detectados:
            melhor = detectados[0]
            linha_mouse = "O mouse foi movido para essa deteccao."
            if mover_erro is not None:
                linha_mouse = f"Falha ao mover o mouse: {mover_erro}"
            mensagem = (
                f"{label} encontrado: {len(detectados)} resultado(s).\n"
                f"Templates usados: {resultado['total_templates']}\n"
                f"Melhor score: {melhor['score']:.2f}\n"
                f"Coordenada: x={melhor['x']}, y={melhor['y']}\n\n"
                f"{linha_mouse}"
            )
            self.update_status(
                f"{label} encontrado: mouse movido para a deteccao.",
                "green",
            )
            messagebox.showinfo(f"Deteccao - {label}", mensagem, parent=self.root)
            return

        mensagem = (
            f"Nenhum resultado encontrado para {label}.\n\n"
            f"Templates usados: {resultado['total_templates']}\n\n"
            "Tente iniciar o treino novamente com o mouse bem no centro do alvo."
        )
        self.update_status(f"Nenhum resultado encontrado para {label}.", "orange")
        messagebox.showwarning(f"Deteccao - {label}", mensagem, parent=self.root)

    def iniciar_modo_treino_tracker_estado(self, minutos):
        if not self.save_config():
            return

        messagebox.showinfo(
            f"Treinar tracker {minutos}/30",
            "A janela vai sumir.\n\n"
            f"Coloque o mouse no centro do texto '{minutos}/30 min' e pressione F9.\n"
            "Cada F9 salva uma nova amostra desse estado.\n\n"
            "Pressione ESC para finalizar o treino.",
            parent=self.root,
        )
        self.root.withdraw()
        self.update_status(f"Treino tracker {minutos}/30 ativo: F9 salva amostra, ESC finaliza.")
        thread = threading.Thread(
            target=lambda: self._modo_treino_tracker_estado_worker(minutos),
            daemon=True,
        )
        thread.start()

    def _modo_treino_tracker_estado_worker(self, minutos):
        resultado = {"erro": None, "arquivos": [], "minutos": int(minutos)}
        concluido = threading.Event()

        def on_press(key):
            if key == keyboard.Key.f9:
                try:
                    mouse_x, mouse_y = get_mouse_position()
                    tracker = self.config.get("edge_tracker", {})
                    offset_x, offset_y = self.obter_offset_captura_tracker()
                    captura_x = mouse_x + offset_x
                    captura_y = mouse_y + offset_y
                    largura = int(tracker.get("capture_width", 130))
                    altura = int(tracker.get("capture_height", 42))
                    treino_dir = self.caminho_treino_tracker_estado(minutos)
                    treino_dir.mkdir(parents=True, exist_ok=True)
                    nome = datetime.now().strftime(f"edge_{int(minutos)}_%Y%m%d_%H%M%S_%f.png")
                    destino = treino_dir / nome
                    capturar_template_em_coordenada(
                        destino,
                        captura_x,
                        captura_y,
                        largura=largura,
                        altura=altura,
                    )
                    resultado["arquivos"].append(
                        {
                            "destino": destino,
                            "mouse_x": mouse_x,
                            "mouse_y": mouse_y,
                            "captura_x": captura_x,
                            "captura_y": captura_y,
                        }
                    )
                except Exception as exc:
                    resultado["erro"] = exc
                    concluido.set()
                    return False

                return True

            if key == keyboard.Key.esc:
                concluido.set()
                return False

            return True

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        concluido.wait()
        listener.stop()

        self.root.after(0, lambda: self._finalizar_modo_treino_tracker_estado(resultado))

    def _finalizar_modo_treino_tracker_estado(self, resultado):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        minutos = resultado["minutos"]
        if resultado["erro"] is not None:
            self.update_status(f"Erro no treino tracker {minutos}/30.", "red")
            messagebox.showerror(
                "Erro",
                f"Nao foi possivel salvar a amostra {minutos}/30: {resultado['erro']}",
                parent=self.root,
            )
            return

        total = len(resultado["arquivos"])
        if total == 0:
            self.update_status(f"Treino tracker {minutos}/30 encerrado sem novas amostras.", "orange")
            return

        ultimo = resultado["arquivos"][-1]
        self.update_status(f"Treino tracker {minutos}/30 finalizado: {total} amostra(s).", "green")
        messagebox.showinfo(
            f"Treino tracker {minutos}/30",
            f"{total} amostra(s) salvas em:\n{self.caminho_treino_tracker_estado(minutos)}\n\n"
            f"Ultima captura corrigida: x={ultimo['captura_x']}, y={ultimo['captura_y']}",
            parent=self.root,
        )

    def testar_progresso_edge_tracker(self):
        if not self.save_config():
            return

        self.root.withdraw()
        self.update_status("Testando progresso do tracker Edge...")
        thread = threading.Thread(target=self._testar_progresso_edge_tracker_worker, daemon=True)
        thread.start()

    def testar_ver_tudo_e_progresso_edge(self):
        if not self.save_config():
            return

        self.root.withdraw()
        self.update_status("Clicando Ver tudo e testando progresso Edge...")
        thread = threading.Thread(
            target=self._testar_ver_tudo_e_progresso_edge_worker,
            daemon=True,
        )
        thread.start()

    def _testar_progresso_edge_tracker_worker(self):
        time.sleep(0.7)
        resultado = {"erro": None, "tracker": None}
        try:
            resultado["tracker"] = detectar_estado_tracker_edge(
                self.config,
                status_callback=self.status_com_log,
            )
        except Exception as exc:
            resultado["erro"] = exc

        self.root.after(0, lambda: self._finalizar_teste_progresso_edge_tracker(resultado))

    def _testar_ver_tudo_e_progresso_edge_worker(self):
        time.sleep(0.7)
        resultado = {"erro": None, "tracker": None}
        try:
            resultado["tracker"] = abrir_ver_tudo_e_detectar_tracker_edge(
                self.config,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
                safety_callback=self.confirmar_intervencao_mouse,
            )
        except Exception as exc:
            resultado["erro"] = exc

        self.root.after(0, lambda: self._finalizar_teste_progresso_edge_tracker(resultado))

    def _finalizar_teste_progresso_edge_tracker(self, resultado):
        tracker = resultado.get("tracker")
        mover_erro = None
        if resultado["erro"] is None and tracker is not None:
            mover_erro = self.mover_mouse_para_resultado(tracker)

        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        if resultado["erro"] is not None:
            self.update_status("Erro ao testar tracker Edge.", "red")
            messagebox.showerror(
                "Erro",
                f"Nao foi possivel testar o tracker Edge: {resultado['erro']}",
                parent=self.root,
            )
            return

        if tracker is None:
            self.update_status("Nao consegui identificar o progresso do Edge.", "orange")
            messagebox.showwarning(
                "Tracker Edge",
                "Nao consegui identificar o estado do tracker.\n\n"
                "Treine os estados 0/30, 5/30 ... 30/30 ou abra o menu Rewards antes de testar.",
                parent=self.root,
            )
            return

        status = "Completo" if tracker["completo"] else "Incompleto"
        linha_mouse = "O mouse foi movido para a deteccao."
        if mover_erro is not None:
            linha_mouse = f"Falha ao mover o mouse: {mover_erro}"
        self.update_status(
            f"Tracker Edge: {tracker['minutos']}/{tracker['total']} min, faltam {tracker['faltam']} min.",
            "green" if tracker["completo"] else "blue",
        )
        messagebox.showinfo(
            "Tracker Edge",
            f"Status: {status}\n"
            f"Contabilizado: {tracker['minutos']} de {tracker['total']} min\n"
            f"Faltam: {tracker['faltam']} min\n"
            f"Score: {tracker['score']:.2f}\n\n"
            f"{linha_mouse}",
            parent=self.root,
        )

    def diagnosticar_mouse_deteccao(self):
        if not self.save_config():
            return

        messagebox.showinfo(
            "Diagnostico",
            "A janela vai sumir por alguns segundos.\n\n"
            "Deixe o mouse sobre uma area que voce quer conferir.\n"
            "O app vai salvar um print do local atual do mouse, detectar o +10/+5 e mover "
            "o mouse para o melhor resultado encontrado.",
            parent=self.root,
        )
        self.root.withdraw()
        self.update_status("Rodando diagnostico de mouse e deteccao...")
        thread = threading.Thread(target=self._diagnosticar_mouse_deteccao_worker, daemon=True)
        thread.start()

    def localizar_templates_bonus_configurados(self, templates, max_resultados=20):
        deteccao = self.config["deteccao_imagem"]
        resultados = localizar_templates(
            templates,
            confianca=deteccao["confianca"],
            regiao=deteccao.get("regiao"),
            max_resultados=max_resultados,
            parar_score=deteccao.get("score_forte", 0.95),
        )
        if resultados or not usar_variacoes_deteccao(self.config, deteccao):
            return resultados

        escalas = obter_escalas_flexiveis(deteccao)
        confianca_flexivel = obter_confianca_flexivel(
            deteccao,
            deteccao["confianca"],
        )
        resultados = localizar_templates(
            templates,
            confianca=confianca_flexivel,
            regiao=deteccao.get("regiao"),
            max_resultados=max_resultados,
            parar_score=deteccao.get("score_forte", 0.95),
            escalas=escalas,
        )
        if resultados:
            return resultados

        return localizar_templates(
            templates,
            confianca=confianca_flexivel,
            regiao=deteccao.get("regiao"),
            max_resultados=max_resultados,
            parar_score=deteccao.get("score_forte", 0.95),
            escalas=escalas,
            tons_cinza=True,
        )

    def _diagnosticar_mouse_deteccao_worker(self):
        time.sleep(0.7)
        resultado = {
            "erro": None,
            "mouse_x": None,
            "mouse_y": None,
            "debug_mouse": None,
            "print_path": None,
            "detectado": None,
            "total_templates": 0,
        }

        try:
            debug_mouse = get_mouse_position_debug()
            mouse_x, mouse_y = get_mouse_position()
            print_path = BASE_DIR / "assets" / "_debug_mouse_atual.png"
            capturar_template_em_coordenada(print_path, mouse_x, mouse_y)

            templates = listar_templates_plus_10(self.config) + listar_templates_plus_5(self.config)
            resultado["total_templates"] = len(templates)
            detectados = []
            if templates:
                detectados = self.localizar_templates_bonus_configurados(
                    templates,
                    max_resultados=20,
                )

            melhor = detectados[0] if detectados else None
            if melhor is not None:
                mover_mouse(melhor["x"], melhor["y"])

            resultado.update(
                {
                    "mouse_x": mouse_x,
                    "mouse_y": mouse_y,
                    "debug_mouse": debug_mouse,
                    "print_path": print_path,
                    "detectado": melhor,
                }
            )
        except Exception as exc:
            resultado["erro"] = exc

        self.root.after(0, lambda: self._finalizar_diagnostico_mouse_deteccao(resultado))

    def _finalizar_diagnostico_mouse_deteccao(self, resultado):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        if resultado["erro"] is not None:
            self.update_status("Erro no diagnostico.", "red")
            messagebox.showerror(
                "Erro",
                f"Nao foi possivel rodar o diagnostico: {resultado['erro']}",
                parent=self.root,
            )
            return

        debug_mouse = resultado.get("debug_mouse") or {}
        logico = debug_mouse.get("logico")
        fisico = debug_mouse.get("fisico")

        if resultado["detectado"] is None:
            mensagem = (
                f"Print do mouse salvo em:\n{resultado['print_path']}\n\n"
                f"Mouse atual: x={resultado['mouse_x']}, y={resultado['mouse_y']}\n"
                f"Mouse logico: {logico}\n"
                f"Mouse fisico: {fisico}\n"
                f"Templates usados: {resultado['total_templates']}\n\n"
                "Nenhum +10/+5 detectado."
            )
            self.update_status("Diagnostico concluido: nenhum +10/+5 detectado.", "orange")
            messagebox.showwarning("Diagnostico", mensagem, parent=self.root)
            return

        detectado = resultado["detectado"]
        mensagem = (
            f"Print do mouse salvo em:\n{resultado['print_path']}\n\n"
            f"Mouse inicial: x={resultado['mouse_x']}, y={resultado['mouse_y']}\n"
            f"Mouse logico: {logico}\n"
            f"Mouse fisico: {fisico}\n"
            f"Templates usados: {resultado['total_templates']}\n"
            f"Melhor deteccao: x={detectado['x']}, y={detectado['y']}\n"
            f"Score: {detectado['score']:.2f}\n\n"
            "O mouse foi movido para a melhor deteccao."
        )
        self.update_status("Diagnostico concluido: mouse movido para a deteccao.", "green")
        messagebox.showinfo("Diagnostico", mensagem, parent=self.root)

    def testar_deteccao_plus_10(self):
        if not self.save_config():
            return

        self.update_status("Testando deteccao +10...")
        self.root.withdraw()
        thread = threading.Thread(target=self._testar_deteccao_plus_10_worker, daemon=True)
        thread.start()

    def _testar_deteccao_plus_10_worker(self):
        time.sleep(0.7)
        resultados = []
        erro = None
        total_templates = 0

        try:
            templates = listar_templates_plus_10(self.config)
            total_templates = len(templates)
            if not templates:
                raise FileNotFoundError("Nenhum template +10 encontrado.")

            resultados = self.localizar_templates_bonus_configurados(
                templates,
                max_resultados=20,
            )
        except FileNotFoundError:
            erro = (
                "Template nao encontrado",
                "Use Iniciar treino para salvar pelo menos uma amostra +10.",
            )
        except Exception as exc:
            erro = ("Erro", f"Nao foi possivel testar a deteccao: {exc}")

        self.root.after(
            0,
            lambda: self._finalizar_teste_deteccao(
                resultados,
                erro,
                total_templates,
            ),
        )

    def _finalizar_teste_deteccao(self, resultados, erro, total_templates):
        mover_erro = None
        if erro is None and resultados:
            mover_erro = self.mover_mouse_para_resultado(resultados[0])

        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        if erro is not None:
            titulo, mensagem = erro
            self.update_status(mensagem, "red")
            messagebox.showerror(titulo, mensagem, parent=self.root)
            return

        if resultados:
            melhor = resultados[0]
            linha_mouse = "O mouse foi movido para essa deteccao."
            if mover_erro is not None:
                linha_mouse = f"Falha ao mover o mouse: {mover_erro}"
            mensagem = (
                f"+10 encontrado: {len(resultados)} resultado(s).\n"
                f"Templates usados: {total_templates}\n"
                f"Melhor score: {melhor['score']:.2f}\n"
                f"Coordenada: x={melhor['x']}, y={melhor['y']}\n\n"
                f"{linha_mouse}"
            )
            self.update_status(
                f"+10 encontrado: mouse movido para a deteccao.",
                "green",
            )
            messagebox.showinfo("Deteccao +10", mensagem, parent=self.root)
            return

        mensagem = (
            "Nenhum +10 encontrado com o template atual.\n\n"
            f"Templates usados: {total_templates}\n\n"
            "Tente iniciar o treino novamente com o mouse bem no centro do selo +10, "
            "ou reduza a confianca para 0.75."
        )
        self.update_status("Nenhum +10 encontrado com o template atual.", "orange")
        messagebox.showwarning("Deteccao +10", mensagem, parent=self.root)

    def testar_deteccao_plus_5(self):
        if not self.save_config():
            return

        self.update_status("Testando deteccao +5...")
        self.root.withdraw()
        thread = threading.Thread(target=self._testar_deteccao_plus_5_worker, daemon=True)
        thread.start()

    def _testar_deteccao_plus_5_worker(self):
        time.sleep(0.7)
        resultados = []
        erro = None
        total_templates = 0

        try:
            templates = listar_templates_plus_5(self.config)
            total_templates = len(templates)
            if not templates:
                raise FileNotFoundError("Nenhum template +5 encontrado.")

            resultados = self.localizar_templates_bonus_configurados(
                templates,
                max_resultados=20,
            )
        except FileNotFoundError:
            erro = (
                "Template +5 nao encontrado",
                "Use Iniciar treino para salvar pelo menos uma amostra +5.",
            )
        except Exception as exc:
            erro = ("Erro", f"Nao foi possivel testar a deteccao +5: {exc}")

        self.root.after(
            0,
            lambda: self._finalizar_teste_deteccao_plus_5(
                resultados,
                erro,
                total_templates,
            ),
        )

    def _finalizar_teste_deteccao_plus_5(self, resultados, erro, total_templates):
        mover_erro = None
        if erro is None and resultados:
            mover_erro = self.mover_mouse_para_resultado(resultados[0])

        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

        if erro is not None:
            titulo, mensagem = erro
            self.update_status(mensagem, "red")
            messagebox.showerror(titulo, mensagem, parent=self.root)
            return

        if resultados:
            melhor = resultados[0]
            linha_mouse = "O mouse foi movido para essa deteccao."
            if mover_erro is not None:
                linha_mouse = f"Falha ao mover o mouse: {mover_erro}"
            mensagem = (
                f"+5 encontrado: {len(resultados)} resultado(s).\n"
                f"Templates usados: {total_templates}\n"
                f"Melhor score: {melhor['score']:.2f}\n"
                f"Coordenada: x={melhor['x']}, y={melhor['y']}\n\n"
                f"{linha_mouse}"
            )
            self.update_status(
                f"+5 encontrado: mouse movido para a deteccao.",
                "green",
            )
            messagebox.showinfo("Deteccao +5", mensagem, parent=self.root)
            return

        mensagem = (
            "Nenhum +5 encontrado com o template atual.\n\n"
            f"Templates usados: {total_templates}\n\n"
            "Tente iniciar o treino novamente com o mouse bem no centro do selo +5, "
            "ou reduza a confianca para 0.75."
        )
        self.update_status("Nenhum +5 encontrado com o template atual.", "orange")
        messagebox.showwarning("Deteccao +5", mensagem, parent=self.root)

