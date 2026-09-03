import copy
import ctypes
import argparse
import base64
import json
import random
import subprocess
import threading
import time
import sys
import uuid
import winsound
from ctypes import wintypes
from pathlib import Path


def ativar_dpi_awareness():
    try:
        ctypes.WinDLL("user32").SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.WinDLL("user32").SetProcessDPIAware()
            except Exception:
                pass


ativar_dpi_awareness()

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

import pyautogui as pa
import requests
from pynput import keyboard

from automacao_edge import (
    abrir_ver_tudo_e_detectar_tracker_edge,
    abrir_edge,
    aguardar_janela_edge,
    carregar_coordenadas,
    detectar_estado_tracker_edge,
    executar_fluxo_inicial,
    clicar_alvo_visual,
    encontrar_janela_edge,
    focar_janela_edge,
    janela_parece_edge,
    janela_windows_valida,
    limpar_cache_execucao,
    localizar_alvo_visual,
    listar_templates_alvo_visual,
    obter_janela_ativa,
    obter_titulo_janela,
)
from deteccao_imagem import (
    clicar_mouse,
    get_mouse_position,
)
from app_config import (
    BASE_DIR,
    CONFIG_FILE,
    COORD_LABELS,
    DEFAULT_CONFIG,
    LOGS_DIR,
    PALAVRAS_FALLBACK,
    SW_RESTORE,
    TEMPO_INTERVALO_LABELS,
    VISUAL_TARGET_LABELS,
    mesclar_config,
    migrar_config_antiga,
)
from dashboard_mixin import DashboardMixin
from edge_session_mixin import EdgeSessionMixin
from execucao_logger import ExecucaoLogger
from training_detection_mixin import TrainingDetectionMixin

AUTO_TASK_DEFAULT_NAME = "AI Rewards Automacao"


def focar_janela_por_titulo(partes_titulo, ignorar_edge_config=None):
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        if isinstance(partes_titulo, str):
            alvos = [partes_titulo]
        else:
            alvos = list(partes_titulo or [])
        alvos = [str(alvo).strip().lower() for alvo in alvos if str(alvo).strip()]
        if not alvos:
            return None

        encontrados = []

        def visitar_janela(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            if ignorar_edge_config and janela_parece_edge(
                hwnd,
                ignorar_edge_config.get("navegador", {}),
            ):
                return True

            tamanho = user32.GetWindowTextLengthW(hwnd)
            if tamanho <= 0:
                return True

            buffer = ctypes.create_unicode_buffer(tamanho + 1)
            user32.GetWindowTextW(hwnd, buffer, tamanho + 1)
            titulo = buffer.value.strip()
            titulo_normalizado = titulo.lower()
            if any(alvo in titulo_normalizado for alvo in alvos):
                encontrados.append((hwnd, titulo))
                return False

            return True

        user32.EnumWindows(enum_proc(visitar_janela), 0)
        if not encontrados:
            return None

        hwnd, titulo = encontrados[0]
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.2)
        user32.SetForegroundWindow(hwnd)
        return titulo
    except Exception:
        return None

