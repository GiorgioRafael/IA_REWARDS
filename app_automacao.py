import copy
import ctypes
import json
import random
import subprocess
import threading
import time


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
from pathlib import Path
from tkinter import messagebox, ttk

import pyautogui as pa
import requests
from pynput import keyboard

from automacao_edge import (
    abrir_edge,
    abrir_extensao_rewards,
    abrir_ver_tudo_e_detectar_tracker_edge,
    carregar_coordenadas,
    detectar_estado_tracker_edge,
    executar_fluxo_inicial,
    clicar_alvo_visual,
    limpar_cache_execucao,
    localizar_alvo_visual,
    listar_templates_tracker_estado,
    listar_templates_alvo_visual,
    listar_templates_plus_5,
    listar_templates_plus_10,
)
from deteccao_imagem import (
    capturar_template_em_coordenada,
    clicar_mouse,
    get_mouse_position,
    get_mouse_position_debug,
    localizar_templates,
    mover_mouse,
)


BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"
LOGS_DIR = BASE_DIR / "logs"

DEFAULT_CONFIG = {
    "app_busca": "EDGE",
    "automacao": {
        "usar_versao_fixa": True,
    },
    "tempos": {
        "apos_windows": 0.5,
        "apos_digitar_app": 0.2,
        "apos_enter": 4.0,
        "movimento_mouse": 0.2,
        "entre_acoes": 1.0,
        "apos_icone_extensao": {"min": 2.0, "max": 5.0},
        "apos_double_click_scroll": {"min": 1.0, "max": 3.0},
        "apos_card_1": {"min": 1.0, "max": 5.0},
        "apos_card_2": {"min": 2.0, "max": 5.0},
        "apos_voltar_card_2": {"min": 2.0, "max": 5.0},
        "apos_card_3": {"min": 2.0, "max": 5.0},
        "apos_card_detectado": {"min": 2.0, "max": 5.0},
        "apos_voltar_card_detectado": {"min": 2.0, "max": 5.0},
    },
    "coordenadas": {
        "icone_extensao": {"x": -636, "y": 54},
        "double_click_scroll": {"x": -406, "y": 578},
        "card_1": {"x": None, "y": None},
        "card_2": {"x": None, "y": None},
        "card_3": {"x": None, "y": None},
        "voltar": {"x": -1894, "y": 54},
    },
    "deteccao_imagem": {
        "ativada": True,
        "usar_fallback_coordenadas": True,
        "template_plus_10": "assets/plus_10.png",
        "template_plus_5": "assets/plus_5.png",
        "usar_plus_10": True,
        "usar_plus_5": True,
        "usar_treinamento": True,
        "treino_dir": "assets/treino_plus_10",
        "treino_dir_plus_5": "assets/treino_plus_5",
        "confianca": 0.85,
        "score_forte": 0.95,
        "validar_sinal_mais": True,
        "max_cards": 3,
        "max_scrolls": 40,
        "scroll_amount": -2,
        "detectar_fim_scroll": True,
        "detectar_painel_automatico": True,
        "usar_painel_para_scroll": True,
        "usar_painel_para_deteccao": True,
        "usar_scrollbar_por_cor": True,
        "scrollbar_color": "#767676",
        "scrollbar_tolerance": 28,
        "scrollbar_min_height": 35,
        "scrollbar_min_delta": 2,
        "scrollbar_end_margin": 12,
        "scroll_end_threshold": 1.0,
        "scroll_end_width": 700,
        "scroll_end_height": 850,
        "scroll_end_x_offset": -620,
        "scroll_end_y_offset": -360,
        "scroll_end_region": {"x": None, "y": None, "width": None, "height": None},
        "capture_offset_x": 0,
        "capture_offset_y": 0,
        "click_offset_x": 0,
        "click_offset_y": 0,
        "regiao": {"x": None, "y": None, "width": None, "height": None},
    },
    "seguranca_mouse": {
        "ativada": True,
        "margem_pixels": 35,
        "reabrir_extensao_ao_continuar": True,
    },
    "debug": {
        "abrir_cmd": True,
    },
    "edge_tracker": {
        "treino_dir": "assets/treino_edge_tracker_estados",
        "estados_minutos": [0, 5, 10, 15, 20, 25, 30],
        "total_minutos": 30,
        "confianca": 0.82,
        "capture_width": 130,
        "capture_height": 42,
    },
    "alvos_visuais": {
        "icone_extensao": {
            "template": "assets/alvos/icone_extensao.png",
            "treino_dir": "assets/treino_icone_extensao",
            "confianca": 0.82,
            "score_forte": 0.95,
            "capture_width": 70,
            "capture_height": 50,
            "click_offset_x": 0,
            "click_offset_y": 0,
            "regiao": {"x": None, "y": None, "width": None, "height": None},
        },
        "voltar": {
            "template": "assets/alvos/voltar.png",
            "treino_dir": "assets/treino_voltar",
            "confianca": 0.82,
            "score_forte": 0.95,
            "capture_width": 70,
            "capture_height": 50,
            "click_offset_x": 0,
            "click_offset_y": 0,
            "regiao": {"x": None, "y": None, "width": None, "height": None},
        },
        "ver_tudo": {
            "template": "assets/alvos/ver_tudo.png",
            "treino_dir": "assets/treino_ver_tudo",
            "confianca": 0.82,
            "score_forte": 0.95,
            "capture_width": 190,
            "capture_height": 55,
            "click_offset_x": 0,
            "click_offset_y": 0,
            "regiao": {"x": None, "y": None, "width": None, "height": None},
        },
        "exibir_painel": {
            "template": "assets/alvos/exibir_painel.png",
            "treino_dir": "assets/treino_exibir_painel",
            "confianca": 0.82,
            "score_forte": 0.95,
            "capture_width": 160,
            "capture_height": 42,
            "click_offset_x": 0,
            "click_offset_y": 70,
            "regiao": {"x": None, "y": None, "width": None, "height": None},
        },
        "tracker_edge_tempo": {
            "template": "assets/alvos/tracker_edge_tempo.png",
            "treino_dir": "assets/treino_tracker_edge_tempo",
            "confianca": 0.78,
            "score_forte": 0.92,
            "capture_width": 280,
            "capture_height": 70,
            "click_offset_x": 0,
            "click_offset_y": 0,
            "regiao": {"x": None, "y": None, "width": None, "height": None},
        },
        "brotato_gamertag": {
            "template": "assets/alvos/brotato_gamertag.png",
            "treino_dir": "assets/treino_brotato_gamertag",
            "confianca": 0.82,
            "score_forte": 0.95,
            "capture_width": 80,
            "capture_height": 32,
            "click_offset_x": 0,
            "click_offset_y": 0,
            "regiao": {"x": None, "y": None, "width": None, "height": None},
        },
        "brotato_icone_barra": {
            "template": "assets/alvos/brotato_icone_barra.png",
            "treino_dir": "assets/treino_brotato_icone_barra",
            "confianca": 0.82,
            "score_forte": 0.95,
            "capture_width": 70,
            "capture_height": 60,
            "click_offset_x": 0,
            "click_offset_y": 0,
            "regiao": {"x": None, "y": None, "width": None, "height": None},
        },
    },
    "pesquisas": {
        "desktop_coords": {"x": -1397, "y": 122},
        "search_count": 30,
        "executar_conjunto_diario": True,
        "executar_pesquisas": True,
        "usar_ctrl_l_desktop": True,
        "delay_apos_conjunto_diario": {"min": 2.0, "max": 5.0},
        "delay_entre_buscas": {"min": 5.0, "max": 8.0},
        "palavras_por_busca": {"min": 1, "max": 3},
    },
    "edge_tempo": {
        "executar": False,
        "url_video": "https://www.youtube.com/watch?v=jfKfPfyJRdk",
        "primeira_espera_minutos": 36,
        "margem_extra_minutos": 1,
        "max_tentativas": 3,
        "delay_apos_abrir_video": 8.0,
        "delay_apos_reabrir_edge": 2.0,
    },
    "brotato": {
        "executar": False,
        "app_busca": "Brotato",
        "tempo_minutos": 17,
        "delay_apos_enter": 10,
        "menu_timeout_segundos": 120,
        "fechar_timeout_segundos": 20,
    },
}

