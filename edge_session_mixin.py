from automacao_edge import (
    abrir_edge,
    abrir_extensao_rewards,
    carregar_coordenadas,
    detectar_estado_rewards_atual,
    encontrar_janela_edge,
    fechar_janela_edge,
    focar_janela_edge,
    forcar_edge_no_segundo_monitor,
    janela_parece_edge,
    janela_windows_valida,
    limpar_cache_execucao,
)


class EdgeSessionMixin:
    def resetar_sessao_edge(self):
        self.edge_session_hwnd = None
        self.edge_session_started = False
        self.edge_open_count = 0
        self.edge_restart_count = 0

    def sessao_edge_valida(self):
        return (
            self.edge_session_hwnd is not None
            and janela_windows_valida(self.edge_session_hwnd)
            and janela_parece_edge(
                self.edge_session_hwnd,
                self.config.get("navegador", {}),
            )
        )

    def garantir_sessao_edge(self):
        if self.stop_automation.is_set():
            return False

        if self.sessao_edge_valida():
            self.status_com_log("Focando janela Edge existente.")
            return focar_janela_edge(
                self.edge_session_hwnd,
                self.config,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
            )

        if self.edge_session_hwnd is not None or self.edge_session_started:
            self.status_com_log(
                "Segunda abertura do Edge bloqueada pela sessao unica. "
                "A janela do Edge parece ter sido fechada ou perdida.",
                "red",
            )
            return False

        hwnd, titulo = encontrar_janela_edge(self.config, preferir_ativa=True)
        if hwnd is not None:
            self.edge_session_hwnd = hwnd
            self.edge_session_started = True
            self.status_com_log(
                f"Sessao Edge iniciada/reutilizada. Janela: {titulo or 'sem titulo'}.",
                "green",
            )
            if not focar_janela_edge(
                hwnd,
                self.config,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
            ):
                return False
            return forcar_edge_no_segundo_monitor(
                self.config,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
                hwnd_preferido=hwnd,
            )

        self.edge_session_started = True
        self.edge_open_count += 1
        self.status_com_log("Nenhuma janela do Edge encontrada. Abrindo Edge uma unica vez.")
        if not abrir_edge(
            self.config,
            stop_event=self.stop_automation,
            status_callback=self.status_com_log,
        ):
            return False

        hwnd, titulo = encontrar_janela_edge(self.config, preferir_ativa=True)
        if hwnd is None:
            self.status_com_log(
                "Edge foi aberto, mas nao consegui armazenar a janela da sessao.",
                "red",
            )
            return False

        self.edge_session_hwnd = hwnd
        self.status_com_log(
            f"Sessao Edge iniciada/reutilizada. Janela: {titulo or 'sem titulo'}.",
            "green",
        )
        return True

    def detectar_estado_rewards(self):
        limpar_cache_execucao(self.config)
        return detectar_estado_rewards_atual(
            self.config,
            status_callback=self.status_com_log,
            stop_event=self.stop_automation,
        )

    def reiniciar_edge_por_estado_rewards(self, motivo):
        estado_config = self.config.get("rewards_estado", {})
        if not estado_config.get("permitir_reinicio_edge_erro", True):
            self.status_com_log(
                "Rewards ficou em estado inesperado, mas reinicio automatico do Edge esta desativado.",
                "red",
            )
            return False

        limite = max(0, int(estado_config.get("max_reinicios_edge", 1)))
        if self.edge_restart_count >= limite:
            self.status_com_log(
                f"Limite de reinicios do Edge por erro Rewards atingido ({limite}).",
                "red",
            )
            return False

        self.edge_restart_count += 1
        self.status_com_log(
            f"Recuperacao Rewards: reiniciando Edge por estado '{motivo}' "
            f"({self.edge_restart_count}/{limite}).",
            "orange",
        )
        self.capturar_screenshot_falha(
            f"rewards_estado_{motivo}",
            "Estado Rewards inesperado antes de reiniciar Edge.",
        )

        hwnd_antigo = self.edge_session_hwnd
        if hwnd_antigo is not None and janela_windows_valida(hwnd_antigo):
            if not fechar_janela_edge(
                hwnd_antigo,
                timeout=10,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
            ):
                return False

        self.edge_session_hwnd = None
        self.edge_session_started = False
        limpar_cache_execucao(self.config)

        delay = float(estado_config.get("delay_apos_reiniciar_edge", 4.0))
        if delay > 0:
            self.status_com_log(f"Aguardando {delay:.1f}s antes de reabrir Edge.")
            if not self.sleep_interruptivel(delay):
                return False

        self.status_com_log("Reabrindo Edge apos recuperacao do Rewards.")
        return self.garantir_sessao_edge()

    def abrir_painel_rewards_sessao(self, tentativas=2):
        coordenadas = carregar_coordenadas(self.config)
        total_tentativas = max(1, int(tentativas))

        for tentativa in range(1, total_tentativas + 1):
            if not self.garantir_sessao_edge():
                return None

            self.pressionar_esc_interno()
            if not self.sleep_interruptivel(0.4):
                return None

            limpar_cache_execucao(self.config)
            self.status_com_log(
                "Abrindo novamente apenas o painel Rewards "
                f"(tentativa {tentativa}/{total_tentativas})."
            )
            if not abrir_extensao_rewards(
                self.config,
                coordenadas,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
                safety_callback=self.confirmar_intervencao_mouse,
            ):
                continue

            if not self.sleep_intervalo(self.config["tempos"]["apos_icone_extensao"]):
                return None

            estado = self.detectar_estado_rewards()
            estado_nome = estado.get("estado", "desconhecido")
            if estado.get("ok") and estado_nome.startswith("popup_rewards_ok"):
                anchor = estado.get("anchor_exibir_painel") or {}
                if "x" in anchor and "y" in anchor:
                    return int(anchor["x"]), int(anchor["y"])

                painel = estado.get("painel") or {}
                if {"x", "y", "width", "height"}.issubset(painel):
                    return (
                        int(painel["x"] + painel["width"] // 2),
                        int(painel["y"] + min(260, max(120, painel["height"] // 4))),
                    )

            if estado_nome in {"popup_rewards_inutilizavel", "pagina_rewards_completa", "desconhecido"}:
                self.status_com_log(
                    f"Painel Rewards nao esta utilizavel ({estado_nome}).",
                    "orange",
                )
                if self.reiniciar_edge_por_estado_rewards(estado_nome):
                    continue
                return None

            self.status_com_log(
                "Painel Rewards ainda nao confirmado apos clicar na extensao.",
                "orange",
            )

        return None