class AutoRewardsApp(EdgeSessionMixin, DashboardMixin, TrainingDetectionMixin):
    def __init__(self, root, cli_args=None):
        self.root = root
        self.cli_args = cli_args or argparse.Namespace(
            auto_run=False,
            shutdown_on_success=False,
            scheduled_run=False,
            minimized=False,
            hide_ui=False,
        )
        self.root.title("AI Rewards Automacao")
        self.root.geometry("760x520")
        self.root.resizable(False, False)

        self.stop_automation = threading.Event()
        self.pause_automation = threading.Event()
        self.stop_automation.pause_event = self.pause_automation
        self.automation_running = False
        self.timer_automatico_aguardando = False
        self.ignorar_esc_interno_ate = 0.0
        self.brotato_aberto = False
        self.edge_session_hwnd = None
        self.edge_session_started = False
        self.edge_open_count = 0
        self.edge_restart_count = 0
        self.edge_search_restart_count = 0
        self.run_id = None
        self.ultimo_pontos_lidos = None
        self.ultima_leitura_pontos = None
        self.config = self.carregar_config()
        self.coord_vars = {}
        self.tempo_intervalo_vars = {}
        self.exec_logger = ExecucaoLogger(BASE_DIR)
        self.resumo_execucao = {}
        self.falhas_visuais = []

        self.setup_ui()
        self.start_keyboard_listener()

        if self.cli_args.auto_run:
            if self.cli_args.minimized or self.cli_args.hide_ui:
                self.root.withdraw()
            self.root.after(1000, self.start_auto_run_from_cli)

    def carregar_config(self):
        if not CONFIG_FILE.exists():
            self.salvar_json(DEFAULT_CONFIG)
            return copy.deepcopy(DEFAULT_CONFIG)

        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as arquivo:
                config_lida = json.load(arquivo)
        except (json.JSONDecodeError, OSError):
            messagebox.showerror(
                "Erro de configuracao",
                f"Nao foi possivel ler {CONFIG_FILE.name}. Usando configuracao padrao.",
            )
            return copy.deepcopy(DEFAULT_CONFIG)

        config_lida = migrar_config_antiga(config_lida)
        return mesclar_config(DEFAULT_CONFIG, config_lida)

    def salvar_json(self, config):
        config_para_salvar = copy.deepcopy(config)
        config_para_salvar.pop("_runtime_cache", None)
        with CONFIG_FILE.open("w", encoding="utf-8") as arquivo:
            json.dump(config_para_salvar, arquivo, indent=2)

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True)

        self.exec_tab = ttk.Frame(self.notebook, padding="10")
        self.agendamento_tab = ttk.Frame(self.notebook, padding="10")
        self.config_tab = ttk.Frame(self.notebook, padding="10")
        self.treino_tab = ttk.Frame(self.notebook, padding="10")
        self.debug_tab = ttk.Frame(self.notebook, padding="10")

        self.notebook.add(self.exec_tab, text="Execução")
        self.notebook.add(self.agendamento_tab, text="Agendamento automatico")
        self.notebook.add(self.config_tab, text="Configurações")
        self.notebook.add(self.treino_tab, text="Treinos e testes")
        self.notebook.add(self.debug_tab, text="Debug")

        self.config_notebook = ttk.Notebook(self.config_tab)
        self.config_notebook.pack(fill="both", expand=True)

        search_container, self.search_tab = self.criar_aba_rolavel(self.config_notebook)
        edge_container, self.edge_tempo_tab = self.criar_aba_rolavel(self.config_notebook)
        brotato_container, self.brotato_tab = self.criar_aba_rolavel(self.config_notebook)
        deteccao_container, self.deteccao_tab = self.criar_aba_rolavel(self.config_notebook)
        dashboard_container, self.dashboard_tab = self.criar_aba_rolavel(self.config_notebook)
        advanced_container, self.advanced_tab = self.criar_aba_rolavel(self.config_notebook)

        self.config_notebook.add(search_container, text="Pesquisar com o Bing")
        self.config_notebook.add(edge_container, text="Navegar com Edge")
        self.config_notebook.add(brotato_container, text="Jogar PC (Brotato)")
        self.config_notebook.add(deteccao_container, text="Detecção de imagem")
        self.config_notebook.add(dashboard_container, text="Dashboard")
        self.config_notebook.add(advanced_container, text="Avançado")

        self.treino_notebook = ttk.Notebook(self.treino_tab)
        self.treino_notebook.pack(fill="both", expand=True)

        visual_container, self.visual_train_tab = self.criar_aba_rolavel(self.treino_notebook)
        bonus_container, self.bonus_train_tab = self.criar_aba_rolavel(self.treino_notebook)
        tracker_container, self.tracker_train_tab = self.criar_aba_rolavel(self.treino_notebook)

        self.treino_notebook.add(visual_container, text="Alvos visuais")
        self.treino_notebook.add(bonus_container, text="Bonus +10/+5")
        self.treino_notebook.add(tracker_container, text="Navegar com Edge")

        self.setup_pesquisas_tab()
        self.setup_conjunto_tab()

        status_frame = ttk.Frame(main_frame, padding=(0, 10, 0, 0))
        status_frame.pack(fill="x")

        self.status_var = tk.StringVar(value="Pronto para iniciar.")
        self.status_label = ttk.Label(
            status_frame,
            textvariable=self.status_var,
            font=("Helvetica", 12),
            foreground="blue",
        )
        self.status_label.pack()

        ttk.Label(
            status_frame,
            text="Durante o timer, ESC é ignorado. Durante o fluxo, ESC cancela a execução.",
            foreground="gray",
        ).pack(pady=(8, 0))

    def criar_aba_rolavel(self, parent):
        container = ttk.Frame(parent)
        canvas = tk.Canvas(container, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        content = ttk.Frame(canvas, padding="10")
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def atualizar_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def ajustar_largura(event):
            canvas.itemconfigure(window_id, width=event.width)

        def rolar_mouse(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        content.bind("<Configure>", atualizar_scrollregion)
        canvas.bind("<Configure>", ajustar_largura)
        canvas.bind("<MouseWheel>", rolar_mouse)
        content.bind("<MouseWheel>", rolar_mouse)

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return container, content

    def setup_pesquisas_tab(self):
        pesquisas = self.config["pesquisas"]
        edge_tempo = self.config.get("edge_tempo", {})
        brotato = self.config.get("brotato", {})
        timer_automatico = self.config.get("timer_automatico", {})
        agendamento = self.config.get("agendamento_automatico", {})

        self.searches_var = tk.StringVar(value=str(pesquisas["search_count"]))
        self.desktop_x_var = tk.StringVar(value=str(pesquisas["desktop_coords"]["x"]))
        self.desktop_y_var = tk.StringVar(value=str(pesquisas["desktop_coords"]["y"]))
        self.executar_conjunto_var = tk.BooleanVar(
            value=pesquisas["executar_conjunto_diario"]
        )
        self.executar_pesquisas_var = tk.BooleanVar(
            value=pesquisas.get("executar_pesquisas", True)
        )
        self.abrir_cmd_debug_var = tk.BooleanVar(
            value=self.config.get("debug", {}).get("abrir_cmd", True)
        )
        self.usar_ctrl_l_desktop_var = tk.BooleanVar(
            value=pesquisas["usar_ctrl_l_desktop"]
        )
        self.delay_apos_conjunto_min_var = tk.StringVar(
            value=str(pesquisas["delay_apos_conjunto_diario"]["min"])
        )
        self.delay_apos_conjunto_max_var = tk.StringVar(
            value=str(pesquisas["delay_apos_conjunto_diario"]["max"])
        )
        self.delay_busca_min_var = tk.StringVar(
            value=str(pesquisas["delay_entre_buscas"]["min"])
        )
        self.delay_busca_max_var = tk.StringVar(
            value=str(pesquisas["delay_entre_buscas"]["max"])
        )
        self.palavras_min_var = tk.StringVar(
            value=str(pesquisas["palavras_por_busca"]["min"])
        )
        self.palavras_max_var = tk.StringVar(
            value=str(pesquisas["palavras_por_busca"]["max"])
        )
        self.executar_edge_tempo_var = tk.BooleanVar(
            value=edge_tempo.get("executar", False)
        )
        self.edge_video_url_var = tk.StringVar(
            value=edge_tempo.get("url_video", DEFAULT_CONFIG["edge_tempo"]["url_video"])
        )
        self.edge_primeira_espera_var = tk.StringVar(
            value=str(edge_tempo.get("primeira_espera_minutos", 36))
        )
        self.edge_margem_extra_var = tk.StringVar(
            value=str(edge_tempo.get("margem_extra_minutos", 1))
        )
        self.edge_max_tentativas_var = tk.StringVar(
            value=str(edge_tempo.get("max_tentativas", 3))
        )
        self.executar_brotato_var = tk.BooleanVar(
            value=brotato.get("executar", False)
        )
        self.brotato_app_busca_var = tk.StringVar(
            value=brotato.get("app_busca", DEFAULT_CONFIG["brotato"]["app_busca"])
        )
        self.brotato_ignorar_verificacoes_var = tk.BooleanVar(
            value=brotato.get("ignorar_verificacoes", False)
        )
        self.brotato_tempo_minutos_var = tk.StringVar(
            value=str(brotato.get("tempo_minutos", 17))
        )
        self.brotato_delay_apos_enter_var = tk.StringVar(
            value=str(brotato.get("delay_apos_enter", 10))
        )
        self.brotato_menu_timeout_var = tk.StringVar(
            value=str(brotato.get("menu_timeout_segundos", 120))
        )
        self.brotato_fechar_timeout_var = tk.StringVar(
            value=str(brotato.get("fechar_timeout_segundos", 20))
        )
        self.timer_horas_var = tk.StringVar(
            value=str(timer_automatico.get("horas", 0))
        )
        self.timer_minutos_var = tk.StringVar(
            value=str(timer_automatico.get("minutos", 0))
        )
        self.timer_segundos_var = tk.StringVar(
            value=str(timer_automatico.get("segundos", 0))
        )
        self.agendamento_horario_var = tk.StringVar(
            value=str(agendamento.get("horario", "06:00"))
        )
        self.agendamento_desligar_var = tk.BooleanVar(
            value=agendamento.get("desligar_ao_finalizar", True)
        )
        agendamento_fluxo = agendamento.get("fluxo", {})
        agendamento_fluxo_padrao = DEFAULT_CONFIG["agendamento_automatico"]["fluxo"]
        self.agendamento_executar_conjunto_var = tk.BooleanVar(
            value=agendamento_fluxo.get(
                "executar_conjunto_diario",
                agendamento_fluxo_padrao["executar_conjunto_diario"],
            )
        )
        self.agendamento_executar_pesquisas_var = tk.BooleanVar(
            value=agendamento_fluxo.get(
                "executar_pesquisas",
                agendamento_fluxo_padrao["executar_pesquisas"],
            )
        )
        self.agendamento_executar_edge_tempo_var = tk.BooleanVar(
            value=agendamento_fluxo.get(
                "executar_edge_tempo",
                agendamento_fluxo_padrao["executar_edge_tempo"],
            )
        )
        self.agendamento_executar_brotato_var = tk.BooleanVar(
            value=agendamento_fluxo.get(
                "executar_brotato",
                agendamento_fluxo_padrao["executar_brotato"],
            )
        )
        self.agendamento_comando_var = tk.StringVar(value=self.descrever_comando_agendamento())
        self.agendamento_status_var = tk.StringVar(value="Verificando tarefa...")
        dashboard = self.config.get("dashboard", {})
        leitura_pontos = dashboard.get("leitura_pontos", {})
        firebase_dashboard = dashboard.get("firebase", {})
        self.dashboard_ativada_var = tk.BooleanVar(
            value=dashboard.get("ativada", False)
        )
        self.dashboard_user_uid_var = tk.StringVar(
            value=dashboard.get("user_uid", "")
        )
        self.dashboard_api_endpoint_var = tk.StringVar(
            value=dashboard.get("api_endpoint", "")
        )
        self.dashboard_api_secret_var = tk.StringVar(
            value=dashboard.get("api_secret", "")
        )
        self.dashboard_source_var = tk.StringVar(
            value=dashboard.get("source", "python_app")
        )
        self.dashboard_project_id_var = tk.StringVar(
            value=firebase_dashboard.get("projectId", "")
        )
        self.dashboard_api_key_var = tk.StringVar(
            value=firebase_dashboard.get("apiKey", "")
        )
        double_click_x = leitura_pontos.get("double_click_x")
        double_click_y = leitura_pontos.get("double_click_y")
        self.dashboard_pontos_double_click_x_var = tk.StringVar(
            value="" if double_click_x is None else str(double_click_x)
        )
        self.dashboard_pontos_double_click_y_var = tk.StringVar(
            value="" if double_click_y is None else str(double_click_y)
        )
        self.dashboard_pontos_tentativas_var = tk.StringVar(
            value=str(leitura_pontos.get("tentativas", 3))
        )
        min_points = leitura_pontos.get("min_points")
        max_auto_drop = leitura_pontos.get("max_auto_drop")
        self.dashboard_min_points_var = tk.StringVar(
            value="" if min_points in (None, "", 0) else str(min_points)
        )
        self.dashboard_max_auto_drop_var = tk.StringVar(
            value="" if max_auto_drop in (None, "", 0) else str(max_auto_drop)
        )
        self.dashboard_max_raw_text_chars_var = tk.StringVar(
            value=str(leitura_pontos.get("max_raw_text_chars", 40))
        )
        self.dashboard_restaurar_clipboard_var = tk.BooleanVar(
            value=leitura_pontos.get("restaurar_clipboard", True)
        )

        fluxo_frame = ttk.LabelFrame(
            self.exec_tab, text="O que executar", padding="10"
        )
        fluxo_frame.pack(fill="x", pady=(0, 10))

        ttk.Checkbutton(
            fluxo_frame,
            text="Conjunto diário",
            variable=self.executar_conjunto_var,
        ).grid(row=0, column=0, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            fluxo_frame,
            text="Pesquisar com o Bing",
            variable=self.executar_pesquisas_var,
        ).grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            fluxo_frame,
            text="Navegar com Edge",
            variable=self.executar_edge_tempo_var,
        ).grid(row=0, column=2, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            fluxo_frame,
            text="Jogar PC (Brotato)",
            variable=self.executar_brotato_var,
        ).grid(row=1, column=0, sticky="w", padx=5, pady=5)

        debug_frame = ttk.LabelFrame(
            self.debug_tab, text="Debug > Log em tempo real", padding="10"
        )
        debug_frame.pack(fill="x", pady=(0, 10))
        ttk.Checkbutton(
            debug_frame,
            text="Mostrar CMD de debug em tempo real",
            variable=self.abrir_cmd_debug_var,
        ).pack(anchor="w", padx=5, pady=5)

        self.setup_agendamento_tab()

        dashboard_frame = ttk.LabelFrame(
            self.dashboard_tab, text="Dashboard > Firestore/API", padding="10"
        )
        dashboard_frame.pack(fill="x", pady=(0, 10))
        dashboard_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            dashboard_frame,
            text="Enviar leituras de pontos para o dashboard",
            variable=self.dashboard_ativada_var,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Label(dashboard_frame, text="User UID:").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(dashboard_frame, textvariable=self.dashboard_user_uid_var).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=5
        )

        ttk.Label(dashboard_frame, text="API endpoint opcional:").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(dashboard_frame, textvariable=self.dashboard_api_endpoint_var).grid(
            row=2, column=1, columnspan=3, sticky="ew", padx=5, pady=5
        )

        ttk.Label(dashboard_frame, text="API secret opcional:").grid(
            row=3, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            dashboard_frame,
            textvariable=self.dashboard_api_secret_var,
            show="*",
        ).grid(row=3, column=1, columnspan=3, sticky="ew", padx=5, pady=5)

        ttk.Label(dashboard_frame, text="Source:").grid(
            row=4, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(dashboard_frame, textvariable=self.dashboard_source_var, width=18).grid(
            row=4, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(dashboard_frame, text="Firebase projectId:").grid(
            row=5, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(dashboard_frame, textvariable=self.dashboard_project_id_var).grid(
            row=5, column=1, columnspan=3, sticky="ew", padx=5, pady=5
        )

        ttk.Label(dashboard_frame, text="Firebase apiKey:").grid(
            row=6, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(dashboard_frame, textvariable=self.dashboard_api_key_var, show="*").grid(
            row=6, column=1, columnspan=3, sticky="ew", padx=5, pady=5
        )

        leitura_frame = ttk.LabelFrame(
            self.dashboard_tab, text="Dashboard > Leitura de pontos", padding="10"
        )
        leitura_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(leitura_frame, text="Double click X:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            leitura_frame,
            textvariable=self.dashboard_pontos_double_click_x_var,
            width=8,
        ).grid(row=0, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(leitura_frame, text="Y:").grid(
            row=0, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            leitura_frame,
            textvariable=self.dashboard_pontos_double_click_y_var,
            width=8,
        ).grid(row=0, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(leitura_frame, text="Tentativas:").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            leitura_frame,
            textvariable=self.dashboard_pontos_tentativas_var,
            width=8,
        ).grid(row=1, column=1, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            leitura_frame,
            text="Restaurar clipboard depois da leitura",
            variable=self.dashboard_restaurar_clipboard_var,
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Label(leitura_frame, text="Saldo minimo opcional:").grid(
            row=3, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            leitura_frame,
            textvariable=self.dashboard_min_points_var,
            width=8,
        ).grid(row=3, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(leitura_frame, text="Queda maxima opcional:").grid(
            row=3, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            leitura_frame,
            textvariable=self.dashboard_max_auto_drop_var,
            width=8,
        ).grid(row=3, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(leitura_frame, text="Max caracteres copiados:").grid(
            row=4, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            leitura_frame,
            textvariable=self.dashboard_max_raw_text_chars_var,
            width=8,
        ).grid(row=4, column=1, sticky="w", padx=5, pady=5)

        ttk.Button(
            leitura_frame,
            text="Capturar posicao com F9",
            command=self.start_captura_posicao_pontos_dashboard,
        ).grid(row=5, column=0, columnspan=2, sticky="ew", padx=5, pady=(8, 5))

        ttk.Button(
            leitura_frame,
            text="Testar double click/leitura dos pontos",
            command=self.start_teste_offset_pontos_dashboard,
        ).grid(row=5, column=2, columnspan=2, sticky="ew", padx=5, pady=(8, 5))

        ttk.Label(
            leitura_frame,
            text=(
                "A leitura so executa o double click se encontrar 'Exibir painel'. "
                "Capture a posicao colocando o mouse sobre o numero grande e apertando F9. "
                "Deixe saldo minimo e queda maxima vazios para aceitar resgates grandes."
            ),
            foreground="gray",
            wraplength=620,
        ).grid(row=6, column=0, columnspan=4, sticky="w", padx=5, pady=(6, 0))

        timer_frame = ttk.LabelFrame(
            self.exec_tab, text="Modo timer", padding="10"
        )
        timer_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(timer_frame, text="Esperar:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(timer_frame, textvariable=self.timer_horas_var, width=6).grid(
            row=0, column=1, sticky="w", padx=5, pady=5
        )
        ttk.Label(timer_frame, text="h").grid(row=0, column=2, sticky="w")
        ttk.Entry(timer_frame, textvariable=self.timer_minutos_var, width=6).grid(
            row=0, column=3, sticky="w", padx=5, pady=5
        )
        ttk.Label(timer_frame, text="min").grid(row=0, column=4, sticky="w")
        ttk.Entry(timer_frame, textvariable=self.timer_segundos_var, width=6).grid(
            row=0, column=5, sticky="w", padx=5, pady=5
        )
        ttk.Label(timer_frame, text="s").grid(row=0, column=6, sticky="w")
        ttk.Label(
            timer_frame,
            text="Ao terminar a espera, roda o fluxo selecionado e desliga o computador.",
            foreground="gray",
        ).grid(row=1, column=0, columnspan=7, sticky="w", padx=5, pady=(2, 0))

        pesquisas_frame = ttk.LabelFrame(
            self.search_tab, text="Pesquisar com o Bing > Configuração", padding="10"
        )
        pesquisas_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(pesquisas_frame, text="Numero de buscas:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(pesquisas_frame, textvariable=self.searches_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Checkbutton(
            pesquisas_frame,
            text="Focar barra do Edge com Ctrl+L no desktop",
            variable=self.usar_ctrl_l_desktop_var,
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Label(pesquisas_frame, text="Pausa após Conjunto diário:").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            pesquisas_frame, textvariable=self.delay_apos_conjunto_min_var, width=8
        ).grid(row=2, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(pesquisas_frame, text="ate").grid(
            row=2, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            pesquisas_frame, textvariable=self.delay_apos_conjunto_max_var, width=8
        ).grid(row=2, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(pesquisas_frame, text="Delay entre buscas:").grid(
            row=3, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(pesquisas_frame, textvariable=self.delay_busca_min_var, width=8).grid(
            row=3, column=1, sticky="w", padx=5, pady=5
        )
        ttk.Label(pesquisas_frame, text="ate").grid(
            row=3, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(pesquisas_frame, textvariable=self.delay_busca_max_var, width=8).grid(
            row=3, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(pesquisas_frame, text="Palavras por busca:").grid(
            row=4, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(pesquisas_frame, textvariable=self.palavras_min_var, width=8).grid(
            row=4, column=1, sticky="w", padx=5, pady=5
        )
        ttk.Label(pesquisas_frame, text="ate").grid(
            row=4, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(pesquisas_frame, textvariable=self.palavras_max_var, width=8).grid(
            row=4, column=3, sticky="w", padx=5, pady=5
        )

        edge_tempo_frame = ttk.LabelFrame(
            self.edge_tempo_tab, text="Navegar com Edge > Vídeo e verificação", padding="10"
        )
        edge_tempo_frame.pack(fill="x", pady=10)
        edge_tempo_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            edge_tempo_frame,
            text="Executar Navegar com Edge depois das etapas selecionadas",
            variable=self.executar_edge_tempo_var,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Label(edge_tempo_frame, text="URL do video:").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(edge_tempo_frame, textvariable=self.edge_video_url_var).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=5
        )

        ttk.Label(edge_tempo_frame, text="Primeira espera (min):").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(edge_tempo_frame, textvariable=self.edge_primeira_espera_var, width=8).grid(
            row=2, column=1, sticky="w", padx=5, pady=5
        )
        ttk.Label(edge_tempo_frame, text="Extra (min):").grid(
            row=2, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(edge_tempo_frame, textvariable=self.edge_margem_extra_var, width=8).grid(
            row=2, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(edge_tempo_frame, text="Max verificacoes:").grid(
            row=3, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(edge_tempo_frame, textvariable=self.edge_max_tentativas_var, width=8).grid(
            row=3, column=1, sticky="w", padx=5, pady=5
        )

        brotato_frame = ttk.LabelFrame(
            self.brotato_tab, text="Jogar PC (Brotato) > Xbox Game Pass", padding="10"
        )
        brotato_frame.pack(fill="x", pady=10)
        brotato_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            brotato_frame,
            text="Executar Jogar PC (Brotato)",
            variable=self.executar_brotato_var,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Label(brotato_frame, text="Buscar app:").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_app_busca_var).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=5
        )

        ttk.Checkbutton(
            brotato_frame,
            text="Ignorar verificacoes visuais (abrir app e voltar ao Edge)",
            variable=self.brotato_ignorar_verificacoes_var,
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Label(brotato_frame, text="Timer sem Edge (min):").grid(
            row=3, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_tempo_minutos_var, width=8).grid(
            row=3, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(brotato_frame, text="Delay apos abrir (seg):").grid(
            row=4, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_delay_apos_enter_var, width=8).grid(
            row=4, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(brotato_frame, text="Timeout menu (seg):").grid(
            row=5, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_menu_timeout_var, width=8).grid(
            row=5, column=1, sticky="w", padx=5, pady=5
        )
        ttk.Label(brotato_frame, text="Timeout fechar (seg):").grid(
            row=5, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_fechar_timeout_var, width=8).grid(
            row=5, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(
            brotato_frame,
            text=(
                "Com Navegar com Edge ativo, o jogo abre antes da espera do Edge e fecha "
                "antes da verificação do Rewards. No modo sem verificacoes, ele so abre o app "
                "configurado e pula Gamer Tag/icone da barra."
            ),
            foreground="gray",
            wraplength=620,
        ).grid(row=6, column=0, columnspan=4, sticky="w", padx=5, pady=(8, 3))

        coords_frame = ttk.LabelFrame(
            self.search_tab, text="Pesquisar com o Bing > Barra de busca", padding="10"
        )
        coords_frame.pack(fill="x", pady=10)

        self.add_xy_row(
            coords_frame,
            0,
            "Desktop",
            self.desktop_x_var,
            self.desktop_y_var,
        )

        self.exec_action_frame = ttk.LabelFrame(
            self.exec_tab, text="Acoes", padding="10"
        )
        self.exec_action_frame.pack(fill="x", pady=10)
        self.exec_action_frame.columnconfigure(0, weight=1)
        self.exec_action_frame.columnconfigure(1, weight=1)
        self.exec_action_frame.columnconfigure(2, weight=1)
        self.exec_action_frame.columnconfigure(3, weight=1)

        self.start_button = ttk.Button(
            self.exec_action_frame,
            text="Iniciar fluxo selecionado",
            command=self.start_fluxo_completo_thread,
        )
        self.start_button.grid(row=0, column=0, padx=5, sticky="ew")

        self.timer_button = ttk.Button(
            self.exec_action_frame,
            text="Iniciar timer",
            command=self.start_timer_automatico_thread,
        )
        self.timer_button.grid(row=0, column=1, padx=5, sticky="ew")

        ttk.Button(
            self.exec_action_frame,
            text="Salvar configuracoes",
            command=self.save_config,
        ).grid(row=0, column=3, padx=5, sticky="ew")

        self.pause_button = ttk.Button(
            self.exec_action_frame,
            text="Pausar",
            command=self.pausar_automacao,
            state="disabled",
        )
        self.pause_button.grid(row=1, column=0, padx=5, pady=(8, 0), sticky="ew")

        self.resume_button = ttk.Button(
            self.exec_action_frame,
            text="Resumir",
            command=self.resumir_automacao,
            state="disabled",
        )
        self.resume_button.grid(row=1, column=1, padx=5, pady=(8, 0), sticky="ew")

        self.cancel_button = ttk.Button(
            self.exec_action_frame,
            text="Cancelar",
            command=self.cancelar_automacao,
            state="disabled",
        )
        self.cancel_button.grid(row=1, column=2, padx=5, pady=(8, 0), sticky="ew")

    def setup_agendamento_tab(self):
        fluxo_frame = ttk.LabelFrame(
            self.agendamento_tab,
            text="Agendamento automatico > O que executar",
            padding="10",
        )
        fluxo_frame.pack(fill="x", pady=(0, 10))

        ttk.Checkbutton(
            fluxo_frame,
            text="Conjunto diario",
            variable=self.agendamento_executar_conjunto_var,
        ).grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Checkbutton(
            fluxo_frame,
            text="Pesquisar com o Bing",
            variable=self.agendamento_executar_pesquisas_var,
        ).grid(row=0, column=1, sticky="w", padx=5, pady=5)
        ttk.Checkbutton(
            fluxo_frame,
            text="Navegar com Edge",
            variable=self.agendamento_executar_edge_tempo_var,
        ).grid(row=0, column=2, sticky="w", padx=5, pady=5)
        ttk.Checkbutton(
            fluxo_frame,
            text="Jogar PC (Brotato)",
            variable=self.agendamento_executar_brotato_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        ttk.Label(
            fluxo_frame,
            text=(
                "Essas opcoes valem apenas para a execucao agendada. "
                "A aba Execucao continua controlando somente o uso manual e o timer."
            ),
            foreground="gray",
            wraplength=680,
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=5, pady=(6, 0))

        agendamento_frame = ttk.LabelFrame(
            self.agendamento_tab, text="Agendamento automatico > Windows", padding="10"
        )
        agendamento_frame.pack(fill="x", pady=(0, 10))
        agendamento_frame.columnconfigure(1, weight=1)

        ttk.Label(agendamento_frame, text="Horario diario:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            agendamento_frame,
            textvariable=self.agendamento_horario_var,
            width=10,
        ).grid(row=0, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(agendamento_frame, text="formato 24h, exemplo 06:00").grid(
            row=0, column=2, sticky="w", padx=5, pady=5
        )

        ttk.Checkbutton(
            agendamento_frame,
            text="Desligar o computador ao finalizar a execucao agendada",
            variable=self.agendamento_desligar_var,
        ).grid(row=1, column=0, columnspan=3, sticky="w", padx=5, pady=5)

        ttk.Label(agendamento_frame, text="Comando detectado:").grid(
            row=2, column=0, sticky="nw", padx=5, pady=5
        )
        ttk.Label(
            agendamento_frame,
            textvariable=self.agendamento_comando_var,
            wraplength=560,
            foreground="gray",
        ).grid(row=2, column=1, columnspan=2, sticky="ew", padx=5, pady=5)

        botoes_frame = ttk.Frame(agendamento_frame)
        botoes_frame.grid(row=3, column=0, columnspan=3, sticky="ew", padx=5, pady=(8, 5))
        botoes_frame.columnconfigure(0, weight=1)
        botoes_frame.columnconfigure(1, weight=1)
        botoes_frame.columnconfigure(2, weight=1)

        self.install_schedule_button = ttk.Button(
            botoes_frame,
            text="Instalar/Atualizar agendamento",
            command=self.instalar_agendamento_windows,
        )
        self.install_schedule_button.grid(row=0, column=0, padx=4, sticky="ew")

        self.remove_schedule_button = ttk.Button(
            botoes_frame,
            text="Remover agendamento",
            command=self.remover_agendamento_windows,
        )
        self.remove_schedule_button.grid(row=0, column=1, padx=4, sticky="ew")

        self.test_schedule_button = ttk.Button(
            botoes_frame,
            text="Testar execucao automatica agora",
            command=self.testar_execucao_automatica_agendada,
        )
        self.test_schedule_button.grid(row=0, column=2, padx=4, sticky="ew")

        status_frame = ttk.LabelFrame(
            self.agendamento_tab, text="Agendamento automatico > Status", padding="10"
        )
        status_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(
            status_frame,
            textvariable=self.agendamento_status_var,
            foreground="blue",
            wraplength=680,
        ).pack(anchor="w", padx=5, pady=5)

        ttk.Label(
            self.agendamento_tab,
            text=(
                "Para desligado real, configure Power On By RTC/Wake By Alarm na BIOS/UEFI "
                "alguns minutos antes desse horario. Para suspensao/hibernacao, o Agendador "
                "do Windows pode acordar o PC. Auto-login deve ser configurado fora do app."
            ),
            foreground="gray",
            wraplength=690,
        ).pack(anchor="w", padx=5, pady=(4, 0))

        self.root.after(500, self.atualizar_status_agendamento)

    def setup_conjunto_tab(self):
        self.app_busca_var = tk.StringVar(value=str(self.config["app_busca"]))
        self.apos_windows_var = tk.StringVar(
            value=str(self.config["tempos"]["apos_windows"])
        )
        self.apos_digitar_app_var = tk.StringVar(
            value=str(self.config["tempos"]["apos_digitar_app"])
        )
        self.apos_enter_var = tk.StringVar(value=str(self.config["tempos"]["apos_enter"]))
        self.movimento_mouse_var = tk.StringVar(
            value=str(self.config["tempos"]["movimento_mouse"])
        )
        navegador = self.config.get("navegador", {})
        self.forcar_edge_segundo_monitor_var = tk.BooleanVar(
            value=navegador.get("forcar_segundo_monitor", False)
        )
        self.buscar_titulo_janela_edge_var = tk.BooleanVar(
            value=navegador.get("buscar_titulo_janela", False)
        )
        self.fechar_popup_restaurar_paginas_var = tk.BooleanVar(
            value=navegador.get("fechar_popup_restaurar_paginas", True)
        )
        deteccao = self.config["deteccao_imagem"]
        usando_versao_fixa = self.config.get("automacao", {}).get(
            "usar_versao_fixa", True
        )
        self.modo_conjunto_var = tk.StringVar(
            value="fixa" if usando_versao_fixa else "imagem"
        )
        self.template_plus_10_var = tk.StringVar(value=deteccao["template_plus_10"])
        self.template_plus_5_var = tk.StringVar(
            value=deteccao.get("template_plus_5", "assets/plus_5.png")
        )
        self.usar_plus_10_var = tk.BooleanVar(value=deteccao.get("usar_plus_10", True))
        self.usar_plus_5_var = tk.BooleanVar(value=deteccao.get("usar_plus_5", True))
        self.usar_treinamento_var = tk.BooleanVar(
            value=deteccao["usar_treinamento"]
        )
        self.usar_variacoes_deteccao_var = tk.BooleanVar(
            value=deteccao.get("usar_variacoes", False)
        )
        self.treino_dir_var = tk.StringVar(value=deteccao["treino_dir"])
        self.treino_dir_plus_5_var = tk.StringVar(
            value=deteccao.get("treino_dir_plus_5", "assets/treino_plus_5")
        )
        self.confianca_plus_10_var = tk.StringVar(value=str(deteccao["confianca"]))
        self.score_forte_var = tk.StringVar(value=str(deteccao.get("score_forte", 0.95)))
        self.max_cards_var = tk.StringVar(value=str(deteccao["max_cards"]))
        self.max_scrolls_var = tk.StringVar(value=str(deteccao["max_scrolls"]))
        self.scroll_amount_var = tk.StringVar(value=str(deteccao["scroll_amount"]))
        self.capture_offset_x_var = tk.StringVar(
            value=str(deteccao["capture_offset_x"])
        )
        self.capture_offset_y_var = tk.StringVar(
            value=str(deteccao["capture_offset_y"])
        )
        self.click_offset_x_var = tk.StringVar(value=str(deteccao["click_offset_x"]))
        self.click_offset_y_var = tk.StringVar(value=str(deteccao["click_offset_y"]))

        abertura_frame = ttk.LabelFrame(
            self.advanced_tab, text="Avancado > Abertura do navegador", padding="10"
        )
        abertura_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(abertura_frame, text="Buscar app:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(abertura_frame, textvariable=self.app_busca_var, width=14).grid(
            row=0, column=1, sticky="w", padx=5, pady=5
        )

        self.add_float_row(
            abertura_frame, 1, "Apos Windows", self.apos_windows_var, "seg"
        )
        self.add_float_row(
            abertura_frame, 2, "Apos digitar app", self.apos_digitar_app_var, "seg"
        )
        self.add_float_row(abertura_frame, 3, "Apos Enter", self.apos_enter_var, "seg")
        self.add_float_row(
            abertura_frame, 4, "Movimento mouse", self.movimento_mouse_var, "seg"
        )
        ttk.Checkbutton(
            abertura_frame,
            text="Forcar Edge no segundo monitor",
            variable=self.forcar_edge_segundo_monitor_var,
        ).grid(row=5, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            abertura_frame,
            text="Buscar janela pelo titulo antes dos atalhos",
            variable=self.buscar_titulo_janela_edge_var,
        ).grid(row=6, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            abertura_frame,
            text="Fechar popup 'Restaurar paginas' antes do Rewards",
            variable=self.fechar_popup_restaurar_paginas_var,
        ).grid(row=7, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        modo_frame = ttk.LabelFrame(
            self.deteccao_tab, text="Deteccao de imagem > Modo", padding="10"
        )
        modo_frame.pack(fill="x", pady=10)

        ttk.Label(
            modo_frame,
            text="Escolha um modo para executar o Conjunto diário:",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=5, pady=(3, 6))

        ttk.Radiobutton(
            modo_frame,
            text="Deteccao por imagem (usa templates e treino)",
            variable=self.modo_conjunto_var,
            value="imagem",
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=5, pady=3)

        ttk.Radiobutton(
            modo_frame,
            text="Coordenadas fixas (modo antigo)",
            variable=self.modo_conjunto_var,
            value="fixa",
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=3)

        ttk.Label(
            modo_frame,
            text=(
                "Imagem procura os botoes na tela. Coordenadas fixas usa os pontos "
                "salvos em Configuracoes > Avancado."
            ),
            foreground="gray",
            wraplength=620,
        ).grid(row=3, column=0, columnspan=4, sticky="w", padx=5, pady=(6, 3))

        visual_frame = ttk.LabelFrame(
            self.visual_train_tab, text="Treino > Alvos visuais da nova versao", padding="10"
        )
        visual_frame.pack(fill="x", pady=10)
        visual_frame.columnconfigure(1, weight=1)
        visual_frame.columnconfigure(2, weight=1)

        for row, (nome, label) in enumerate(VISUAL_TARGET_LABELS.items()):
            ttk.Label(visual_frame, text=f"{label}:").grid(
                row=row, column=0, sticky="w", padx=5, pady=4
            )
            ttk.Button(
                visual_frame,
                text="Iniciar treino",
                command=lambda alvo=nome: self.iniciar_modo_treino_alvo_visual(alvo),
            ).grid(row=row, column=1, sticky="ew", padx=5, pady=4)
            ttk.Button(
                visual_frame,
                text="Testar deteccao",
                command=lambda alvo=nome: self.testar_deteccao_alvo_visual(alvo),
            ).grid(row=row, column=2, sticky="ew", padx=5, pady=4)

        tracker_frame = ttk.LabelFrame(
            self.tracker_train_tab, text="Treino > Tracker Edge 30 minutos", padding="10"
        )
        tracker_frame.pack(fill="x", pady=10)
        tracker_frame.columnconfigure(0, weight=1)
        tracker_frame.columnconfigure(1, weight=1)
        tracker_frame.columnconfigure(2, weight=1)
        tracker_frame.columnconfigure(3, weight=1)

        estados_tracker = self.config.get("edge_tracker", {}).get(
            "estados_minutos", [0, 5, 10, 15, 20, 25, 30]
        )
        for index, minutos in enumerate(estados_tracker):
            ttk.Button(
                tracker_frame,
                text=f"Treinar {minutos}/30",
                command=lambda valor=minutos: self.iniciar_modo_treino_tracker_estado(valor),
            ).grid(row=index // 4, column=index % 4, sticky="ew", padx=5, pady=4)

        ttk.Button(
            tracker_frame,
            text="Testar progresso Edge",
            command=self.testar_progresso_edge_tracker,
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=(8, 4))

        ttk.Button(
            tracker_frame,
            text="Clicar Ver tudo + testar",
            command=self.testar_ver_tudo_e_progresso_edge,
        ).grid(row=2, column=2, columnspan=2, sticky="ew", padx=5, pady=(8, 4))

        deteccao_frame = ttk.LabelFrame(
            self.deteccao_tab, text="Deteccao de imagem > Confianca e limites", padding="10"
        )
        deteccao_frame.pack(fill="x", pady=10)
        deteccao_frame.columnconfigure(1, weight=1)
        deteccao_frame.columnconfigure(2, weight=1)

        ttk.Checkbutton(
            deteccao_frame,
            text="Clicar bonus +10",
            variable=self.usar_plus_10_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=3)

        ttk.Checkbutton(
            deteccao_frame,
            text="Clicar bonus +5",
            variable=self.usar_plus_5_var,
        ).grid(row=0, column=2, columnspan=2, sticky="w", padx=5, pady=3)

        ttk.Checkbutton(
            deteccao_frame,
            text="Usar base de treino",
            variable=self.usar_treinamento_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=5, pady=3)

        ttk.Checkbutton(
            deteccao_frame,
            text="Usar variacoes para melhorar a deteccao",
            variable=self.usar_variacoes_deteccao_var,
        ).grid(row=1, column=2, columnspan=2, sticky="w", padx=5, pady=3)

        ttk.Label(deteccao_frame, text="Confianca:").grid(
            row=2, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.confianca_plus_10_var, width=8).grid(
            row=2, column=1, sticky="w", padx=5, pady=3
        )
        ttk.Label(deteccao_frame, text="Match forte:").grid(
            row=2, column=2, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.score_forte_var, width=8).grid(
            row=2, column=3, sticky="w", padx=5, pady=3
        )

        ttk.Label(deteccao_frame, text="Max cards:").grid(
            row=3, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.max_cards_var, width=8).grid(
            row=3, column=1, sticky="w", padx=5, pady=3
        )

        ttk.Label(deteccao_frame, text="Limite scrolls:").grid(
            row=4, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.max_scrolls_var, width=8).grid(
            row=4, column=1, sticky="w", padx=5, pady=3
        )
        ttk.Label(deteccao_frame, text="Scroll por busca:").grid(
            row=4, column=2, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.scroll_amount_var, width=8).grid(
            row=4, column=3, sticky="w", padx=5, pady=3
        )

        bonus_train_frame = ttk.LabelFrame(
            self.bonus_train_tab, text="Treino > Bonus Rewards (+10/+5)", padding="10"
        )
        bonus_train_frame.pack(fill="x", pady=(0, 10))
        bonus_train_frame.columnconfigure(1, weight=1)
        bonus_train_frame.columnconfigure(2, weight=1)

        ttk.Label(bonus_train_frame, text="+10:").grid(
            row=0, column=0, sticky="w", padx=5, pady=4
        )
        ttk.Button(
            bonus_train_frame,
            text="Iniciar treino",
            command=self.iniciar_modo_treino_plus_10,
        ).grid(row=0, column=1, sticky="ew", padx=5, pady=4)
        ttk.Button(
            bonus_train_frame,
            text="Testar deteccao",
            command=self.testar_deteccao_plus_10,
        ).grid(row=0, column=2, sticky="ew", padx=5, pady=4)

        ttk.Label(bonus_train_frame, text="+5:").grid(
            row=1, column=0, sticky="w", padx=5, pady=4
        )
        ttk.Button(
            bonus_train_frame,
            text="Iniciar treino",
            command=self.iniciar_modo_treino_plus_5,
        ).grid(row=1, column=1, sticky="ew", padx=5, pady=4)
        ttk.Button(
            bonus_train_frame,
            text="Testar deteccao",
            command=self.testar_deteccao_plus_5,
        ).grid(row=1, column=2, sticky="ew", padx=5, pady=4)

        ttk.Button(
            bonus_train_frame,
            text="Diagnostico mouse + deteccao",
            command=self.diagnosticar_mouse_deteccao,
        ).grid(row=2, column=0, columnspan=3, sticky="ew", padx=5, pady=(8, 3))

        coords_frame = ttk.LabelFrame(
            self.advanced_tab, text="Avancado > Coordenadas da versao fixa", padding="10"
        )
        coords_frame.pack(fill="x", pady=10)

        for row, (nome, label) in enumerate(COORD_LABELS.items()):
            coord = self.config["coordenadas"][nome]
            x_var = tk.StringVar(value="" if coord["x"] is None else str(coord["x"]))
            y_var = tk.StringVar(value="" if coord["y"] is None else str(coord["y"]))
            self.coord_vars[nome] = (x_var, y_var)
            self.add_xy_row(coords_frame, row, label, x_var, y_var)

        tempos_frame = ttk.LabelFrame(
            self.advanced_tab, text="Avancado > Intervalos aleatorios", padding="10"
        )
        tempos_frame.pack(fill="x", pady=10)

        for row, (nome, label) in enumerate(TEMPO_INTERVALO_LABELS.items()):
            intervalo = self.config["tempos"][nome]
            min_var = tk.StringVar(value=str(intervalo["min"]))
            max_var = tk.StringVar(value=str(intervalo["max"]))
            self.tempo_intervalo_vars[nome] = (min_var, max_var)
            ttk.Label(tempos_frame, text=f"{label}:").grid(
                row=row, column=0, sticky="w", padx=5, pady=3
            )
            ttk.Entry(tempos_frame, textvariable=min_var, width=8).grid(
                row=row, column=1, sticky="w", padx=5, pady=3
            )
            ttk.Label(tempos_frame, text="ate").grid(
                row=row, column=2, sticky="w", padx=5, pady=3
            )
            ttk.Entry(tempos_frame, textvariable=max_var, width=8).grid(
                row=row, column=3, sticky="w", padx=5, pady=3
            )

        self.conjunto_button = ttk.Button(
            self.exec_action_frame,
            text="Rodar só Conjunto diário",
            command=self.start_conjunto_thread,
        )
        self.conjunto_button.grid(row=0, column=2, padx=5, sticky="ew")

    def add_xy_row(self, parent, row, label, x_var, y_var):
        ttk.Label(parent, text=f"{label}:").grid(
            row=row, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Label(parent, text="X").grid(row=row, column=1, sticky="w", padx=5, pady=3)
        ttk.Entry(parent, textvariable=x_var, width=9).grid(
            row=row, column=2, sticky="w", padx=5, pady=3
        )
        ttk.Label(parent, text="Y").grid(row=row, column=3, sticky="w", padx=5, pady=3)
        ttk.Entry(parent, textvariable=y_var, width=9).grid(
            row=row, column=4, sticky="w", padx=5, pady=3
        )
        ttk.Button(
            parent,
            text="Calibrar",
            command=lambda: self.calibrar_coords(x_var, y_var),
        ).grid(row=row, column=5, padx=10, pady=3)

    def add_float_row(self, parent, row, label, var, suffix):
        ttk.Label(parent, text=f"{label}:").grid(
            row=row, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(parent, textvariable=var, width=9).grid(
            row=row, column=1, sticky="w", padx=5, pady=3
        )
        ttk.Label(parent, text=suffix).grid(row=row, column=2, sticky="w", padx=5)

    def calibrar_coords(self, x_var, y_var):
        messagebox.showinfo(
            "Calibrar posicao",
            "Voce tem 3 segundos para mover o mouse ate a posicao desejada.",
        )
        self.root.withdraw()
        time.sleep(3)

        try:
            x, y = get_mouse_position()
            x_var.set(str(x))
            y_var.set(str(y))
            messagebox.showinfo("Sucesso", f"Posicao capturada: X={x}, Y={y}")
        except Exception as exc:
            messagebox.showerror(
                "Erro", f"Nao foi possivel capturar a posicao do mouse: {exc}"
            )
        finally:
            self.root.deiconify()













































    def parse_int(self, var, nome):
        try:
            return int(var.get().strip())
        except ValueError as exc:
            raise ValueError(f"{nome} precisa ser um numero inteiro.") from exc

    def parse_int_nao_negativo(self, var, nome):
        valor = self.parse_int(var, nome)
        if valor < 0:
            raise ValueError(f"{nome} nao pode ser negativo.")
        return valor

    def parse_int_nao_negativo_or_none(self, var, nome):
        valor = self.parse_int_or_none(var, nome)
        if valor is not None and valor < 0:
            raise ValueError(f"{nome} nao pode ser negativo.")
        return valor

    def parse_int_or_none(self, var, nome):
        valor = var.get().strip()
        if valor == "":
            return None

        try:
            return int(valor)
        except ValueError as exc:
            raise ValueError(f"{nome} precisa ser um numero inteiro.") from exc

    def parse_float(self, var, nome):
        try:
            return float(var.get().strip())
        except ValueError as exc:
            raise ValueError(f"{nome} precisa ser um numero.") from exc

    def parse_intervalo(self, min_var, max_var, nome):
        minimo = self.parse_float(min_var, f"{nome} minimo")
        maximo = self.parse_float(max_var, f"{nome} maximo")

        if minimo > maximo:
            raise ValueError(f"{nome}: o minimo nao pode ser maior que o maximo.")

        return {"min": minimo, "max": maximo}

    def save_config(self):
        try:
            self.config["app_busca"] = self.app_busca_var.get().strip() or "EDGE"
            self.config["tempos"]["apos_windows"] = self.parse_float(
                self.apos_windows_var, "Apos Windows"
            )
            self.config["tempos"]["apos_digitar_app"] = self.parse_float(
                self.apos_digitar_app_var, "Apos digitar app"
            )
            self.config["tempos"]["apos_enter"] = self.parse_float(
                self.apos_enter_var, "Apos Enter"
            )
            self.config["tempos"]["movimento_mouse"] = self.parse_float(
                self.movimento_mouse_var, "Movimento mouse"
            )
            navegador = self.config.setdefault("navegador", {})
            navegador["forcar_segundo_monitor"] = self.forcar_edge_segundo_monitor_var.get()
            navegador["buscar_titulo_janela"] = self.buscar_titulo_janela_edge_var.get()
            navegador[
                "fechar_popup_restaurar_paginas"
            ] = self.fechar_popup_restaurar_paginas_var.get()
            navegador.setdefault("titulo_janela", "Microsoft Edge")
            self.config.setdefault("automacao", {})
            modo_por_imagem = self.modo_conjunto_var.get() == "imagem"
            self.config["automacao"]["usar_versao_fixa"] = not modo_por_imagem

            for nome, (x_var, y_var) in self.coord_vars.items():
                self.config["coordenadas"][nome]["x"] = self.parse_int_or_none(
                    x_var, f"{COORD_LABELS[nome]} X"
                )
                self.config["coordenadas"][nome]["y"] = self.parse_int_or_none(
                    y_var, f"{COORD_LABELS[nome]} Y"
                )

            for nome, (min_var, max_var) in self.tempo_intervalo_vars.items():
                self.config["tempos"][nome] = self.parse_intervalo(
                    min_var, max_var, TEMPO_INTERVALO_LABELS[nome]
                )

            deteccao = self.config["deteccao_imagem"]
            deteccao["ativada"] = modo_por_imagem
            deteccao["usar_fallback_coordenadas"] = not modo_por_imagem
            deteccao["template_plus_10"] = (
                self.template_plus_10_var.get().strip() or "assets/plus_10.png"
            )
            deteccao["template_plus_5"] = (
                self.template_plus_5_var.get().strip() or "assets/plus_5.png"
            )
            deteccao["usar_plus_10"] = self.usar_plus_10_var.get()
            deteccao["usar_plus_5"] = self.usar_plus_5_var.get()
            deteccao["usar_treinamento"] = self.usar_treinamento_var.get()
            deteccao["usar_variacoes"] = self.usar_variacoes_deteccao_var.get()
            deteccao["busca_flexivel"] = deteccao["usar_variacoes"]
            deteccao["treino_dir"] = (
                self.treino_dir_var.get().strip() or "assets/treino_plus_10"
            )
            deteccao["treino_dir_plus_5"] = (
                self.treino_dir_plus_5_var.get().strip() or "assets/treino_plus_5"
            )
            deteccao["confianca"] = self.parse_float(
                self.confianca_plus_10_var, "Confianca +10"
            )
            deteccao["score_forte"] = self.parse_float(
                self.score_forte_var, "Match forte"
            )
            deteccao["max_cards"] = self.parse_int(self.max_cards_var, "Max cards")
            deteccao["max_scrolls"] = self.parse_int(self.max_scrolls_var, "Max scrolls")
            deteccao["scroll_amount"] = self.parse_int(self.scroll_amount_var, "Scroll")
            deteccao["capture_offset_x"] = self.parse_int(
                self.capture_offset_x_var, "Offset captura X"
            )
            deteccao["capture_offset_y"] = self.parse_int(
                self.capture_offset_y_var, "Offset captura Y"
            )
            deteccao["click_offset_x"] = self.parse_int(
                self.click_offset_x_var, "Offset click X"
            )
            deteccao["click_offset_y"] = self.parse_int(
                self.click_offset_y_var, "Offset click Y"
            )

            if not 0 < deteccao["confianca"] <= 1:
                raise ValueError("Confianca +10 precisa ficar entre 0 e 1.")
            if not 0 < deteccao["score_forte"] <= 1:
                raise ValueError("Match forte precisa ficar entre 0 e 1.")
            if deteccao["max_cards"] < 0:
                raise ValueError("Max cards nao pode ser negativo.")
            if deteccao["max_scrolls"] < 0:
                raise ValueError("Max scrolls nao pode ser negativo.")

            self.config.setdefault("debug", {})
            self.config["debug"]["abrir_cmd"] = self.abrir_cmd_debug_var.get()

            dashboard = self.config.setdefault("dashboard", {})
            dashboard["ativada"] = self.dashboard_ativada_var.get()
            dashboard["user_uid"] = self.dashboard_user_uid_var.get().strip()
            dashboard["api_endpoint"] = self.dashboard_api_endpoint_var.get().strip()
            dashboard["api_secret"] = self.dashboard_api_secret_var.get().strip()
            dashboard["source"] = self.dashboard_source_var.get().strip() or "python_app"
            firebase_dashboard = dashboard.setdefault("firebase", {})
            firebase_dashboard["apiKey"] = self.dashboard_api_key_var.get().strip()
            firebase_dashboard["projectId"] = self.dashboard_project_id_var.get().strip()
            firebase_dashboard.setdefault(
                "authDomain",
                "personalrewardsdashboard.firebaseapp.com",
            )
            firebase_dashboard.setdefault(
                "storageBucket",
                "personalrewardsdashboard.firebasestorage.app",
            )
            firebase_dashboard.setdefault("messagingSenderId", "990756612461")
            firebase_dashboard.setdefault(
                "appId",
                "1:990756612461:web:ed86a992035287ec1fd264",
            )
            leitura_pontos = dashboard.setdefault("leitura_pontos", {})
            leitura_pontos["double_click_x"] = self.parse_int_or_none(
                self.dashboard_pontos_double_click_x_var,
                "Dashboard double click X",
            )
            leitura_pontos["double_click_y"] = self.parse_int_or_none(
                self.dashboard_pontos_double_click_y_var,
                "Dashboard double click Y",
            )
            leitura_pontos["tentativas"] = self.parse_int(
                self.dashboard_pontos_tentativas_var,
                "Dashboard tentativas leitura",
            )
            leitura_pontos["restaurar_clipboard"] = (
                self.dashboard_restaurar_clipboard_var.get()
            )
            leitura_pontos["min_points"] = self.parse_int_nao_negativo_or_none(
                self.dashboard_min_points_var,
                "Dashboard pontos minimos",
            )
            leitura_pontos["max_auto_drop"] = self.parse_int_nao_negativo_or_none(
                self.dashboard_max_auto_drop_var,
                "Dashboard queda maxima automatica",
            )
            leitura_pontos["max_raw_text_chars"] = self.parse_int(
                self.dashboard_max_raw_text_chars_var,
                "Dashboard max caracteres copiados",
            )
            if (
                leitura_pontos["double_click_x"] is None
                and leitura_pontos["double_click_y"] is not None
            ) or (
                leitura_pontos["double_click_x"] is not None
                and leitura_pontos["double_click_y"] is None
            ):
                raise ValueError("Preencha X e Y da leitura de pontos, ou deixe ambos vazios.")
            if leitura_pontos["tentativas"] <= 0:
                raise ValueError("Dashboard tentativas precisa ser maior que zero.")
            if leitura_pontos["max_raw_text_chars"] <= 0:
                raise ValueError("Dashboard max caracteres copiados precisa ser maior que zero.")

            pesquisas = self.config["pesquisas"]
            pesquisas["desktop_coords"]["x"] = self.parse_int(
                self.desktop_x_var, "Desktop X"
            )
            pesquisas["desktop_coords"]["y"] = self.parse_int(
                self.desktop_y_var, "Desktop Y"
            )
            pesquisas["search_count"] = self.parse_int(
                self.searches_var, "Numero de buscas"
            )
            pesquisas["executar_conjunto_diario"] = self.executar_conjunto_var.get()
            pesquisas["executar_pesquisas"] = self.executar_pesquisas_var.get()
            pesquisas["usar_ctrl_l_desktop"] = self.usar_ctrl_l_desktop_var.get()
            pesquisas["delay_apos_conjunto_diario"] = self.parse_intervalo(
                self.delay_apos_conjunto_min_var,
                self.delay_apos_conjunto_max_var,
                "Pausa após Conjunto diário",
            )
            pesquisas["delay_entre_buscas"] = self.parse_intervalo(
                self.delay_busca_min_var,
                self.delay_busca_max_var,
                "Delay entre buscas",
            )

            palavras_min = self.parse_int(self.palavras_min_var, "Palavras minimo")
            palavras_max = self.parse_int(self.palavras_max_var, "Palavras maximo")
            if palavras_min > palavras_max:
                raise ValueError(
                    "Palavras por busca: o minimo nao pode ser maior que o maximo."
                )
            pesquisas["palavras_por_busca"] = {"min": palavras_min, "max": palavras_max}

            edge_tempo = self.config.setdefault("edge_tempo", {})
            edge_tempo["executar"] = self.executar_edge_tempo_var.get()
            edge_tempo["url_video"] = self.edge_video_url_var.get().strip()
            edge_tempo["primeira_espera_minutos"] = self.parse_float(
                self.edge_primeira_espera_var, "Primeira espera Edge"
            )
            edge_tempo["margem_extra_minutos"] = self.parse_float(
                self.edge_margem_extra_var, "Margem extra Edge"
            )
            edge_tempo["max_tentativas"] = self.parse_int(
                self.edge_max_tentativas_var, "Max verificacoes Edge"
            )
            edge_tempo.setdefault("delay_apos_abrir_video", 8.0)
            edge_tempo.setdefault("delay_apos_reabrir_edge", 2.0)
            if edge_tempo["executar"] and not edge_tempo["url_video"]:
                raise ValueError("Informe a URL do video para o tempo no Edge.")
            if edge_tempo["primeira_espera_minutos"] <= 0:
                raise ValueError("Primeira espera Edge precisa ser maior que zero.")
            if edge_tempo["margem_extra_minutos"] < 0:
                raise ValueError("Margem extra Edge nao pode ser negativa.")
            if edge_tempo["max_tentativas"] <= 0:
                raise ValueError("Max verificacoes Edge precisa ser maior que zero.")

            brotato = self.config.setdefault("brotato", {})
            brotato["executar"] = self.executar_brotato_var.get()
            brotato["app_busca"] = self.brotato_app_busca_var.get().strip() or "Brotato"
            brotato["ignorar_verificacoes"] = self.brotato_ignorar_verificacoes_var.get()
            brotato["tempo_minutos"] = self.parse_float(
                self.brotato_tempo_minutos_var, "Timer Brotato"
            )
            brotato["delay_apos_enter"] = self.parse_float(
                self.brotato_delay_apos_enter_var, "Delay apos abrir Brotato"
            )
            brotato["menu_timeout_segundos"] = self.parse_float(
                self.brotato_menu_timeout_var, "Timeout menu Brotato"
            )
            brotato["fechar_timeout_segundos"] = self.parse_float(
                self.brotato_fechar_timeout_var, "Timeout fechar Brotato"
            )
            if brotato["tempo_minutos"] <= 0:
                raise ValueError("Timer Brotato precisa ser maior que zero.")
            if brotato["delay_apos_enter"] < 0:
                raise ValueError("Delay apos abrir Brotato nao pode ser negativo.")
            if brotato["menu_timeout_segundos"] <= 0:
                raise ValueError("Timeout menu Brotato precisa ser maior que zero.")
            if brotato["fechar_timeout_segundos"] <= 0:
                raise ValueError("Timeout fechar Brotato precisa ser maior que zero.")

            timer_automatico = self.config.setdefault("timer_automatico", {})
            timer_automatico["horas"] = self.parse_int_nao_negativo(
                self.timer_horas_var, "Timer horas"
            )
            timer_automatico["minutos"] = self.parse_int_nao_negativo(
                self.timer_minutos_var, "Timer minutos"
            )
            timer_automatico["segundos"] = self.parse_int_nao_negativo(
                self.timer_segundos_var, "Timer segundos"
            )
            timer_automatico.setdefault("desligar_delay_segundos", 30)

            agendamento = self.config.setdefault("agendamento_automatico", {})
            agendamento["horario"] = self.normalizar_horario_agendamento(
                self.agendamento_horario_var.get()
            )
            agendamento["desligar_ao_finalizar"] = self.agendamento_desligar_var.get()
            agendamento.setdefault("task_name", AUTO_TASK_DEFAULT_NAME)
            agendamento["fluxo"] = {
                "executar_conjunto_diario": self.agendamento_executar_conjunto_var.get(),
                "executar_pesquisas": self.agendamento_executar_pesquisas_var.get(),
                "executar_edge_tempo": self.agendamento_executar_edge_tempo_var.get(),
                "executar_brotato": self.agendamento_executar_brotato_var.get(),
            }
            self.agendamento_horario_var.set(agendamento["horario"])
            self.agendamento_comando_var.set(self.descrever_comando_agendamento())

            self.salvar_json(self.config)
            self.update_status("Configuracoes salvas com sucesso.", "green")
            return True
        except ValueError as exc:
            messagebox.showerror("Erro de valor", str(exc))
            return False
        except OSError as exc:
            messagebox.showerror("Erro ao salvar", f"Nao foi possivel salvar: {exc}")
            return False

    def update_status(self, message, color="blue"):
        def aplicar():
            self.status_var.set(message)
            self.status_label.config(foreground=color)

        self.root.after(0, aplicar)

    def log_execucao(self, message):
        self.exec_logger.escrever(message)

    def status_com_log(self, message, color="blue"):
        self.log_execucao(message)
        self.update_status(message, color)

    def iniciar_run_id(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_id = f"run_{timestamp}_{uuid.uuid4().hex[:8]}"
        self.ultimo_pontos_lidos = None
        self.ultima_leitura_pontos = None
        self.log_execucao(f"RunId da execucao: {self.run_id}")

    def iniciar_resumo_execucao(self):
        self.resumo_execucao = {}
        self.falhas_visuais = []
        self.resetar_sessao_edge()

    def marcar_etapa(self, nome, status, detalhe=""):
        self.resumo_execucao[nome] = {
            "status": status,
            "detalhe": detalhe,
        }

    def capturar_screenshot_falha(self, nome, detalhe=""):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_limpo = "".join(
            caractere.lower() if caractere.isalnum() else "_"
            for caractere in nome
        ).strip("_") or "falha"
        caminho = LOGS_DIR / f"falha_{timestamp}_{nome_limpo}.png"

        try:
            try:
                from PIL import ImageGrab

                imagem = ImageGrab.grab(all_screens=True)
            except Exception:
                imagem = pa.screenshot()

            imagem.save(caminho)
            self.falhas_visuais.append({"nome": nome, "caminho": caminho, "detalhe": detalhe})
            if detalhe:
                self.log_execucao(f"Screenshot de falha salvo: {caminho} ({detalhe})")
            else:
                self.log_execucao(f"Screenshot de falha salvo: {caminho}")
            return caminho
        except Exception as exc:
            self.log_execucao(f"Nao foi possivel salvar screenshot de falha '{nome}': {exc}")
            return None

    def escrever_relatorio_final(self, titulo="Resumo final da execucao"):
        self.log_execucao("=" * 70)
        self.log_execucao(titulo)
        if not self.resumo_execucao:
            self.log_execucao("Nenhuma etapa registrada no resumo.")
        else:
            for nome, info in self.resumo_execucao.items():
                detalhe = info.get("detalhe") or ""
                sufixo = f" - {detalhe}" if detalhe else ""
                self.log_execucao(f"{nome}: {info.get('status', 'indefinido')}{sufixo}")

        self.log_execucao(
            f"Edge aberto pelo app nesta execucao: {self.edge_open_count} vez(es)."
        )
        self.log_execucao(
            f"Reinicios do Edge por recuperacao Rewards: {self.edge_restart_count} vez(es)."
        )
        self.log_execucao(
            "Reinicios do Edge por pesquisas sem credito: "
            f"{self.edge_search_restart_count} vez(es)."
        )

        if self.falhas_visuais:
            self.log_execucao("Screenshots de falha:")
            for item in self.falhas_visuais:
                detalhe = f" - {item['detalhe']}" if item.get("detalhe") else ""
                self.log_execucao(f"{item['nome']}: {item['caminho']}{detalhe}")
        else:
            self.log_execucao("Screenshots de falha: nenhum.")
        self.log_execucao("=" * 70)

    def confirmar_intervencao_mouse(self, evento):
        concluido = threading.Event()
        resposta = {"continuar": False}

        def perguntar():
            esperado = evento["esperado"]
            atual = evento["atual"]
            estado = evento.get("estado") or {}
            scrolls = estado.get("scrolls_concluidos", 0)
            ticks = estado.get("ticks_parciais", 0)
            cards = estado.get("cards_executados", 0)
            recuperacao = "sim" if evento.get("recuperacao") else "nao"

            self.update_status("Automacao pausada: mouse saiu do local esperado.", "orange")
            self.log_execucao(
                "Pausa de seguranca: "
                f"acao={evento['nome']}, esperado=({esperado['x']},{esperado['y']}), "
                f"atual=({atual['x']},{atual['y']}), scrolls={scrolls}, ticks={ticks}, cards={cards}."
            )

            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            continuar = messagebox.askokcancel(
                "Automacao pausada",
                "O mouse saiu da area esperada durante uma etapa critica.\n\n"
                f"Etapa: {evento['nome']}\n"
                f"Esperado: x={esperado['x']}, y={esperado['y']}\n"
                f"Atual: x={atual['x']}, y={atual['y']}\n"
                f"Margem: {evento['margem']} px\n\n"
                f"Scrolls ja concluidos: {scrolls}\n"
                f"Ticks parciais do scroll atual: {ticks}\n"
                f"Cards ja executados: {cards}\n"
                f"Recuperacao automatica disponivel: {recuperacao}\n\n"
                "Clique OK para continuar. Se houver scroll salvo, o app vai tentar "
                "reabrir/restaurar a extensao e voltar para o mesmo ponto.\n"
                "Clique Cancelar para parar a automacao.",
                parent=self.root,
            )
            resposta["continuar"] = continuar
            concluido.set()

        if threading.current_thread() is threading.main_thread():
            perguntar()
        else:
            self.root.after(0, perguntar)
            concluido.wait()

        if resposta["continuar"]:
            self.status_com_log("Usuario escolheu continuar apos pausa de seguranca.", "orange")
            return True

        self.status_com_log("Usuario cancelou apos pausa de seguranca.", "orange")
        self.stop_automation.set()
        self.pause_automation.clear()
        return False

    def set_running(self, running):
        self.automation_running = running
        if not running:
            self.pause_automation.clear()

        def aplicar():
            principal_state = "disabled" if running else "normal"
            cancelando = self.stop_automation.is_set()
            pause_state = (
                "normal"
                if running and not cancelando and not self.pause_automation.is_set()
                else "disabled"
            )
            resume_state = (
                "normal"
                if running and not cancelando and self.pause_automation.is_set()
                else "disabled"
            )
            cancel_state = "normal" if running and not cancelando else "disabled"

            self.start_button.config(state=principal_state)
            self.timer_button.config(state=principal_state)
            self.conjunto_button.config(state=principal_state)
            self.install_schedule_button.config(state=principal_state)
            self.remove_schedule_button.config(state=principal_state)
            self.test_schedule_button.config(state=principal_state)
            self.pause_button.config(state=pause_state)
            self.resume_button.config(state=resume_state)
            self.cancel_button.config(state=cancel_state)

        self.root.after(0, aplicar)

    def atualizar_botoes_pausa(self):
        self.set_running(self.automation_running)

    def trazer_app_para_frente(self):
        self.root.after(
            0,
            lambda: (
                self.root.deiconify(),
                self.root.lift(),
                self.root.focus_force(),
                self.notebook.select(self.exec_tab),
            ),
        )

    def emitir_alerta_cancelamento(self):
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

    def pressionar_esc_interno(self):
        self.ignorar_esc_interno_ate = time.time() + 0.6
        pa.press("esc")

    def pausar_automacao(self):
        if not self.automation_running or self.stop_automation.is_set():
            return

        if self.pause_automation.is_set():
            return

        self.pause_automation.set()
        self.status_com_log("Automacao pausada. Clique em Resumir para continuar.", "orange")
        self.trazer_app_para_frente()
        self.atualizar_botoes_pausa()

    def resumir_automacao(self):
        if not self.automation_running:
            return

        self.pause_automation.clear()
        self.status_com_log("Automacao retomada.", "blue")
        self.atualizar_botoes_pausa()

    def cancelar_automacao(self, mensagem=None):
        if not self.automation_running:
            return

        if self.stop_automation.is_set():
            return

        self.stop_automation.set()
        self.pause_automation.clear()
        self.status_com_log(
            mensagem or "Cancelando automacao... aguardando etapa atual parar.",
            "orange",
        )
        self.atualizar_botoes_pausa()

    def cancelar_automacao_por_esc(self):
        if time.time() < self.ignorar_esc_interno_ate:
            return

        if not self.automation_running or self.stop_automation.is_set():
            return

        if self.timer_automatico_aguardando:
            self.log_execucao("ESC ignorado: timer automatico ainda esta aguardando.")
            return

        self.emitir_alerta_cancelamento()
        self.trazer_app_para_frente()
        self.cancelar_automacao(
            "ESC pressionado. Cancelando automacao... aguardando etapa atual parar."
        )

    def esperar_se_pausado(self):
        if not self.pause_automation.is_set():
            return not self.stop_automation.is_set()

        while self.pause_automation.is_set():
            if self.stop_automation.is_set():
                return False
            time.sleep(0.1)

        return not self.stop_automation.is_set()

    def fluxo_selecionado_existe(self):
        return self.fluxo_tem_alguma_funcao(self.obter_fluxo_manual_config())

    def fluxo_tem_alguma_funcao(self, fluxo):
        return (
            bool(fluxo.get("executar_conjunto_diario", False))
            or bool(fluxo.get("executar_pesquisas", False))
            or bool(fluxo.get("executar_edge_tempo", False))
            or bool(fluxo.get("executar_brotato", False))
        )

    def obter_fluxo_manual_config(self):
        pesquisas = self.config["pesquisas"]
        return {
            "executar_conjunto_diario": bool(
                pesquisas.get("executar_conjunto_diario", False)
            ),
            "executar_pesquisas": bool(pesquisas.get("executar_pesquisas", True)),
            "executar_edge_tempo": bool(
                self.config.get("edge_tempo", {}).get("executar", False)
            ),
            "executar_brotato": bool(
                self.config.get("brotato", {}).get("executar", False)
            ),
        }

    def obter_fluxo_agendamento_config(self):
        agendamento = self.config.get("agendamento_automatico", {})
        fluxo = agendamento.get("fluxo", {})
        padrao = DEFAULT_CONFIG["agendamento_automatico"]["fluxo"]
        return {
            "executar_conjunto_diario": bool(
                fluxo.get(
                    "executar_conjunto_diario",
                    padrao["executar_conjunto_diario"],
                )
            ),
            "executar_pesquisas": bool(
                fluxo.get("executar_pesquisas", padrao["executar_pesquisas"])
            ),
            "executar_edge_tempo": bool(
                fluxo.get("executar_edge_tempo", padrao["executar_edge_tempo"])
            ),
            "executar_brotato": bool(
                fluxo.get("executar_brotato", padrao["executar_brotato"])
            ),
        }

    def aplicar_fluxo_config(self, fluxo):
        pesquisas = self.config.setdefault("pesquisas", {})
        pesquisas["executar_conjunto_diario"] = bool(
            fluxo.get("executar_conjunto_diario", False)
        )
        pesquisas["executar_pesquisas"] = bool(
            fluxo.get("executar_pesquisas", False)
        )
        self.config.setdefault("edge_tempo", {})["executar"] = bool(
            fluxo.get("executar_edge_tempo", False)
        )
        self.config.setdefault("brotato", {})["executar"] = bool(
            fluxo.get("executar_brotato", False)
        )

    def descrever_fluxo_config(self, fluxo):
        nomes = [
            ("executar_conjunto_diario", "Conjunto diario"),
            ("executar_pesquisas", "Pesquisar com o Bing"),
            ("executar_edge_tempo", "Navegar com Edge"),
            ("executar_brotato", "Jogar PC (Brotato)"),
        ]
        ativos = [label for chave, label in nomes if fluxo.get(chave)]
        return ", ".join(ativos) if ativos else "nenhuma funcao selecionada"

    def validar_fluxo_selecionado(self):
        if self.fluxo_selecionado_existe():
            return True

        messagebox.showwarning(
            "Nenhuma funcao selecionada",
            "Selecione pelo menos uma funcao primaria: Conjunto diario, "
            "Pesquisar com o Bing, Navegar com Edge ou Jogar PC (Brotato).",
            parent=self.root,
        )
        return False

    def normalizar_horario_agendamento(self, valor):
        texto = (valor or "").strip()
        try:
            horario = datetime.strptime(texto, "%H:%M")
        except ValueError as exc:
            raise ValueError("Horario do agendamento precisa estar no formato HH:MM, exemplo 06:00.") from exc

        return horario.strftime("%H:%M")

    def task_name_agendamento(self):
        agendamento = self.config.get("agendamento_automatico", {})
        return agendamento.get("task_name") or AUTO_TASK_DEFAULT_NAME

    def comando_agendamento(self, desligar_ao_finalizar=None):
        if desligar_ao_finalizar is None:
            desligar_ao_finalizar = self.agendamento_desligar_var.get()

        args = ["--auto-run", "--scheduled-run"]
        if desligar_ao_finalizar:
            args.append("--shutdown-on-success")

        if getattr(sys, "frozen", False):
            executavel = sys.executable
            argumentos = args
            pasta_trabalho = str(Path(sys.executable).resolve().parent)
        else:
            executavel = sys.executable
            argumentos = [str(BASE_DIR / "app_automacao.py"), *args]
            pasta_trabalho = str(BASE_DIR)

        return executavel, argumentos, pasta_trabalho

    def descrever_comando_agendamento(self):
        executavel, argumentos, pasta_trabalho = self.comando_agendamento()
        comando = subprocess.list2cmdline([executavel, *argumentos])
        return f"{comando}\nPasta: {pasta_trabalho}"

    def powershell_quote(self, valor):
        return "'" + str(valor).replace("'", "''") + "'"

    def executar_powershell_agendamento(self, script):
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            capture_output=True,
            text=True,
            timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def agendamento_instalado(self):
        resultado = subprocess.run(
            ["schtasks", "/Query", "/TN", self.task_name_agendamento()],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return resultado.returncode == 0

    def atualizar_status_agendamento(self):
        try:
            if self.agendamento_instalado():
                self.agendamento_status_var.set(
                    f"Tarefa instalada no Windows: {self.task_name_agendamento()}"
                )
            else:
                self.agendamento_status_var.set(
                    "Nenhum agendamento instalado pelo AI Rewards neste usuario."
                )
        except Exception as exc:
            self.agendamento_status_var.set(f"Nao consegui verificar o agendamento: {exc}")

    def instalar_agendamento_windows(self):
        if not self.save_config():
            return

        horario = self.config["agendamento_automatico"]["horario"]
        task_name = self.task_name_agendamento()
        executavel, argumentos, pasta_trabalho = self.comando_agendamento(
            self.config["agendamento_automatico"].get("desligar_ao_finalizar", True)
        )
        argumentos_texto = subprocess.list2cmdline(argumentos)

        script = f"""
$ErrorActionPreference = 'Stop'
$taskName = {self.powershell_quote(task_name)}
$execute = {self.powershell_quote(executavel)}
$argument = {self.powershell_quote(argumentos_texto)}
$workingDirectory = {self.powershell_quote(pasta_trabalho)}
$at = [datetime]::ParseExact({self.powershell_quote(horario)}, 'HH:mm', [System.Globalization.CultureInfo]::InvariantCulture)
$action = New-ScheduledTaskAction -Execute $execute -Argument $argument -WorkingDirectory $workingDirectory
$trigger = New-ScheduledTaskTrigger -Daily -At $at
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 6)
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'AI Rewards: execucao automatica diaria.' -Force | Out-Null
"""
        try:
            resultado = self.executar_powershell_agendamento(script)
        except Exception as exc:
            messagebox.showerror(
                "Erro no agendamento",
                f"Nao consegui instalar o agendamento: {exc}",
                parent=self.root,
            )
            return

        if resultado.returncode != 0:
            mensagem = (resultado.stderr or resultado.stdout or "").strip()
            messagebox.showerror(
                "Erro no agendamento",
                f"O Windows nao aceitou o agendamento.\n\n{mensagem}",
                parent=self.root,
            )
            self.atualizar_status_agendamento()
            return

        self.update_status("Agendamento instalado/atualizado com sucesso.", "green")
        self.atualizar_status_agendamento()
        messagebox.showinfo(
            "Agendamento instalado",
            "A tarefa diaria foi criada no Windows.\n\n"
            "Para PC suspenso/hibernando, o Windows pode acordar pela tarefa.\n"
            "Para PC desligado real, configure Power On By RTC/Wake By Alarm na BIOS/UEFI.",
            parent=self.root,
        )

    def remover_agendamento_windows(self):
        task_name = self.task_name_agendamento()
        resultado = subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if resultado.returncode != 0 and self.agendamento_instalado():
            mensagem = (resultado.stderr or resultado.stdout or "").strip()
            messagebox.showerror(
                "Erro ao remover",
                f"Nao consegui remover o agendamento.\n\n{mensagem}",
                parent=self.root,
            )
            return

        self.update_status("Agendamento removido.", "green")
        self.atualizar_status_agendamento()

    def testar_execucao_automatica_agendada(self):
        if not self.save_config():
            return

        if self.agendamento_desligar_var.get():
            continuar = messagebox.askokcancel(
                "Teste sem desligamento",
                "O teste vai iniciar o fluxo salvo nesta aba de agendamento, mas nao vai desligar o PC.\n\n"
                "O desligamento automatico fica reservado para a tarefa diaria instalada.",
                parent=self.root,
            )
            if not continuar:
                return

        self.start_auto_run(
            shutdown_on_success=False,
            scheduled_run=True,
            origem="Teste do agendamento",
        )

    def start_fluxo_completo_thread(self):
        if not self.save_config():
            return

        pesquisas = self.config["pesquisas"]
        executar_edge_tempo = self.config.get("edge_tempo", {}).get("executar", False)
        executar_brotato = self.config.get("brotato", {}).get("executar", False)
        if (
            not pesquisas["executar_conjunto_diario"]
            and not pesquisas.get("executar_pesquisas", True)
            and not executar_edge_tempo
            and not executar_brotato
        ):
            messagebox.showwarning(
                "Nenhuma função selecionada",
                "Selecione pelo menos uma função primária: Conjunto diário, Pesquisar com o Bing, Navegar com Edge ou Jogar PC (Brotato).",
                parent=self.root,
            )
            return

        self.exec_logger.iniciar(
            "Fluxo selecionado",
            abrir_cmd=self.config.get("debug", {}).get("abrir_cmd", True),
        )
        self.iniciar_resumo_execucao()
        self.iniciar_run_id()
        limpar_cache_execucao(self.config)
        self.stop_automation.clear()
        self.pause_automation.clear()
        self.stop_automation.pause_event = self.pause_automation
        self.timer_automatico_aguardando = False
        self.set_running(True)
        self.status_com_log("Iniciando fluxo selecionado...")
        thread = threading.Thread(target=self.fluxo_completo, daemon=True)
        thread.start()

    def start_auto_run_from_cli(self):
        self.start_auto_run(
            shutdown_on_success=bool(self.cli_args.shutdown_on_success),
            scheduled_run=bool(self.cli_args.scheduled_run),
            origem="Execucao agendada" if self.cli_args.scheduled_run else "Execucao automatica",
        )

    def start_auto_run(self, shutdown_on_success=False, scheduled_run=False, origem="Execucao automatica"):
        if self.automation_running:
            return

        fluxo = (
            self.obter_fluxo_agendamento_config()
            if scheduled_run
            else self.obter_fluxo_manual_config()
        )
        if not self.fluxo_tem_alguma_funcao(fluxo):
            self.exec_logger.iniciar(
                origem,
                abrir_cmd=self.config.get("debug", {}).get("abrir_cmd", True),
            )
            self.iniciar_resumo_execucao()
            self.iniciar_run_id()
            self.marcar_etapa(origem, "cancelado", "Nenhuma funcao primaria selecionada.")
            self.escrever_relatorio_final()
            self.update_status("Execucao automatica cancelada: nenhuma funcao selecionada.", "orange")
            return

        self.exec_logger.iniciar(
            origem,
            abrir_cmd=self.config.get("debug", {}).get("abrir_cmd", True),
        )
        self.iniciar_resumo_execucao()
        self.iniciar_run_id()
        limpar_cache_execucao(self.config)
        self.stop_automation.clear()
        self.pause_automation.clear()
        self.stop_automation.pause_event = self.pause_automation
        self.timer_automatico_aguardando = False
        self.set_running(True)
        self.status_com_log(
            f"{origem} iniciada. Desligar ao finalizar: {'sim' if shutdown_on_success else 'nao'}."
        )
        if scheduled_run:
            self.status_com_log(
                "Fluxo do agendamento: "
                f"{self.descrever_fluxo_config(fluxo)}."
            )

        thread = threading.Thread(
            target=self.fluxo_auto_run,
            args=(shutdown_on_success, scheduled_run, origem),
            daemon=True,
        )
        thread.start()

    def edge_em_primeiro_plano(self):
        hwnd = obter_janela_ativa()
        if not janela_windows_valida(hwnd):
            return False
        return janela_parece_edge(hwnd, self.config.get("navegador", {}))

    def garantir_edge_primeiro_plano_pos_falha(self):
        if self.edge_em_primeiro_plano():
            titulo = obter_titulo_janela(obter_janela_ativa()) or "janela Edge ativa"
            self.status_com_log(
                f"Falha agendada: Edge ja esta em primeiro plano ({titulo}).",
                "green",
            )
            return True

        hwnd, titulo = encontrar_janela_edge(self.config, preferir_ativa=False)
        if hwnd is not None:
            self.status_com_log(
                f"Falha agendada: Edge encontrado. Vou deixar em primeiro plano: {titulo or 'sem titulo'}.",
                "orange",
            )
            self.edge_session_hwnd = hwnd
            self.edge_session_started = True
            return focar_janela_edge(
                hwnd,
                self.config,
                stop_event=None,
                status_callback=self.status_com_log,
            )

        self.status_com_log(
            "Falha agendada: Edge nao esta aberto. Vou abrir e deixar em primeiro plano.",
            "orange",
        )
        if not abrir_edge(
            self.config,
            stop_event=None,
            status_callback=self.status_com_log,
        ):
            self.status_com_log(
                "Falha agendada: nao consegui abrir o Edge antes do desligamento longo.",
                "red",
            )
            return False

        hwnd, titulo = aguardar_janela_edge(
            self.config,
            timeout=self.config.get("navegador", {}).get("abrir_timeout_segundos", 30),
            stop_event=None,
            status_callback=self.status_com_log,
        )
        if hwnd is None:
            self.status_com_log(
                "Falha agendada: Edge abriu, mas nao consegui confirmar a janela.",
                "red",
            )
            return False

        self.edge_session_hwnd = hwnd
        self.edge_session_started = True
        self.status_com_log(
            f"Falha agendada: Edge confirmado em primeiro plano: {titulo or 'sem titulo'}.",
            "green",
        )
        return focar_janela_edge(
            hwnd,
            self.config,
            stop_event=None,
            status_callback=self.status_com_log,
        )

    def delay_desligamento_falha_agendada(self):
        agendamento = self.config.get("agendamento_automatico", {})
        minutos = agendamento.get("delay_desligar_falha_minutos", 31)
        try:
            minutos = float(minutos)
        except (TypeError, ValueError):
            minutos = 31.0
        return max(60, int(minutos * 60))

    def preparar_desligamento_longo_falha_agendada(self, motivo):
        edge_ok = self.garantir_edge_primeiro_plano_pos_falha()
        delay = self.delay_desligamento_falha_agendada()
        detalhe_edge = (
            "Edge em primeiro plano antes do desligamento longo."
            if edge_ok
            else "Nao consegui garantir Edge em primeiro plano."
        )
        self.marcar_etapa(
            "Agendamento automatico",
            "finalizado",
            f"{motivo} {detalhe_edge}",
        )
        self.desligar_computador(
            delay_segundos=delay,
            motivo=(
                "Execucao agendada falhou. "
                "Mantendo/abrindo Edge e desligando depois da janela de recuperacao."
            ),
            comentario="AI Rewards falhou no agendamento; desligamento apos janela Edge.",
        )

    def fluxo_auto_run(self, shutdown_on_success, scheduled_run, origem):
        desligamento_solicitado = False
        fluxo_manual_original = None
        try:
            if scheduled_run:
                self.marcar_etapa("Agendamento automatico", "em execucao", origem)
                fluxo_manual_original = self.obter_fluxo_manual_config()
                fluxo_agendado = self.obter_fluxo_agendamento_config()
                self.status_com_log(
                    "Aplicando fluxo salvo do agendamento nesta execucao: "
                    f"{self.descrever_fluxo_config(fluxo_agendado)}."
                )
                self.aplicar_fluxo_config(fluxo_agendado)

            concluido = self.fluxo_completo()
            if scheduled_run and shutdown_on_success:
                if concluido:
                    self.marcar_etapa(
                        "Agendamento automatico",
                        "finalizado",
                        "Fluxo agendado concluido.",
                    )
                    self.desligar_computador()
                else:
                    self.preparar_desligamento_longo_falha_agendada(
                        "Fluxo agendado terminou com falha/interrupcao."
                    )
                desligamento_solicitado = True
            elif concluido and shutdown_on_success and not self.stop_automation.is_set():
                self.desligar_computador()
                desligamento_solicitado = True
            elif concluido:
                self.status_com_log("Execucao automatica concluida sem desligamento.", "green")
            else:
                self.marcar_etapa(
                    "Desligamento",
                    "cancelado",
                    "Fluxo automatico nao foi concluido com sucesso.",
                )
                self.status_com_log(
                    "Execucao automatica falhou ou foi interrompida. O computador nao sera desligado.",
                    "orange",
                )
        except Exception as exc:
            self.marcar_etapa("Execucao automatica", "erro", str(exc))
            self.capturar_screenshot_falha("execucao_automatica", str(exc))
            self.status_com_log(f"Erro na execucao automatica: {exc}", "red")
            if scheduled_run and shutdown_on_success and not desligamento_solicitado:
                self.preparar_desligamento_longo_falha_agendada(
                    "Erro na execucao agendada."
                )
                desligamento_solicitado = True
        finally:
            if scheduled_run and fluxo_manual_original is not None:
                self.aplicar_fluxo_config(fluxo_manual_original)
                self.log_execucao("Fluxo manual restaurado apos execucao agendada.")

    def total_segundos_timer_automatico(self):
        timer_automatico = self.config.get("timer_automatico", {})
        horas = int(timer_automatico.get("horas", 0))
        minutos = int(timer_automatico.get("minutos", 0))
        segundos = int(timer_automatico.get("segundos", 0))
        return horas * 3600 + minutos * 60 + segundos

    def formatar_duracao(self, total_segundos):
        total_segundos = max(0, int(total_segundos))
        horas, resto = divmod(total_segundos, 3600)
        minutos, segundos = divmod(resto, 60)
        partes = []
        if horas:
            partes.append(f"{horas}h")
        if minutos:
            partes.append(f"{minutos}min")
        if segundos or not partes:
            partes.append(f"{segundos}s")
        return " ".join(partes)

    def start_timer_automatico_thread(self):
        if not self.save_config():
            return

        if not self.validar_fluxo_selecionado():
            return

        total_segundos = self.total_segundos_timer_automatico()
        if total_segundos <= 0:
            messagebox.showwarning(
                "Timer invalido",
                "Configure um tempo maior que zero para iniciar o modo timer.",
                parent=self.root,
            )
            return

        self.exec_logger.iniciar(
            "Modo timer",
            abrir_cmd=self.config.get("debug", {}).get("abrir_cmd", True),
        )
        self.iniciar_resumo_execucao()
        self.iniciar_run_id()
        self.marcar_etapa("Timer automatico", "aguardando", self.formatar_duracao(total_segundos))
        limpar_cache_execucao(self.config)
        self.stop_automation.clear()
        self.pause_automation.clear()
        self.stop_automation.pause_event = self.pause_automation
        self.timer_automatico_aguardando = True
        self.set_running(True)
        self.status_com_log(
            f"Timer iniciado. Aguardando {self.formatar_duracao(total_segundos)}."
        )
        thread = threading.Thread(
            target=self.fluxo_timer_automatico,
            args=(total_segundos,),
            daemon=True,
        )
        thread.start()

    def start_conjunto_thread(self):
        if not self.save_config():
            return

        self.exec_logger.iniciar(
            "Conjunto diário",
            abrir_cmd=self.config.get("debug", {}).get("abrir_cmd", True),
        )
        self.iniciar_resumo_execucao()
        self.iniciar_run_id()
        self.marcar_etapa("Conjunto diario", "pendente")
        limpar_cache_execucao(self.config)
        self.stop_automation.clear()
        self.pause_automation.clear()
        self.stop_automation.pause_event = self.pause_automation
        self.timer_automatico_aguardando = False
        self.set_running(True)
        self.status_com_log("Iniciando somente o Conjunto diário...")
        thread = threading.Thread(target=self.fluxo_conjunto_diario, daemon=True)
        thread.start()

    def fluxo_conjunto_diario(self):
        try:
            self.log_execucao("Preparando automação do Conjunto diário.")
            self.marcar_etapa("Conjunto diario", "em execucao")
            pa.FAILSAFE = True
            pa.PAUSE = 0.05
            coordenadas = carregar_coordenadas(self.config)
            self.log_execucao(f"Coordenadas carregadas: {coordenadas}")
            leitura_conjunto_before = self.registrar_pontos_etapa(
                "conjunto_diario",
                "before",
                "ok",
                "Leitura antes do Conjunto diario.",
            )
            if not self.garantir_sessao_edge():
                self.marcar_etapa("Conjunto diario", "falhou", "Nao conseguiu preparar a sessao unica do Edge.")
                self.capturar_screenshot_falha("conjunto_diario_edge", "Falha na sessao unica do Edge.")
                self.status_com_log("Automacao interrompida ao preparar Edge.", "orange")
                return
            if self.abrir_painel_rewards_sessao(tentativas=2) is None:
                self.marcar_etapa("Conjunto diario", "falhou", "Nao conseguiu abrir/validar o Rewards.")
                self.capturar_screenshot_falha("conjunto_diario_rewards", "Popup Rewards nao ficou em estado valido.")
                self.status_com_log("Automacao interrompida: Rewards nao ficou utilizavel.", "red")
                return

            concluido = executar_fluxo_inicial(
                self.config,
                coordenadas=coordenadas,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
                safety_callback=self.confirmar_intervencao_mouse,
                edge_ja_aberto=True,
                painel_ja_aberto=True,
            )

            if concluido:
                self.marcar_etapa("Conjunto diario", "ok")
                self.registrar_pontos_etapa(
                    "conjunto_diario",
                    "after",
                    "ok",
                    "Conjunto diario concluido.",
                    abrir_edge_primeiro=False,
                )
                self.status_com_log("Conjunto diário concluído.", "green")
            else:
                self.marcar_etapa("Conjunto diario", "falhou/interrompido")
                self.capturar_screenshot_falha("conjunto_diario", "Fluxo inicial retornou falha.")
                self.registrar_pontos_etapa(
                    "conjunto_diario",
                    "after",
                    "falhou",
                    "Conjunto diario falhou/interrompido.",
                    abrir_edge_primeiro=False,
                )
                self.status_com_log("Automacao interrompida.", "orange")
        except SystemExit as exc:
            self.marcar_etapa("Conjunto diario", "falhou", str(exc))
            self.capturar_screenshot_falha("conjunto_diario_erro", str(exc))
            self.registrar_pontos_etapa(
                "conjunto_diario",
                "after",
                "falhou",
                str(exc),
                abrir_edge_primeiro=False,
            )
            self.status_com_log(str(exc), "red")
        except Exception as exc:
            self.marcar_etapa("Conjunto diario", "erro", str(exc))
            self.capturar_screenshot_falha("conjunto_diario_excecao", str(exc))
            self.registrar_pontos_etapa(
                "conjunto_diario",
                "after",
                "falhou",
                str(exc),
                abrir_edge_primeiro=False,
            )
            self.status_com_log(f"Erro no Conjunto diário: {exc}", "red")
        finally:
            self.escrever_relatorio_final()
            self.log_execucao("Finalizando thread do Conjunto diário.")
            self.set_running(False)

    def fluxo_timer_automatico(self, total_segundos):
        fluxo_iniciado = False
        try:
            if not self.sleep_segundos_com_log(total_segundos, "Timer automatico"):
                self.marcar_etapa("Timer automatico", "cancelado")
                self.status_com_log("Timer cancelado pelo usuario.", "orange")
                return

            self.timer_automatico_aguardando = False
            self.marcar_etapa("Timer automatico", "ok")
            self.status_com_log("Timer concluido. Iniciando fluxo selecionado...")
            fluxo_iniciado = True
            concluido = self.fluxo_completo()
            if concluido and not self.stop_automation.is_set():
                self.desligar_computador()
            else:
                self.marcar_etapa("Desligamento", "cancelado", "Fluxo nao foi concluido.")
                self.status_com_log(
                    "Fluxo nao foi concluido com sucesso. O computador nao sera desligado.",
                    "orange",
                )
        except Exception as exc:
            self.marcar_etapa("Timer automatico", "erro", str(exc))
            self.capturar_screenshot_falha("timer_automatico", str(exc))
            self.status_com_log(f"Erro no modo timer: {exc}", "red")
        finally:
            self.timer_automatico_aguardando = False
            if not fluxo_iniciado:
                self.escrever_relatorio_final()
                self.log_execucao("Finalizando thread do modo timer.")
                self.set_running(False)

    def desligar_computador(self, delay_segundos=None, motivo=None, comentario=None):
        if delay_segundos is None:
            delay = int(
                self.config.get("timer_automatico", {}).get("desligar_delay_segundos", 30)
            )
        else:
            delay = int(delay_segundos)
        delay = max(0, delay)
        motivo = motivo or "Fluxo concluido."
        comentario = comentario or "AI Rewards concluiu o fluxo selecionado."
        self.status_com_log(
            f"{motivo} Desligando o computador em {delay} segundo(s).",
            "green",
        )
        self.marcar_etapa("Desligamento", "agendado", f"{delay}s")
        self.escrever_relatorio_final("Resumo final da execucao com desligamento")
        subprocess.Popen(
            [
                "shutdown",
                "/s",
                "/t",
                str(delay),
                "/c",
                comentario,
            ],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def fluxo_completo(self):
        try:
            self.log_execucao("Preparando automacao completa.")
            pa.FAILSAFE = True
            pa.PAUSE = 0.25
            executar_conjunto = self.config["pesquisas"]["executar_conjunto_diario"]
            executar_pesquisas = self.config["pesquisas"].get("executar_pesquisas", True)
            executar_edge_tempo = self.config.get("edge_tempo", {}).get("executar", False)
            executar_brotato = self.config.get("brotato", {}).get("executar", False)
            edge_aberto = False
            houve_falha_parcial = False
            self.brotato_aberto = False

            if executar_conjunto:
                self.marcar_etapa("Conjunto diario", "pendente")
            if executar_pesquisas:
                self.marcar_etapa("Pesquisar com o Bing", "pendente")
            if executar_brotato:
                self.marcar_etapa("Jogar PC (Brotato)", "pendente")
            if executar_edge_tempo:
                self.marcar_etapa("Navegar com Edge", "pendente")

            if executar_conjunto:
                leitura_conjunto_before = self.registrar_pontos_etapa(
                    "conjunto_diario",
                    "before",
                    "ok",
                    "Leitura antes do Conjunto diario.",
                )
                if leitura_conjunto_before and leitura_conjunto_before.get("pontos") is not None:
                    edge_aberto = True

                self.marcar_etapa("Conjunto diario", "em execucao")
                coordenadas = carregar_coordenadas(self.config)
                self.log_execucao(f"Coordenadas carregadas: {coordenadas}")
                if not self.garantir_sessao_edge():
                    self.marcar_etapa("Conjunto diario", "falhou", "Nao conseguiu preparar a sessao unica do Edge.")
                    self.capturar_screenshot_falha("conjunto_diario_edge", "Falha na sessao unica do Edge.")
                    self.status_com_log("Automacao interrompida ao preparar Edge.", "orange")
                    return False
                edge_aberto = True
                if self.abrir_painel_rewards_sessao(tentativas=2) is None:
                    self.marcar_etapa("Conjunto diario", "falhou", "Nao conseguiu abrir/validar o Rewards.")
                    self.capturar_screenshot_falha("conjunto_diario_rewards", "Popup Rewards nao ficou em estado valido.")
                    self.status_com_log("Automacao interrompida: Rewards nao ficou utilizavel.", "red")
                    return False
                concluido = executar_fluxo_inicial(
                    self.config,
                    coordenadas=coordenadas,
                    stop_event=self.stop_automation,
                    status_callback=self.status_com_log,
                    safety_callback=self.confirmar_intervencao_mouse,
                    edge_ja_aberto=True,
                    painel_ja_aberto=True,
                )

                if not concluido:
                    self.marcar_etapa("Conjunto diario", "falhou/interrompido")
                    self.capturar_screenshot_falha("conjunto_diario", "Fluxo inicial retornou falha.")
                    self.registrar_pontos_etapa(
                        "conjunto_diario",
                        "after",
                        "falhou",
                        "Conjunto diario falhou/interrompido.",
                        abrir_edge_primeiro=False,
                    )
                    if self.stop_automation.is_set():
                        self.status_com_log("Automacao interrompida.", "orange")
                        return False

                    houve_falha_parcial = True
                    self.status_com_log(
                        "Conjunto diario falhou, mas vou continuar o fluxo para nao perder as outras etapas.",
                        "orange",
                    )
                    self.pressionar_esc_interno()
                else:
                    self.marcar_etapa("Conjunto diario", "ok")
                    self.registrar_pontos_etapa(
                        "conjunto_diario",
                        "after",
                        "ok",
                        "Conjunto diario concluido.",
                        abrir_edge_primeiro=False,
                    )

                edge_aberto = True
                if executar_pesquisas:
                    if houve_falha_parcial:
                        self.status_com_log("Seguindo para Pesquisar com o Bing...")
                    else:
                        self.status_com_log("Conjunto diário concluído. Iniciando Pesquisar com o Bing...")
                    if not self.sleep_intervalo(
                        self.config["pesquisas"]["delay_apos_conjunto_diario"]
                    ):
                        self.marcar_etapa("Pesquisar com o Bing", "cancelado", "Interrompido antes de iniciar.")
                        self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                        return False
                elif not houve_falha_parcial:
                    self.status_com_log("Conjunto diário concluído. Pesquisar com o Bing desativado.", "green")

            if executar_pesquisas:
                leitura_pesquisas_before = self.registrar_pontos_etapa(
                    "pesquisar_bing",
                    "before",
                    "ok",
                    "Leitura antes de Pesquisar com o Bing.",
                    reutilizar_ultima_leitura=executar_conjunto,
                )
                if leitura_pesquisas_before and leitura_pesquisas_before.get("pontos") is not None:
                    edge_aberto = True

                self.marcar_etapa("Pesquisar com o Bing", "em execucao")
                if not self.garantir_sessao_edge():
                    self.marcar_etapa("Pesquisar com o Bing", "falhou", "Nao conseguiu preparar a sessao unica do Edge.")
                    self.capturar_screenshot_falha("pesquisar_com_bing_edge", "Falha na sessao unica do Edge.")
                    self.status_com_log("Automacao interrompida ao preparar Edge.", "orange")
                    return False
                edge_aberto = True
                consultas_pesquisas_usadas = set()
                if not self.automation_search_logic(consultas_usadas=consultas_pesquisas_usadas):
                    self.marcar_etapa("Pesquisar com o Bing", "falhou/interrompido")
                    self.capturar_screenshot_falha("pesquisar_com_bing", "Fluxo de pesquisas retornou falha.")
                    self.registrar_pontos_etapa(
                        "pesquisar_bing",
                        "after",
                        "falhou",
                        "Pesquisar com o Bing falhou/interrompido.",
                    )
                    return False

                pesquisas_config = self.config.get("pesquisas", {})
                validar_credito = bool(pesquisas_config.get("validar_credito_pontos", True))
                leitura_pesquisas_after = None
                pontos_pesquisas_before = self.extrair_pontos_leitura(leitura_pesquisas_before)
                pontos_pesquisas_after = None

                if validar_credito and self.dashboard_ativo():
                    leitura_pesquisas_after = self.ler_pontos_rewards_para_validacao(
                        "apos Pesquisar com o Bing"
                    )
                    pontos_pesquisas_after = self.extrair_pontos_leitura(leitura_pesquisas_after)

                    deve_recuperar_pesquisas = (
                        pontos_pesquisas_before is not None
                        and (
                            pontos_pesquisas_after is None
                            or pontos_pesquisas_after <= pontos_pesquisas_before
                        )
                        and bool(pesquisas_config.get("retry_sem_credito", True))
                    )
                    if deve_recuperar_pesquisas:
                        retry_count = max(0, int(pesquisas_config.get("retry_search_count", 8)))
                        max_retentativas = max(
                            0,
                            int(pesquisas_config.get("max_retentativas_sem_credito", 3)),
                        )
                        delay_retry = max(
                            0.0,
                            float(pesquisas_config.get("delay_apos_retry_sem_credito", 6.0)),
                        )

                        for tentativa_retry in range(1, max_retentativas + 1):
                            if retry_count <= 0:
                                break

                            self.status_com_log(
                                "Pesquisar com o Bing nao confirmou aumento de pontos. "
                                "Vou fechar e reabrir o Edge antes de tentar novamente "
                                f"({tentativa_retry}/{max_retentativas}).",
                                "orange",
                            )
                            if not self.reiniciar_edge_para_retry_pesquisas(max_retentativas):
                                self.status_com_log(
                                    "Nao consegui reiniciar o Edge para recuperar as pesquisas.",
                                    "red",
                                )
                                break

                            if delay_retry and not self.sleep_interruptivel(delay_retry):
                                self.marcar_etapa(
                                    "Pesquisar com o Bing",
                                    "cancelado",
                                    "Interrompido antes do retry sem credito.",
                                )
                                return False

                            if not self.automation_search_logic(
                                total_buscas=retry_count,
                                rotulo=(
                                    "Retry Pesquisar com o Bing "
                                    f"{tentativa_retry}/{max_retentativas}"
                                ),
                                consultas_usadas=consultas_pesquisas_usadas,
                            ):
                                self.marcar_etapa("Pesquisar com o Bing", "falhou/interrompido")
                                self.capturar_screenshot_falha(
                                    "pesquisar_com_bing_retry",
                                    "Retry de pesquisas retornou falha.",
                                )
                                self.registrar_pontos_etapa(
                                    "pesquisar_bing",
                                    "after",
                                    "falhou",
                                    "Pesquisar com o Bing falhou durante retry sem credito.",
                                )
                                return False

                            leitura_pesquisas_after = self.ler_pontos_rewards_para_validacao(
                                "apos retry de Pesquisar com o Bing "
                                f"{tentativa_retry}/{max_retentativas}"
                            )
                            pontos_pesquisas_after = self.extrair_pontos_leitura(
                                leitura_pesquisas_after
                            )
                            if (
                                pontos_pesquisas_after is not None
                                and pontos_pesquisas_after > pontos_pesquisas_before
                            ):
                                self.status_com_log(
                                    "Credito das pesquisas confirmado apos reiniciar o Edge.",
                                    "green",
                                )
                                break

                            self.status_com_log(
                                "Retry concluido, mas os pontos ainda nao aumentaram.",
                                "orange",
                            )

                    if pontos_pesquisas_after is None:
                        self.marcar_etapa(
                            "Pesquisar com o Bing",
                            "falhou",
                            "Nao conseguiu validar pontos apos pesquisas.",
                        )
                        self.registrar_pontos_etapa(
                            "pesquisar_bing",
                            "after",
                            "falhou",
                            "Nao conseguiu validar pontos apos Pesquisar com o Bing.",
                            leitura_pre_lida=leitura_pesquisas_after,
                        )
                        self.status_com_log(
                            "Nao consegui validar o credito das pesquisas. "
                            "Vou continuar o fluxo para nao perder as outras etapas.",
                            "orange",
                        )
                    elif (
                        pontos_pesquisas_before is not None
                        and pontos_pesquisas_after <= pontos_pesquisas_before
                    ):
                        delta_pesquisas = pontos_pesquisas_after - pontos_pesquisas_before
                        self.capturar_screenshot_falha(
                            "pesquisar_com_bing_sem_credito",
                            "Pontos nao aumentaram apos esgotar os reinicios do Edge.",
                        )
                        self.marcar_etapa(
                            "Pesquisar com o Bing",
                            "falhou",
                            f"Sem ganho de pontos nas pesquisas (delta {delta_pesquisas}).",
                        )
                        self.registrar_pontos_etapa(
                            "pesquisar_bing",
                            "after",
                            "falhou",
                            "Pesquisar com o Bing nao gerou aumento de pontos apos retry.",
                            leitura_pre_lida=leitura_pesquisas_after,
                        )
                        self.status_com_log(
                            "Pesquisar com o Bing terminou sem credito no Rewards. "
                            "Marquei a etapa como falha e vou continuar o restante do fluxo.",
                            "orange",
                        )
                    else:
                        ganho_pesquisas = (
                            pontos_pesquisas_after - pontos_pesquisas_before
                            if pontos_pesquisas_before is not None
                            else None
                        )
                        detalhe_ganho = (
                            f" Ganhou {ganho_pesquisas} ponto(s)."
                            if ganho_pesquisas is not None
                            else ""
                        )
                        self.marcar_etapa("Pesquisar com o Bing", "ok", detalhe_ganho.strip() or None)
                        self.registrar_pontos_etapa(
                            "pesquisar_bing",
                            "after",
                            "ok",
                            f"Pesquisar com o Bing concluido.{detalhe_ganho}",
                            leitura_pre_lida=leitura_pesquisas_after,
                        )
                else:
                    self.marcar_etapa("Pesquisar com o Bing", "ok")
                    self.registrar_pontos_etapa(
                        "pesquisar_bing",
                        "after",
                        "ok",
                        "Pesquisar com o Bing concluido.",
                    )
                edge_aberto = True

            if executar_brotato and executar_edge_tempo:
                if not self.executar_brotato_logic(com_timer=False):
                    self.marcar_etapa("Jogar PC (Brotato)", "falhou/interrompido")
                    self.capturar_screenshot_falha("brotato", "Falha ao abrir Brotato para rodar junto com Edge.")
                    return False
                edge_aberto = self.sessao_edge_valida()

            if executar_edge_tempo:
                leitura_edge_before = self.registrar_pontos_etapa(
                    "navegar_edge",
                    "before",
                    "ok",
                    "Leitura antes de Navegar com Edge.",
                    reutilizar_ultima_leitura=bool(executar_conjunto or executar_pesquisas),
                )
                if leitura_edge_before and leitura_edge_before.get("pontos") is not None:
                    edge_aberto = True

                self.marcar_etapa("Navegar com Edge", "em execucao")
                if not self.executar_tempo_edge_logic(
                    edge_ja_aberto=edge_aberto,
                    fechar_brotato_antes_verificar=executar_brotato,
                ):
                    self.marcar_etapa("Navegar com Edge", "falhou/interrompido")
                    self.capturar_screenshot_falha("navegar_com_edge", "Fluxo de tempo no Edge retornou falha.")
                    self.registrar_pontos_etapa(
                        "navegar_edge",
                        "after",
                        "falhou",
                        "Navegar com Edge falhou/interrompido.",
                    )
                    return False
                self.marcar_etapa("Navegar com Edge", "ok")
                self.registrar_pontos_etapa(
                    "navegar_edge",
                    "after",
                    "ok",
                    "Navegar com Edge concluido.",
                )
            elif executar_brotato:
                if not self.executar_brotato_logic(com_timer=True):
                    self.marcar_etapa("Jogar PC (Brotato)", "falhou/interrompido")
                    self.capturar_screenshot_falha("brotato", "Fluxo do Brotato retornou falha.")
                    return False

            if not executar_conjunto and not executar_pesquisas and not executar_edge_tempo and not executar_brotato:
                self.status_com_log("Nenhuma funcao primaria selecionada.", "orange")
                return False

            if houve_falha_parcial:
                self.status_com_log(
                    "Fluxo terminou, mas o Conjunto diario falhou. Veja o resumo final.",
                    "orange",
                )
                return False

            self.status_com_log("Fluxo selecionado concluido.", "green")
            return True
        except SystemExit as exc:
            self.capturar_screenshot_falha("erro_automacao", str(exc))
            self.status_com_log(str(exc), "red")
            return False
        except Exception as exc:
            self.capturar_screenshot_falha("erro_automacao", str(exc))
            self.status_com_log(f"Erro na automacao: {exc}", "red")
            return False
        finally:
            self.escrever_relatorio_final()
            self.log_execucao("Finalizando thread do fluxo completo.")
            self.set_running(False)

    def extrair_pontos_leitura(self, leitura):
        if not isinstance(leitura, dict):
            return None
        pontos = leitura.get("pontos")
        if pontos is None and isinstance(leitura.get("leitura"), dict):
            pontos = leitura["leitura"].get("pontos")
        try:
            return int(pontos)
        except (TypeError, ValueError):
            return None

    def ler_pontos_rewards_para_validacao(self, contexto):
        if not self.dashboard_ativo():
            return None

        self.status_com_log(f"Dashboard: validando pontos {contexto}.")
        leitura = self.copiar_pontos_rewards_clipboard(
            abrir_edge_primeiro=True,
            fechar_painel=True,
        )
        if not leitura.get("ok"):
            self.status_com_log(
                f"Dashboard: nao consegui validar pontos {contexto} ({leitura.get('erro')}).",
                "orange",
            )
        return leitura

    def automation_search_logic(self, total_buscas=None, rotulo="Pesquisar com o Bing", consultas_usadas=None):
        pesquisas = self.config["pesquisas"]
        num_searches = int(total_buscas if total_buscas is not None else pesquisas["search_count"])
        delay_buscas = pesquisas["delay_entre_buscas"]
        consultas_usadas = consultas_usadas if consultas_usadas is not None else set()
        self.log_execucao(f"Iniciando {rotulo}: {num_searches} busca(s).")

        for i in range(1, num_searches + 1):
            if not self.esperar_se_pausado():
                self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                break

            self.status_com_log(f"Busca {i} de {num_searches}...", "blue")

            words = self.get_random_words(consultas_usadas)
            if not words:
                self.status_com_log("Erro ao buscar palavras. Tentando novamente...", "red")
                self.sleep_interruptivel(2)
                continue

            sentence = " ".join(words)
            consultas_usadas.add(sentence.strip().lower())
            self.log_execucao(f"Texto da busca {i}: {sentence}")

            self.focar_barra_busca(pesquisas)
            if not self.esperar_se_pausado():
                self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                break

            self.log_execucao("Limpando barra de busca com Ctrl+A e Delete.")
            pa.hotkey("ctrl", "a")
            pa.press("delete")
            self.log_execucao("Digitando busca letra por letra.")
            self.write_text_letter_by_letter(sentence)

            if not self.esperar_se_pausado():
                self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                break

            self.log_execucao("Pressionando Enter para pesquisar.")
            if not self.esperar_se_pausado():
                self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                break
            pa.press("enter")

            delay = random.uniform(delay_buscas["min"], delay_buscas["max"])
            self.log_execucao(f"Aguardando {delay:.2f}s ate a proxima busca.")
            if not self.sleep_interruptivel(delay):
                self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                return False
        else:
            self.status_com_log("Pesquisar com o Bing concluído.", "green")
            return True

        return False

    def focar_barra_busca(self, pesquisas):
        if not self.esperar_se_pausado():
            return

        if not self.config.get("automacao", {}).get("usar_versao_fixa", True):
            self.log_execucao("Nova versao ativa: focando barra do Edge com Ctrl+L.")
            pa.hotkey("ctrl", "l")
        elif pesquisas["usar_ctrl_l_desktop"]:
            self.log_execucao("Focando barra do Edge com Ctrl+L.")
            pa.hotkey("ctrl", "l")
        else:
            self.log_execucao(
                "Focando barra desktop por coordenada: "
                f"x={pesquisas['desktop_coords']['x']}, y={pesquisas['desktop_coords']['y']}"
            )
            clicar_mouse(pesquisas["desktop_coords"]["x"], pesquisas["desktop_coords"]["y"])

        self.sleep_interruptivel(0.5)

    def abrir_brotato(self):
        brotato = self.config.get("brotato", {})
        app_busca = brotato.get("app_busca", "Brotato").strip() or "Brotato"
        delay = float(brotato.get("delay_apos_enter", 10))

        if not self.esperar_se_pausado():
            return False

        self.status_com_log(f"Abrindo Brotato pelo menu iniciar: {app_busca}")
        pa.press("win")
        if not self.sleep_interruptivel(0.5):
            return False
        pa.write(app_busca, interval=0.03)
        if not self.sleep_interruptivel(0.2):
            return False
        pa.press("enter")
        self.log_execucao(f"Aguardando Brotato iniciar por {delay:.1f}s.")
        return self.sleep_interruptivel(delay)

    def jogo_ignora_verificacoes_visuais(self):
        return bool(self.config.get("brotato", {}).get("ignorar_verificacoes", False))

    def termos_janela_jogo(self):
        app_busca = self.config.get("brotato", {}).get("app_busca", "Brotato").strip() or "Brotato"
        termos = [app_busca]
        app_normalizado = app_busca.lower()
        substituicoes = (
            " for windows",
            " para windows",
            " windows",
        )
        base = app_busca
        for trecho in substituicoes:
            base = base.replace(trecho, "").replace(trecho.title(), "")
        base = base.strip()
        if base and base.lower() not in {termo.lower() for termo in termos}:
            termos.append(base)
        if "minecraft" in app_normalizado and "minecraft" not in {termo.lower() for termo in termos}:
            termos.append("Minecraft")
        if "brotato" in app_normalizado and "brotato" not in {termo.lower() for termo in termos}:
            termos.append("Brotato")
        return termos

    def focar_jogo_por_janela(self):
        termos = self.termos_janela_jogo()
        titulo = focar_janela_por_titulo(termos, ignorar_edge_config=self.config)
        if titulo:
            self.status_com_log(f"Jogo focado pela janela aberta: {titulo}", "green")
            return self.sleep_interruptivel(0.7)

        self.log_execucao(
            "Nao encontrei a janela do jogo pelo titulo: " + ", ".join(termos)
        )
        return False

    def voltar_para_edge_apos_abrir_jogo(self):
        if not getattr(self, "edge_session_hwnd", None):
            self.log_execucao(
                "Sem sessao Edge ativa para retornar apos abrir o jogo; o proximo passo abrira/focara Edge se precisar."
            )
            return True

        self.status_com_log("Voltando para a sessao Edge depois de abrir o jogo...")
        if self.garantir_sessao_edge():
            return self.sleep_interruptivel(0.5)

        self.status_com_log(
            "Nao consegui voltar para o Edge apos abrir o jogo. Vou continuar e deixar a proxima etapa recuperar.",
            "orange",
        )
        return True

    def aguardar_brotato_menu(self):
        brotato = self.config.get("brotato", {})
        timeout = float(brotato.get("menu_timeout_segundos", 120))
        if not listar_templates_alvo_visual(self.config, "brotato_gamertag"):
            self.status_com_log(
                "Nenhum template treinado para Brotato Gamer Tag. Treine esse alvo antes de executar.",
                "red",
            )
            return False

        restante = timeout
        tentativa = 0
        while restante > 0:
            if not self.esperar_se_pausado():
                return False

            tentativa += 1
            self.status_com_log(
                f"Procurando Gamer Tag do Brotato ({restante:.0f}s restantes)..."
            )
            inicio = time.time()
            alvo = localizar_alvo_visual(
                self.config,
                "brotato_gamertag",
                status_callback=self.status_com_log if tentativa == 1 else None,
                stop_event=self.stop_automation,
            )
            if alvo is not None:
                self.status_com_log(
                    f"Brotato no menu detectado: x={alvo['x']}, y={alvo['y']}, score={alvo['score']:.2f}.",
                    "green",
                )
                self.brotato_aberto = True
                return self.minimizar_brotato_pela_barra()

            restante -= time.time() - inicio
            pausa = min(2.0, restante)
            if pausa > 0 and not self.sleep_interruptivel(pausa):
                return False
            restante -= pausa

        self.status_com_log(
            "Nao consegui detectar o menu do Brotato dentro do timeout.",
            "red",
        )
        return False

    def minimizar_brotato_pela_barra(self):
        if not listar_templates_alvo_visual(self.config, "brotato_icone_barra"):
            self.status_com_log(
                "Nenhum template treinado para o icone do Brotato na barra. Treine esse alvo antes de minimizar o jogo.",
                "red",
            )
            return False

        self.status_com_log("Minimizando Brotato pelo icone da barra de tarefas...")
        if clicar_alvo_visual(
            self.config,
            "brotato_icone_barra",
            stop_event=self.stop_automation,
            status_callback=self.status_com_log,
            safety_callback=self.confirmar_intervencao_mouse,
        ):
            return self.sleep_interruptivel(1.0)

        self.status_com_log("Nao consegui minimizar o Brotato pelo icone da barra.", "red")
        return False

    def focar_brotato_pela_barra(self):
        brotato = self.config.get("brotato", {})
        timeout = float(brotato.get("fechar_timeout_segundos", 20))

        if self.focar_jogo_por_janela():
            return True

        self.log_execucao(
            "Nao encontrei uma janela do Brotato pelo titulo. Tentando pelo icone da barra."
        )
        if not listar_templates_alvo_visual(self.config, "brotato_icone_barra"):
            self.status_com_log(
                "Nenhum template treinado para o icone do Brotato na barra. Treine esse alvo antes de fechar o jogo.",
                "red",
            )
            return False

        restante = timeout
        while restante > 0:
            if not self.esperar_se_pausado():
                return False

            inicio = time.time()
            self.status_com_log("Procurando icone do Brotato na barra de tarefas...")
            if clicar_alvo_visual(
                self.config,
                "brotato_icone_barra",
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
                safety_callback=self.confirmar_intervencao_mouse,
            ):
                return self.sleep_interruptivel(1.0)

            restante -= time.time() - inicio
            pausa = min(1.0, restante)
            if pausa > 0 and not self.sleep_interruptivel(pausa):
                return False
            restante -= pausa

        self.status_com_log("Nao consegui focar o Brotato pelo icone da barra.", "red")
        return False

    def fechar_brotato(self):
        if not self.brotato_aberto:
            self.log_execucao("Brotato nao esta marcado como aberto. Nada para fechar.")
            return True

        self.status_com_log("Fechando Brotato com Alt+F4...")
        if self.jogo_ignora_verificacoes_visuais():
            if not self.focar_jogo_por_janela():
                self.status_com_log(
                    "Modo sem verificacoes: nao achei a janela do jogo para fechar. Vou seguir sem bloquear o fluxo.",
                    "orange",
                )
                self.brotato_aberto = False
                return True
        elif not self.focar_brotato_pela_barra():
            return False
        if not self.esperar_se_pausado():
            return False
        pa.hotkey("alt", "f4")
        if not self.sleep_interruptivel(2.0):
            return False
        self.brotato_aberto = False
        self.status_com_log("Brotato fechado.", "green")
        return True

    def garantir_brotato_fechado(self):
        if not self.brotato_aberto:
            return True

        self.status_com_log("Brotato aberto antes da verificacao. Vou fechar primeiro.")
        return self.fechar_brotato()

    def executar_brotato_logic(self, com_timer=True):
        self.marcar_etapa("Jogar PC (Brotato)", "em execucao")
        if not self.abrir_brotato():
            self.marcar_etapa("Jogar PC (Brotato)", "falhou", "Nao abriu o jogo.")
            self.capturar_screenshot_falha("brotato_abrir", "Falha ao abrir Brotato.")
            return False
        self.brotato_aberto = True

        if self.jogo_ignora_verificacoes_visuais():
            self.status_com_log(
                "Modo sem templates visuais ativo: confirmando a janela real do jogo.",
                "green",
            )
            if not self.focar_jogo_por_janela():
                self.marcar_etapa(
                    "Jogar PC (Brotato)",
                    "falhou",
                    "O comando foi enviado, mas nenhuma janela do jogo foi encontrada.",
                )
                self.capturar_screenshot_falha(
                    "brotato_janela",
                    "O jogo nao abriu ou sua janela nao foi confirmada.",
                )
                self.brotato_aberto = False
                return False
            self.voltar_para_edge_apos_abrir_jogo()
        elif not self.aguardar_brotato_menu():
            self.marcar_etapa("Jogar PC (Brotato)", "falhou", "Menu/Gamer Tag nao detectado.")
            self.capturar_screenshot_falha("brotato_menu", "Nao detectou Gamer Tag/Menu.")
            return False

        if not com_timer:
            self.marcar_etapa(
                "Jogar PC (Brotato)",
                "em execucao",
                "Janela confirmada; aberto em background junto com Edge.",
            )
            self.status_com_log("Brotato aberto para rodar junto com Navegar com Edge.")
            return True

        minutos = float(self.config.get("brotato", {}).get("tempo_minutos", 17))
        self.status_com_log(f"Brotato ficara aberto por {minutos:.1f} minuto(s).")
        if not self.sleep_minutos_com_log(minutos, "Timer Brotato"):
            self.marcar_etapa("Jogar PC (Brotato)", "cancelado", "Timer interrompido.")
            self.status_com_log("Automacao interrompida durante timer do Brotato.", "orange")
            return False

        if not self.fechar_brotato():
            self.marcar_etapa("Jogar PC (Brotato)", "falhou", "Nao conseguiu fechar o jogo.")
            self.capturar_screenshot_falha("brotato_fechar", "Falha ao fechar Brotato.")
            return False

        self.marcar_etapa("Jogar PC (Brotato)", "ok", f"Timer de {minutos:.1f} min concluido.")
        return True

    def executar_tempo_edge_logic(self, edge_ja_aberto=False, fechar_brotato_antes_verificar=False):
        edge_tempo = self.config.get("edge_tempo", {})
        url_video = edge_tempo.get("url_video", "").strip()
        if not url_video:
            self.marcar_etapa("Navegar com Edge", "falhou", "URL do video vazia.")
            self.status_com_log("Navegar com Edge ativado, mas a URL do vídeo está vazia.", "red")
            return False

        primeira_espera = float(edge_tempo.get("primeira_espera_minutos", 36))
        margem_extra = float(edge_tempo.get("margem_extra_minutos", 1))
        max_tentativas = int(edge_tempo.get("max_tentativas", 3))
        espera_atual = primeira_espera

        if not self.garantir_sessao_edge():
            self.marcar_etapa("Navegar com Edge", "falhou", "Nao conseguiu preparar a sessao unica do Edge.")
            self.capturar_screenshot_falha("edge_tempo_abrir", "Falha na sessao unica do Edge.")
            self.status_com_log("Automacao interrompida ao preparar Edge.", "orange")
            return False

        for tentativa in range(1, max_tentativas + 1):
            self.status_com_log(
                f"Navegar com Edge: tentativa {tentativa}/{max_tentativas}. "
                f"Video ficara aberto por {espera_atual:.1f} minuto(s)."
            )
            if not self.abrir_video_no_edge(url_video):
                self.marcar_etapa("Navegar com Edge", "falhou", "Nao abriu o video.")
                self.capturar_screenshot_falha("edge_tempo_video", "Falha ao abrir video no Edge.")
                return False

            if not self.sleep_minutos_com_log(
                espera_atual,
                f"Aguardando tempo no Edge ({tentativa}/{max_tentativas})",
            ):
                self.status_com_log("Automacao interrompida durante espera do Edge.", "orange")
                return False

            if fechar_brotato_antes_verificar:
                if not self.garantir_brotato_fechado():
                    return False
                self.marcar_etapa(
                    "Jogar PC (Brotato)",
                    "ok",
                    f"Janela confirmada e mantida aberta por {espera_atual:.1f} min.",
                )
                self.status_com_log("Refocando Edge antes de verificar o Rewards...")
                if not self.garantir_sessao_edge():
                    self.capturar_screenshot_falha("edge_refocar_verificacao", "Falha ao refocar a sessao unica do Edge.")
                    return False

            tracker = self.atualizar_painel_rewards_e_verificar_tracker()
            if tracker is None:
                self.marcar_etapa("Navegar com Edge", "falhou", "Nao verificou tracker do Rewards.")
                self.status_com_log(
                    "Nao consegui verificar o tempo do Edge. Treine os estados do tracker e tente novamente.",
                    "red",
                )
                return False

            if tracker["completo"]:
                self.marcar_etapa(
                    "Navegar com Edge",
                    "ok",
                    f"{tracker['minutos']}/{tracker['total']} min.",
                )
                self.status_com_log(
                    f"Task Navegar com Edge completa: {tracker['minutos']}/{tracker['total']} min.",
                    "green",
                )
                return True

            faltam = int(tracker["faltam"])
            if tentativa >= max_tentativas:
                self.marcar_etapa(
                    "Navegar com Edge",
                    "incompleto",
                    f"Faltam {faltam} min; limite de verificacoes atingido.",
                )
                self.status_com_log(
                    f"Navegar com Edge ainda incompleto: faltam {faltam} min e o limite de verificações foi atingido.",
                    "orange",
                )
                return False

            espera_atual = max(1.0, faltam + margem_extra)
            self.status_com_log(
                f"Navegar com Edge incompleto: {tracker['minutos']}/{tracker['total']} min. "
                f"Nova espera: {espera_atual:.1f} minuto(s).",
                "orange",
            )

        return False

    def abrir_video_no_edge(self, url_video):
        if not self.esperar_se_pausado():
            return False

        if not self.garantir_sessao_edge():
            return False

        self.pressionar_esc_interno()
        if not self.sleep_interruptivel(0.3):
            return False

        self.status_com_log(f"Abrindo video no Edge: {url_video}")
        pa.hotkey("ctrl", "l")
        if not self.sleep_interruptivel(0.4):
            return False
        self.inserir_texto(url_video)
        pa.press("enter")

        delay = float(self.config.get("edge_tempo", {}).get("delay_apos_abrir_video", 8.0))
        self.log_execucao(f"Aguardando video carregar por {delay:.1f}s.")
        return self.sleep_interruptivel(delay)

    def inserir_texto(self, texto):
        try:
            import pyperclip

            pyperclip.copy(texto)
            pa.hotkey("ctrl", "v")
        except Exception:
            pa.write(texto, interval=0.01)

    def atualizar_painel_rewards_e_verificar_tracker(self):
        limpar_cache_execucao(self.config)
        self.status_com_log("Cache visual limpo antes de atualizar o painel Rewards.")

        if not self.garantir_sessao_edge():
            self.capturar_screenshot_falha("edge_refocar_verificacao", "Nao conseguiu refocar a sessao unica do Edge.")
            return None

        delay = float(self.config.get("edge_tempo", {}).get("delay_apos_reabrir_edge", 2.0))
        if not self.sleep_interruptivel(delay):
            return None

        coordenadas = carregar_coordenadas(self.config)
        max_tentativas = 2
        for tentativa in range(1, max_tentativas + 1):
            if not self.esperar_se_pausado():
                return None

            self.status_com_log(
                f"Abrindo painel Rewards para checar progresso "
                f"(tentativa {tentativa}/{max_tentativas})..."
            )
            anchor = self.abrir_painel_rewards_sessao(tentativas=2)
            if anchor is None:
                self.capturar_screenshot_falha(
                    f"rewards_extensao_tentativa_{tentativa}",
                    "Nao conseguiu abrir/validar popup Rewards.",
                )
                if tentativa >= max_tentativas:
                    break
                continue

            tracker = abrir_ver_tudo_e_detectar_tracker_edge(
                self.config,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
                safety_callback=self.confirmar_intervencao_mouse,
            )
            if tracker is not None:
                return tracker

            self.capturar_screenshot_falha(
                f"ver_tudo_tracker_tentativa_{tentativa}",
                "Nao conseguiu achar Ver tudo ou detectar o tracker Edge.",
            )
            if tentativa >= max_tentativas:
                break

            self.status_com_log(
                "Nao consegui verificar nessa tentativa. Fechando apenas o painel Rewards e tentando de novo.",
                "orange",
            )
            self.pressionar_esc_interno()
            limpar_cache_execucao(self.config)
            if not self.sleep_interruptivel(1.0):
                return None

        self.status_com_log(
            "Popup Rewards nao entregou o tracker. Tentando fallback pela pagina completa do Rewards.",
            "orange",
        )
        return self.detectar_tracker_pagina_rewards_completa()

    def detectar_tracker_pagina_rewards_completa(self):
        if not self.garantir_sessao_edge():
            return None

        url = self.config.get("rewards_estado", {}).get("url_rewards", "https://rewards.bing.com/")
        self.status_com_log(f"Abrindo pagina completa do Rewards para fallback: {url}")
        self.pressionar_esc_interno()
        if not self.sleep_interruptivel(0.3):
            return None
        pa.hotkey("ctrl", "l")
        if not self.sleep_interruptivel(0.3):
            return None
        self.inserir_texto(url)
        pa.press("enter")

        delay = float(self.config.get("rewards_estado", {}).get("delay_apos_reiniciar_edge", 4.0))
        self.status_com_log(f"Aguardando pagina Rewards carregar por {delay:.1f}s.")
        if not self.sleep_interruptivel(delay):
            return None

        limpar_cache_execucao(self.config)
        estado = self.detectar_estado_rewards()
        if estado.get("estado") not in {
            "pagina_rewards_completa",
            "popup_rewards_ok",
            "popup_rewards_ok_sem_exibir_painel",
            "edge_normal",
        }:
            self.status_com_log(
                f"Fallback Rewards em estado inesperado: {estado.get('estado')}.",
                "orange",
            )

        tracker = detectar_estado_tracker_edge(
            self.config,
            status_callback=self.status_com_log,
            stop_event=self.stop_automation,
            usar_regiao_painel=False,
        )
        if tracker is not None:
            self.status_com_log("Tracker Edge identificado pelo fallback da pagina Rewards.", "green")
            return tracker

        self.capturar_screenshot_falha(
            "tracker_rewards_pagina_completa",
            "Fallback pela pagina completa do Rewards nao encontrou o tracker.",
        )
        return None

    def sleep_minutos_com_log(self, minutos, label):
        return self.sleep_segundos_com_log(float(minutos) * 60, label)

    def sleep_segundos_com_log(self, segundos, label):
        restante = max(0.0, float(segundos))
        proximo_log = 0.0

        while restante > 0:
            if not self.esperar_se_pausado():
                return False

            if proximo_log <= 0:
                self.status_com_log(
                    f"{label}: faltam {self.formatar_duracao(round(restante))}."
                )
                proximo_log = 60.0

            pausa = min(1.0, restante)
            inicio = time.time()
            time.sleep(pausa)
            decorrido = time.time() - inicio
            restante -= decorrido
            proximo_log -= decorrido

        return True

    def gerar_consulta_local(self, consultas_usadas=None):
        consultas_usadas = consultas_usadas or set()
        consultas = list(PALAVRAS_FALLBACK)
        random.shuffle(consultas)

        for consulta in consultas:
            consulta = " ".join(str(consulta).strip().split())
            if consulta and consulta.lower() not in consultas_usadas:
                self.log_execucao(f"Consulta local escolhida: {consulta}")
                return consulta

        consulta = f"{random.choice(PALAVRAS_FALLBACK)} {random.randint(2026, 2099)}"
        consulta = " ".join(str(consulta).strip().split())
        self.log_execucao(f"Consultas locais esgotadas. Usando variacao: {consulta}")
        return consulta

    def get_random_words(self, consultas_usadas=None):
        intervalo = self.config["pesquisas"]["palavras_por_busca"]
        number_of_words = random.randint(intervalo["min"], intervalo["max"])
        url = f"https://random-word-api.vercel.app/api?words={number_of_words}"
        consultas_usadas = consultas_usadas or set()

        try:
            self.log_execucao(f"Buscando {number_of_words} palavra(s) na API.")
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            words = response.json()
            if isinstance(words, list) and words:
                words = [str(word).strip() for word in words if str(word).strip()]
                consulta_api = " ".join(words).strip().lower()
                if words and consulta_api not in consultas_usadas:
                    self.log_execucao(f"Palavras recebidas da API: {words}")
                    return words
                self.log_execucao("API retornou consulta repetida/vazia. Usando fallback local.")
        except requests.exceptions.RequestException:
            self.log_execucao("API de palavras falhou. Usando palavras locais.")

        consulta_local = self.gerar_consulta_local(consultas_usadas)
        return [consulta_local] if consulta_local else []

    def write_text_letter_by_letter(self, text):
        for letter in text:
            if not self.esperar_se_pausado():
                break

            pa.write(letter)
            self.sleep_interruptivel(random.uniform(0.01, 0.03))

    def sleep_interruptivel(self, segundos):
        restante = float(segundos)
        while restante > 0:
            if not self.esperar_se_pausado():
                return False

            pausa = min(0.1, restante)
            inicio = time.time()
            time.sleep(pausa)
            restante -= time.time() - inicio
        return True

    def sleep_intervalo(self, intervalo):
        segundos = random.uniform(intervalo["min"], intervalo["max"])
        return self.sleep_interruptivel(segundos)

    def on_press(self, key):
        if key == keyboard.Key.esc:
            self.cancelar_automacao_por_esc()

    def start_keyboard_listener(self):
        listener = keyboard.Listener(on_press=self.on_press)
        listener.daemon = True
        listener.start()


def parse_cli_args():
    parser = argparse.ArgumentParser(description="AI Rewards Automacao")
    parser.add_argument(
        "--auto-run",
        action="store_true",
        help="Inicia automaticamente o fluxo selecionado salvo no config.json.",
    )
    parser.add_argument(
        "--shutdown-on-success",
        action="store_true",
        help=(
            "Desliga o computador ao fim da execucao automatica. "
            "No modo agendado, desliga mesmo se o fluxo falhar."
        ),
    )
    parser.add_argument(
        "--scheduled-run",
        action="store_true",
        help="Marca a execucao como originada pelo Agendador do Windows.",
    )
    parser.add_argument(
        "--minimized",
        action="store_true",
        help="Inicia com a janela principal escondida.",
    )
    parser.add_argument(
        "--hide-ui",
        action="store_true",
        help="Alias de --minimized para execucoes automaticas.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_cli_args()
    root = tk.Tk()
    app = AutoRewardsApp(root, args)
    root.mainloop()