VISUAL_TARGET_LABELS = {
    "icone_extensao": "Icone da extensao",
    "voltar": "Botao voltar",
    "ver_tudo": "Botao Ver tudo",
    "exibir_painel": "Texto Exibir painel",
    "tracker_edge_tempo": "Navegar com Edge / tempo",
    "brotato_gamertag": "Brotato Gamer Tag",
    "brotato_icone_barra": "Brotato icone na barra",
}

COORD_LABELS = {
    "icone_extensao": "Icone extensao",
    "double_click_scroll": "Double click scroll",
    "card_1": "Card 1",
    "card_2": "Card 2",
    "card_3": "Card 3",
    "voltar": "Voltar",
}

TEMPO_INTERVALO_LABELS = {
    "apos_icone_extensao": "Apos icone extensao",
    "apos_double_click_scroll": "Apos double click scroll",
    "apos_card_1": "Apos card 1",
    "apos_card_2": "Apos card 2",
    "apos_voltar_card_2": "Apos voltar card 2",
    "apos_card_3": "Apos card 3",
    "apos_card_detectado": "Apos card detectado",
    "apos_voltar_card_detectado": "Apos voltar detectado",
}

PALAVRAS_FALLBACK = [
    "python",
    "weather",
    "music",
    "notebook",
    "recipe",
    "travel",
    "history",
    "science",
    "movie",
    "coffee",
    "garden",
    "finance",
    "sports",
    "language",
    "technology",
    "health",
    "books",
    "space",
    "maps",
    "calendar",
]


class ExecucaoLogger:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.log_path = None
        self.cmd_path = None
        self.lock = threading.Lock()

    def iniciar(self, titulo, abrir_cmd=True):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        agora = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = LOGS_DIR / f"execucao_{agora}.log"
        self.cmd_path = LOGS_DIR / f"abrir_log_{agora}.cmd"

        self.escrever("=" * 70)
        self.escrever(f"{titulo} iniciado")
        self.escrever(f"Arquivo de log: {self.log_path}")
        self.escrever("=" * 70)
        if abrir_cmd:
            self.abrir_janela_cmd()

    def abrir_janela_cmd(self):
        if self.log_path is None or self.cmd_path is None:
            return

        conteudo = (
            "@echo off\n"
            "title AI Rewards - Log em tempo real\n"
            "color 0A\n"
            f'echo Monitorando: "{self.log_path}"\n'
            "echo.\n"
            "powershell -NoProfile -ExecutionPolicy Bypass "
            f'-Command "Get-Content -LiteralPath \'{self.log_path}\' -Wait"\n'
        )
        self.cmd_path.write_text(conteudo, encoding="utf-8")
        subprocess.Popen(
            ["cmd.exe", "/k", str(self.cmd_path)],
            cwd=str(self.base_dir),
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    def escrever(self, mensagem):
        if self.log_path is None:
            return

        linha = f"[{datetime.now().strftime('%H:%M:%S')}] {mensagem}"
        with self.lock:
            with self.log_path.open("a", encoding="utf-8") as arquivo:
                arquivo.write(linha + "\n")


def mesclar_config(default, atual):
    config = copy.deepcopy(default)

    def mesclar(destino, origem):
        for chave, valor in origem.items():
            if (
                chave in destino
                and isinstance(destino[chave], dict)
                and isinstance(valor, dict)
            ):
                mesclar(destino[chave], valor)
            elif chave in destino:
                destino[chave] = valor

    mesclar(config, atual)
    return config


def migrar_config_antiga(config):
    if "pesquisas" not in config:
        config["pesquisas"] = {}

    for chave in ("desktop_coords", "search_count"):
        if chave in config:
            config["pesquisas"][chave] = config[chave]

    if "skip_browser_open" in config:
        config["pesquisas"]["executar_conjunto_diario"] = not config["skip_browser_open"]

    return config


class AutoRewardsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Rewards Automacao")
        self.root.geometry("760x520")
        self.root.resizable(False, False)

        self.stop_automation = threading.Event()
        self.pause_automation = threading.Event()
        self.stop_automation.pause_event = self.pause_automation
        self.automation_running = False
        self.brotato_aberto = False
        self.config = self.carregar_config()
        self.coord_vars = {}
        self.tempo_intervalo_vars = {}
        self.exec_logger = ExecucaoLogger(BASE_DIR)

        self.setup_ui()
        self.start_keyboard_listener()

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
        self.config_tab = ttk.Frame(self.notebook, padding="10")
        self.treino_tab = ttk.Frame(self.notebook, padding="10")

        self.notebook.add(self.exec_tab, text="Execucao")
        self.notebook.add(self.config_tab, text="Configuracoes")
        self.notebook.add(self.treino_tab, text="Treinos e testes")

        self.config_notebook = ttk.Notebook(self.config_tab)
        self.config_notebook.pack(fill="both", expand=True)

        search_container, self.search_tab = self.criar_aba_rolavel(self.config_notebook)
        edge_container, self.edge_tempo_tab = self.criar_aba_rolavel(self.config_notebook)
        brotato_container, self.brotato_tab = self.criar_aba_rolavel(self.config_notebook)
        deteccao_container, self.deteccao_tab = self.criar_aba_rolavel(self.config_notebook)
        advanced_container, self.advanced_tab = self.criar_aba_rolavel(self.config_notebook)

        self.config_notebook.add(search_container, text="Pesquisas")
        self.config_notebook.add(edge_container, text="Tempo Edge")
        self.config_notebook.add(brotato_container, text="Brotato")
        self.config_notebook.add(deteccao_container, text="Deteccao de imagem")
        self.config_notebook.add(advanced_container, text="Avancado")

        self.treino_notebook = ttk.Notebook(self.treino_tab)
        self.treino_notebook.pack(fill="both", expand=True)

        visual_container, self.visual_train_tab = self.criar_aba_rolavel(self.treino_notebook)
        bonus_container, self.bonus_train_tab = self.criar_aba_rolavel(self.treino_notebook)
        tracker_container, self.tracker_train_tab = self.criar_aba_rolavel(self.treino_notebook)

        self.treino_notebook.add(visual_container, text="Alvos visuais")
        self.treino_notebook.add(bonus_container, text="Bonus +10/+5")
        self.treino_notebook.add(tracker_container, text="Tempo Edge")

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
            text="Pressione ESC para pausar. Use Resumir ou Cancelar na aba Execucao.",
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

        fluxo_frame = ttk.LabelFrame(
            self.exec_tab, text="O que executar", padding="10"
        )
        fluxo_frame.pack(fill="x", pady=(0, 10))

        ttk.Checkbutton(
            fluxo_frame,
            text="Conjunto diario",
            variable=self.executar_conjunto_var,
        ).grid(row=0, column=0, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            fluxo_frame,
            text="Pesquisas",
            variable=self.executar_pesquisas_var,
        ).grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            fluxo_frame,
            text="Tempo no Edge",
            variable=self.executar_edge_tempo_var,
        ).grid(row=0, column=2, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            fluxo_frame,
            text="Brotato / Game Pass",
            variable=self.executar_brotato_var,
        ).grid(row=1, column=0, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            fluxo_frame,
            text="Mostrar CMD de debug em tempo real",
            variable=self.abrir_cmd_debug_var,
        ).grid(row=1, column=1, columnspan=2, sticky="w", padx=5, pady=5)

        pesquisas_frame = ttk.LabelFrame(
            self.search_tab, text="Pesquisas > Configuracao", padding="10"
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

        ttk.Label(pesquisas_frame, text="Pausa apos conjunto diario:").grid(
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
            self.edge_tempo_tab, text="Tempo Edge > Video e verificacao", padding="10"
        )
        edge_tempo_frame.pack(fill="x", pady=10)
        edge_tempo_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            edge_tempo_frame,
            text="Executar tempo no Edge depois das etapas selecionadas",
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
            self.brotato_tab, text="Brotato > Xbox Game Pass", padding="10"
        )
        brotato_frame.pack(fill="x", pady=10)
        brotato_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            brotato_frame,
            text="Executar Brotato / Game Pass",
            variable=self.executar_brotato_var,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Label(brotato_frame, text="Buscar app:").grid(
            row=1, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_app_busca_var).grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=5
        )

        ttk.Label(brotato_frame, text="Timer sem Edge (min):").grid(
            row=2, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_tempo_minutos_var, width=8).grid(
            row=2, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(brotato_frame, text="Delay apos abrir (seg):").grid(
            row=3, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_delay_apos_enter_var, width=8).grid(
            row=3, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Label(brotato_frame, text="Timeout menu (seg):").grid(
            row=4, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_menu_timeout_var, width=8).grid(
            row=4, column=1, sticky="w", padx=5, pady=5
        )
        ttk.Label(brotato_frame, text="Timeout fechar (seg):").grid(
            row=4, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(brotato_frame, textvariable=self.brotato_fechar_timeout_var, width=8).grid(
            row=4, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(
            brotato_frame,
            text=(
                "Com Tempo no Edge ativo, o jogo abre antes da espera do Edge e fecha "
                "antes da verificacao do Rewards. O timer de 17 minutos e usado apenas sem Edge."
            ),
            foreground="gray",
            wraplength=620,
        ).grid(row=5, column=0, columnspan=4, sticky="w", padx=5, pady=(8, 3))

        coords_frame = ttk.LabelFrame(
            self.search_tab, text="Pesquisas > Barra de busca", padding="10"
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

        self.start_button = ttk.Button(
            self.exec_action_frame,
            text="Iniciar fluxo selecionado",
            command=self.start_fluxo_completo_thread,
        )
        self.start_button.grid(row=0, column=0, padx=5, sticky="ew")

        ttk.Button(
            self.exec_action_frame,
            text="Salvar configuracoes",
            command=self.save_config,
        ).grid(row=0, column=2, padx=5, sticky="ew")

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

        modo_frame = ttk.LabelFrame(
            self.deteccao_tab, text="Deteccao de imagem > Modo", padding="10"
        )
        modo_frame.pack(fill="x", pady=10)

        ttk.Label(
            modo_frame,
            text="Escolha um modo para executar o conjunto diario:",
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
            text="Rodar so conjunto diario",
            command=self.start_conjunto_thread,
        )
        self.conjunto_button.grid(row=0, column=1, padx=5, sticky="ew")

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
                    deteccao = self.config["deteccao_imagem"]
                    captura_x = mouse_x + int(deteccao["capture_offset_x"])
                    captura_y = mouse_y + int(deteccao["capture_offset_y"])
                    alvo_config = self.config.get("alvos_visuais", {}).get(nome, {})
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
        resultado = {"nome": nome, "erro": None, "detectados": [], "total_templates": 0}

        try:
            templates = listar_templates_alvo_visual(self.config, nome)
            resultado["total_templates"] = len(templates)
            if not templates:
                raise FileNotFoundError(f"Nenhum template treinado para {nome}.")

            alvo_config = self.config.get("alvos_visuais", {}).get(nome, {})
            resultado["detectados"] = localizar_templates(
                templates,
                confianca=float(alvo_config.get("confianca", 0.82)),
                regiao=alvo_config.get("regiao"),
                max_resultados=10,
                parar_score=alvo_config.get("score_forte", 0.95),
            )
        except FileNotFoundError:
            resultado["erro"] = (
                "Template nao encontrado",
                "Use Iniciar treino para salvar pelo menos uma amostra desse alvo.",
            )
        except Exception as exc:
            resultado["erro"] = ("Erro", f"Nao foi possivel testar a deteccao: {exc}")

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
                    deteccao = self.config["deteccao_imagem"]
                    tracker = self.config.get("edge_tracker", {})
                    captura_x = mouse_x + int(deteccao["capture_offset_x"])
                    captura_y = mouse_y + int(deteccao["capture_offset_y"])
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
                detectados = localizar_templates(
                    templates,
                    confianca=self.config["deteccao_imagem"]["confianca"],
                    regiao=self.config["deteccao_imagem"].get("regiao"),
                    max_resultados=20,
                    parar_score=self.config["deteccao_imagem"].get("score_forte", 0.95),
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
            deteccao = self.config["deteccao_imagem"]
            templates = listar_templates_plus_10(self.config)
            total_templates = len(templates)
            if not templates:
                raise FileNotFoundError("Nenhum template +10 encontrado.")

            resultados = localizar_templates(
                templates,
                confianca=deteccao["confianca"],
                regiao=deteccao.get("regiao"),
                max_resultados=20,
                parar_score=deteccao.get("score_forte", 0.95),
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
            deteccao = self.config["deteccao_imagem"]
            templates = listar_templates_plus_5(self.config)
            total_templates = len(templates)
            if not templates:
                raise FileNotFoundError("Nenhum template +5 encontrado.")

            resultados = localizar_templates(
                templates,
                confianca=deteccao["confianca"],
                regiao=deteccao.get("regiao"),
                max_resultados=20,
                parar_score=deteccao.get("score_forte", 0.95),
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

    def parse_int(self, var, nome):
        try:
            return int(var.get().strip())
        except ValueError as exc:
            raise ValueError(f"{nome} precisa ser um numero inteiro.") from exc

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
                "Pausa apos conjunto diario",
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
            pause_state = "normal" if running and not self.pause_automation.is_set() else "disabled"
            resume_state = "normal" if running and self.pause_automation.is_set() else "disabled"
            cancel_state = "normal" if running else "disabled"

            self.start_button.config(state=principal_state)
            self.conjunto_button.config(state=principal_state)
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

    def cancelar_automacao(self):
        if not self.automation_running:
            return

        self.stop_automation.set()
        self.pause_automation.clear()
        self.status_com_log("Cancelando automacao...", "orange")
        self.atualizar_botoes_pausa()

    def esperar_se_pausado(self):
        if not self.pause_automation.is_set():
            return not self.stop_automation.is_set()

        while self.pause_automation.is_set():
            if self.stop_automation.is_set():
                return False
            time.sleep(0.1)

        return not self.stop_automation.is_set()

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
                "Nenhuma funcao selecionada",
                "Selecione pelo menos uma funcao primaria: conjunto diario, pesquisas, tempo no Edge ou Brotato.",
                parent=self.root,
            )
            return

        self.exec_logger.iniciar(
            "Fluxo selecionado",
            abrir_cmd=self.config.get("debug", {}).get("abrir_cmd", True),
        )
        limpar_cache_execucao(self.config)
        self.stop_automation.clear()
        self.pause_automation.clear()
        self.stop_automation.pause_event = self.pause_automation
        self.set_running(True)
        self.status_com_log("Iniciando fluxo selecionado...")
        thread = threading.Thread(target=self.fluxo_completo, daemon=True)
        thread.start()

    def start_conjunto_thread(self):
        if not self.save_config():
            return

        self.exec_logger.iniciar(
            "Config conjunto diario",
            abrir_cmd=self.config.get("debug", {}).get("abrir_cmd", True),
        )
        limpar_cache_execucao(self.config)
        self.stop_automation.clear()
        self.pause_automation.clear()
        self.stop_automation.pause_event = self.pause_automation
        self.set_running(True)
        self.status_com_log("Iniciando somente o conjunto diario...")
        thread = threading.Thread(target=self.fluxo_conjunto_diario, daemon=True)
        thread.start()

    def fluxo_conjunto_diario(self):
        try:
            self.log_execucao("Preparando automacao do conjunto diario.")
            pa.FAILSAFE = True
            pa.PAUSE = 0.05
            coordenadas = carregar_coordenadas(self.config)
            self.log_execucao(f"Coordenadas carregadas: {coordenadas}")
            concluido = executar_fluxo_inicial(
                self.config,
                coordenadas=coordenadas,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
                safety_callback=self.confirmar_intervencao_mouse,
            )

            if concluido:
                self.status_com_log("Config conjunto diario concluido.", "green")
            else:
                self.status_com_log("Automacao interrompida.", "orange")
        except SystemExit as exc:
            self.status_com_log(str(exc), "red")
        except Exception as exc:
            self.status_com_log(f"Erro no conjunto diario: {exc}", "red")
        finally:
            self.log_execucao("Finalizando thread do conjunto diario.")
            self.set_running(False)

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
            self.brotato_aberto = False

            if executar_conjunto:
                coordenadas = carregar_coordenadas(self.config)
                self.log_execucao(f"Coordenadas carregadas: {coordenadas}")
                concluido = executar_fluxo_inicial(
                    self.config,
                    coordenadas=coordenadas,
                    stop_event=self.stop_automation,
                    status_callback=self.status_com_log,
                    safety_callback=self.confirmar_intervencao_mouse,
                )

                if not concluido:
                    self.status_com_log("Automacao interrompida.", "orange")
                    return

                edge_aberto = True
                if executar_pesquisas:
                    self.status_com_log("Conjunto diario concluido. Iniciando pesquisas...")
                    if not self.sleep_intervalo(
                        self.config["pesquisas"]["delay_apos_conjunto_diario"]
                    ):
                        self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                        return
                else:
                    self.status_com_log("Conjunto diario concluido. Pesquisas desativadas.", "green")

            if executar_pesquisas:
                if not executar_conjunto:
                    self.status_com_log("Abrindo Edge para executar somente pesquisas...")
                    if not abrir_edge(
                        self.config,
                        stop_event=self.stop_automation,
                        status_callback=self.status_com_log,
                    ):
                        self.status_com_log("Automacao interrompida ao abrir Edge.", "orange")
                        return
                    edge_aberto = True
                if not self.automation_search_logic():
                    return
                edge_aberto = True

            if executar_brotato and executar_edge_tempo:
                if not self.executar_brotato_logic(com_timer=False):
                    return
                edge_aberto = False

            if executar_edge_tempo:
                if not self.executar_tempo_edge_logic(
                    edge_ja_aberto=edge_aberto,
                    fechar_brotato_antes_verificar=executar_brotato,
                ):
                    return
            elif executar_brotato:
                if not self.executar_brotato_logic(com_timer=True):
                    return

            if not executar_conjunto and not executar_pesquisas and not executar_edge_tempo and not executar_brotato:
                self.status_com_log("Nenhuma funcao primaria selecionada.", "orange")
            else:
                self.status_com_log("Fluxo selecionado concluido.", "green")
        except SystemExit as exc:
            self.status_com_log(str(exc), "red")
        except Exception as exc:
            self.status_com_log(f"Erro na automacao: {exc}", "red")
        finally:
            self.log_execucao("Finalizando thread do fluxo completo.")
            self.set_running(False)

    def automation_search_logic(self):
        pesquisas = self.config["pesquisas"]
        num_searches = pesquisas["search_count"]
        delay_buscas = pesquisas["delay_entre_buscas"]
        self.log_execucao(f"Iniciando sessao de pesquisas: {num_searches} busca(s).")

        for i in range(1, num_searches + 1):
            if not self.esperar_se_pausado():
                self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                break

            self.status_com_log(f"Busca {i} de {num_searches}...", "blue")

            words = self.get_random_words()
            if not words:
                self.status_com_log("Erro ao buscar palavras. Tentando novamente...", "red")
                self.sleep_interruptivel(2)
                continue

            sentence = " ".join(words)
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
            self.status_com_log("Sessao de pesquisas concluida.", "green")
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
            )
            if alvo is not None:
                self.status_com_log(
                    f"Brotato no menu detectado: x={alvo['x']}, y={alvo['y']}, score={alvo['score']:.2f}.",
                    "green",
                )
                self.brotato_aberto = True
                return True

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

    def focar_brotato_pela_barra(self):
        brotato = self.config.get("brotato", {})
        timeout = float(brotato.get("fechar_timeout_segundos", 20))
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
        if not self.focar_brotato_pela_barra():
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
        if not self.abrir_brotato():
            return False
        if not self.aguardar_brotato_menu():
            return False

        if not com_timer:
            self.status_com_log("Brotato aberto para rodar junto com o Tempo no Edge.")
            return True

        minutos = float(self.config.get("brotato", {}).get("tempo_minutos", 17))
        self.status_com_log(f"Brotato ficara aberto por {minutos:.1f} minuto(s).")
        if not self.sleep_minutos_com_log(minutos, "Timer Brotato"):
            self.status_com_log("Automacao interrompida durante timer do Brotato.", "orange")
            return False

        return self.fechar_brotato()

    def executar_tempo_edge_logic(self, edge_ja_aberto=False, fechar_brotato_antes_verificar=False):
        edge_tempo = self.config.get("edge_tempo", {})
        url_video = edge_tempo.get("url_video", "").strip()
        if not url_video:
            self.status_com_log("Tempo Edge ativado, mas a URL do video esta vazia.", "red")
            return False

        primeira_espera = float(edge_tempo.get("primeira_espera_minutos", 36))
        margem_extra = float(edge_tempo.get("margem_extra_minutos", 1))
        max_tentativas = int(edge_tempo.get("max_tentativas", 3))
        espera_atual = primeira_espera

        if not edge_ja_aberto:
            self.status_com_log("Abrindo Edge para iniciar tempo no navegador...")
            if not abrir_edge(
                self.config,
                stop_event=self.stop_automation,
                status_callback=self.status_com_log,
            ):
                self.status_com_log("Automacao interrompida ao abrir Edge.", "orange")
                return False

        for tentativa in range(1, max_tentativas + 1):
            self.status_com_log(
                f"Tempo Edge: tentativa {tentativa}/{max_tentativas}. "
                f"Video ficara aberto por {espera_atual:.1f} minuto(s)."
            )
            if not self.abrir_video_no_edge(url_video):
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
                self.status_com_log("Refocando Edge antes de fechar e verificar o Rewards...")
                if not abrir_edge(
                    self.config,
                    stop_event=self.stop_automation,
                    status_callback=self.status_com_log,
                ):
                    return False

            tracker = self.reabrir_edge_e_verificar_tracker()
            if tracker is None:
                self.status_com_log(
                    "Nao consegui verificar o tempo do Edge. Treine os estados do tracker e tente novamente.",
                    "red",
                )
                return False

            if tracker["completo"]:
                self.status_com_log(
                    f"Task Navegar com Edge completa: {tracker['minutos']}/{tracker['total']} min.",
                    "green",
                )
                return True

            faltam = int(tracker["faltam"])
            if tentativa >= max_tentativas:
                self.status_com_log(
                    f"Tempo Edge ainda incompleto: faltam {faltam} min e o limite de verificacoes foi atingido.",
                    "orange",
                )
                return False

            espera_atual = max(1.0, faltam + margem_extra)
            self.status_com_log(
                f"Tempo Edge incompleto: {tracker['minutos']}/{tracker['total']} min. "
                f"Nova espera: {espera_atual:.1f} minuto(s).",
                "orange",
            )

        return False

    def abrir_video_no_edge(self, url_video):
        if not self.esperar_se_pausado():
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

    def reabrir_edge_e_verificar_tracker(self):
        if not self.fechar_edge_ativo():
            return None

        self.status_com_log("Reabrindo Edge para verificar task Navegar com Edge...")
        if not abrir_edge(
            self.config,
            stop_event=self.stop_automation,
            status_callback=self.status_com_log,
        ):
            return None

        delay = float(self.config.get("edge_tempo", {}).get("delay_apos_reabrir_edge", 2.0))
        if not self.sleep_interruptivel(delay):
            return None

        coordenadas = carregar_coordenadas(self.config)
        self.status_com_log("Abrindo menu do Microsoft Rewards para checar progresso...")
        if not abrir_extensao_rewards(
            self.config,
            coordenadas,
            stop_event=self.stop_automation,
            status_callback=self.status_com_log,
            safety_callback=self.confirmar_intervencao_mouse,
        ):
            return None

        if not self.sleep_intervalo(self.config["tempos"]["apos_icone_extensao"]):
            return None

        return abrir_ver_tudo_e_detectar_tracker_edge(
            self.config,
            stop_event=self.stop_automation,
            status_callback=self.status_com_log,
            safety_callback=self.confirmar_intervencao_mouse,
        )

    def fechar_edge_ativo(self):
        if not self.esperar_se_pausado():
            return False

        self.status_com_log("Fechando janela atual do Edge para forcar atualizacao do Rewards...")
        pa.hotkey("alt", "f4")
        return self.sleep_interruptivel(2.0)

    def sleep_minutos_com_log(self, minutos, label):
        restante = max(0.0, float(minutos) * 60)
        proximo_log = 0.0

        while restante > 0:
            if not self.esperar_se_pausado():
                return False

            if proximo_log <= 0:
                restantes_min = restante / 60
                self.status_com_log(f"{label}: faltam {restantes_min:.1f} minuto(s).")
                proximo_log = 60.0

            pausa = min(1.0, restante)
            inicio = time.time()
            time.sleep(pausa)
            decorrido = time.time() - inicio
            restante -= decorrido
            proximo_log -= decorrido

        return True

    def get_random_words(self):
        intervalo = self.config["pesquisas"]["palavras_por_busca"]
        number_of_words = random.randint(intervalo["min"], intervalo["max"])
        url = f"https://random-word-api.vercel.app/api?words={number_of_words}"

        try:
            self.log_execucao(f"Buscando {number_of_words} palavra(s) na API.")
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            words = response.json()
            if isinstance(words, list) and words:
                self.log_execucao(f"Palavras recebidas da API: {words}")
                return words
        except requests.exceptions.RequestException:
            self.log_execucao("API de palavras falhou. Usando palavras locais.")

        words = random.choices(PALAVRAS_FALLBACK, k=number_of_words)
        self.log_execucao(f"Palavras locais escolhidas: {words}")
        return words

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
            self.pausar_automacao()

    def start_keyboard_listener(self):
        listener = keyboard.Listener(on_press=self.on_press)
        listener.daemon = True
        listener.start()


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoRewardsApp(root)
    root.mainloop()
