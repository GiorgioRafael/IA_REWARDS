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
    carregar_coordenadas,
    executar_fluxo_inicial,
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
        "usar_treinamento": True,
        "treino_dir": "assets/treino_plus_10",
        "confianca": 0.85,
        "max_cards": 3,
        "max_scrolls": 40,
        "scroll_amount": -2,
        "detectar_fim_scroll": True,
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
    "pesquisas": {
        "desktop_coords": {"x": -1397, "y": 122},
        "mobile_coords": {"x": -1152, "y": 114},
        "search_count": 30,
        "use_mobile": False,
        "executar_conjunto_diario": True,
        "usar_ctrl_l_desktop": True,
        "delay_apos_conjunto_diario": {"min": 2.0, "max": 5.0},
        "delay_entre_buscas": {"min": 5.0, "max": 8.0},
        "palavras_por_busca": {"min": 1, "max": 3},
    },
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

    def iniciar(self, titulo):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        agora = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = LOGS_DIR / f"execucao_{agora}.log"
        self.cmd_path = LOGS_DIR / f"abrir_log_{agora}.cmd"

        self.escrever("=" * 70)
        self.escrever(f"{titulo} iniciado")
        self.escrever(f"Arquivo de log: {self.log_path}")
        self.escrever("=" * 70)
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
            else:
                destino[chave] = valor

    mesclar(config, atual)
    return config


def migrar_config_antiga(config):
    if "pesquisas" not in config:
        config["pesquisas"] = {}

    for chave in ("desktop_coords", "mobile_coords", "search_count", "use_mobile"):
        if chave in config:
            config["pesquisas"][chave] = config[chave]

    if "skip_browser_open" in config:
        config["pesquisas"]["executar_conjunto_diario"] = not config["skip_browser_open"]

    return config


class AutoRewardsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Rewards Automacao")
        self.root.geometry("820x920")
        self.root.resizable(False, True)

        self.stop_automation = threading.Event()
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
        with CONFIG_FILE.open("w", encoding="utf-8") as arquivo:
            json.dump(config, arquivo, indent=2)

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill="both", expand=True)

        self.search_tab = ttk.Frame(self.notebook, padding="10")
        self.conjunto_tab = ttk.Frame(self.notebook, padding="10")

        self.notebook.add(self.search_tab, text="Pesquisas")
        self.notebook.add(self.conjunto_tab, text="Config conjunto diario")

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
            text="Pressione ESC a qualquer momento para parar a automacao.",
            foreground="gray",
        ).pack(pady=(8, 0))

    def setup_pesquisas_tab(self):
        pesquisas = self.config["pesquisas"]

        self.searches_var = tk.StringVar(value=str(pesquisas["search_count"]))
        self.desktop_x_var = tk.StringVar(value=str(pesquisas["desktop_coords"]["x"]))
        self.desktop_y_var = tk.StringVar(value=str(pesquisas["desktop_coords"]["y"]))
        self.mobile_x_var = tk.StringVar(value=str(pesquisas["mobile_coords"]["x"]))
        self.mobile_y_var = tk.StringVar(value=str(pesquisas["mobile_coords"]["y"]))
        self.use_mobile_var = tk.BooleanVar(value=pesquisas["use_mobile"])
        self.executar_conjunto_var = tk.BooleanVar(
            value=pesquisas["executar_conjunto_diario"]
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

        general_frame = ttk.LabelFrame(
            self.search_tab, text="Configuracoes gerais", padding="10"
        )
        general_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(general_frame, text="Numero de buscas:").grid(
            row=0, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(general_frame, textvariable=self.searches_var, width=10).grid(
            row=0, column=1, sticky="w", padx=5, pady=5
        )

        ttk.Checkbutton(
            general_frame,
            text="Usar coordenadas de Celular/Mobile",
            variable=self.use_mobile_var,
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            general_frame,
            text="Executar Config conjunto diario antes das pesquisas",
            variable=self.executar_conjunto_var,
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Checkbutton(
            general_frame,
            text="Focar barra do Edge com Ctrl+L no desktop",
            variable=self.usar_ctrl_l_desktop_var,
        ).grid(row=3, column=0, columnspan=4, sticky="w", padx=5, pady=5)

        ttk.Label(general_frame, text="Pausa apos conjunto diario:").grid(
            row=4, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            general_frame, textvariable=self.delay_apos_conjunto_min_var, width=8
        ).grid(row=4, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(general_frame, text="ate").grid(
            row=4, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(
            general_frame, textvariable=self.delay_apos_conjunto_max_var, width=8
        ).grid(row=4, column=3, sticky="w", padx=5, pady=5)

        ttk.Label(general_frame, text="Delay entre buscas:").grid(
            row=5, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(general_frame, textvariable=self.delay_busca_min_var, width=8).grid(
            row=5, column=1, sticky="w", padx=5, pady=5
        )
        ttk.Label(general_frame, text="ate").grid(
            row=5, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(general_frame, textvariable=self.delay_busca_max_var, width=8).grid(
            row=5, column=3, sticky="w", padx=5, pady=5
        )

        ttk.Label(general_frame, text="Palavras por busca:").grid(
            row=6, column=0, sticky="w", padx=5, pady=5
        )
        ttk.Entry(general_frame, textvariable=self.palavras_min_var, width=8).grid(
            row=6, column=1, sticky="w", padx=5, pady=5
        )
        ttk.Label(general_frame, text="ate").grid(
            row=6, column=2, sticky="w", padx=5, pady=5
        )
        ttk.Entry(general_frame, textvariable=self.palavras_max_var, width=8).grid(
            row=6, column=3, sticky="w", padx=5, pady=5
        )

        coords_frame = ttk.LabelFrame(
            self.search_tab, text="Coordenadas da barra de busca", padding="10"
        )
        coords_frame.pack(fill="x", pady=10)

        self.add_xy_row(
            coords_frame,
            0,
            "Desktop",
            self.desktop_x_var,
            self.desktop_y_var,
        )
        self.add_xy_row(coords_frame, 1, "Mobile", self.mobile_x_var, self.mobile_y_var)

        action_frame = ttk.Frame(self.search_tab, padding="10")
        action_frame.pack(fill="x")
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        self.start_button = ttk.Button(
            action_frame,
            text="Iniciar conjunto diario + pesquisas",
            command=self.start_fluxo_completo_thread,
        )
        self.start_button.grid(row=0, column=0, padx=5, sticky="ew")

        ttk.Button(
            action_frame,
            text="Salvar configuracoes",
            command=self.save_config,
        ).grid(row=0, column=1, padx=5, sticky="ew")

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
        self.deteccao_ativada_var = tk.BooleanVar(value=deteccao["ativada"])
        self.deteccao_fallback_var = tk.BooleanVar(
            value=deteccao["usar_fallback_coordenadas"]
        )
        self.template_plus_10_var = tk.StringVar(value=deteccao["template_plus_10"])
        self.usar_treinamento_var = tk.BooleanVar(
            value=deteccao["usar_treinamento"]
        )
        self.treino_dir_var = tk.StringVar(value=deteccao["treino_dir"])
        self.confianca_plus_10_var = tk.StringVar(value=str(deteccao["confianca"]))
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
            self.conjunto_tab, text="Abertura do navegador", padding="10"
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

        deteccao_frame = ttk.LabelFrame(
            self.conjunto_tab, text="Deteccao de imagem +10", padding="10"
        )
        deteccao_frame.pack(fill="x", pady=10)

        ttk.Checkbutton(
            deteccao_frame,
            text="Usar deteccao de imagem no conjunto diario",
            variable=self.deteccao_ativada_var,
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=5, pady=3)

        ttk.Checkbutton(
            deteccao_frame,
            text="Usar coordenadas antigas se o template nao existir",
            variable=self.deteccao_fallback_var,
        ).grid(row=1, column=0, columnspan=4, sticky="w", padx=5, pady=3)

        ttk.Label(deteccao_frame, text="Template:").grid(
            row=2, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.template_plus_10_var, width=28).grid(
            row=2, column=1, columnspan=3, sticky="w", padx=5, pady=3
        )

        ttk.Checkbutton(
            deteccao_frame,
            text="Usar base de treino",
            variable=self.usar_treinamento_var,
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=3)

        ttk.Label(deteccao_frame, text="Pasta treino:").grid(
            row=4, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.treino_dir_var, width=28).grid(
            row=4, column=1, columnspan=3, sticky="w", padx=5, pady=3
        )

        ttk.Label(deteccao_frame, text="Confianca:").grid(
            row=5, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.confianca_plus_10_var, width=8).grid(
            row=5, column=1, sticky="w", padx=5, pady=3
        )
        ttk.Label(deteccao_frame, text="Max cards:").grid(
            row=5, column=2, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.max_cards_var, width=8).grid(
            row=5, column=3, sticky="w", padx=5, pady=3
        )

        ttk.Label(deteccao_frame, text="Limite scrolls:").grid(
            row=6, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.max_scrolls_var, width=8).grid(
            row=6, column=1, sticky="w", padx=5, pady=3
        )
        ttk.Label(deteccao_frame, text="Scroll por busca:").grid(
            row=6, column=2, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.scroll_amount_var, width=8).grid(
            row=6, column=3, sticky="w", padx=5, pady=3
        )

        ttk.Label(deteccao_frame, text="Offset click X/Y:").grid(
            row=7, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.click_offset_x_var, width=8).grid(
            row=7, column=1, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.click_offset_y_var, width=8).grid(
            row=7, column=2, sticky="w", padx=5, pady=3
        )

        ttk.Label(deteccao_frame, text="Offset captura X/Y:").grid(
            row=8, column=0, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.capture_offset_x_var, width=8).grid(
            row=8, column=1, sticky="w", padx=5, pady=3
        )
        ttk.Entry(deteccao_frame, textvariable=self.capture_offset_y_var, width=8).grid(
            row=8, column=2, sticky="w", padx=5, pady=3
        )

        ttk.Button(
            deteccao_frame,
            text="Capturar template +10",
            command=self.capturar_template_plus_10,
        ).grid(row=9, column=0, columnspan=2, sticky="ew", padx=5, pady=(8, 3))

        ttk.Button(
            deteccao_frame,
            text="Testar deteccao +10",
            command=self.testar_deteccao_plus_10,
        ).grid(row=9, column=2, columnspan=2, sticky="ew", padx=5, pady=(8, 3))

        ttk.Button(
            deteccao_frame,
            text="Modo treino +10",
            command=self.iniciar_modo_treino_plus_10,
        ).grid(row=10, column=0, columnspan=4, sticky="ew", padx=5, pady=3)

        ttk.Button(
            deteccao_frame,
            text="Diagnostico mouse + deteccao",
            command=self.diagnosticar_mouse_deteccao,
        ).grid(row=11, column=0, columnspan=4, sticky="ew", padx=5, pady=3)

        coords_frame = ttk.LabelFrame(
            self.conjunto_tab, text="Coordenadas da extensao", padding="10"
        )
        coords_frame.pack(fill="x", pady=10)

        for row, (nome, label) in enumerate(COORD_LABELS.items()):
            coord = self.config["coordenadas"][nome]
            x_var = tk.StringVar(value="" if coord["x"] is None else str(coord["x"]))
            y_var = tk.StringVar(value="" if coord["y"] is None else str(coord["y"]))
            self.coord_vars[nome] = (x_var, y_var)
            self.add_xy_row(coords_frame, row, label, x_var, y_var)

        tempos_frame = ttk.LabelFrame(
            self.conjunto_tab, text="Intervalos aleatorios", padding="10"
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

        action_frame = ttk.Frame(self.conjunto_tab, padding="10")
        action_frame.pack(fill="x")
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        self.conjunto_button = ttk.Button(
            action_frame,
            text="Rodar apenas Config conjunto diario",
            command=self.start_conjunto_thread,
        )
        self.conjunto_button.grid(row=0, column=0, padx=5, sticky="ew")

        ttk.Button(
            action_frame,
            text="Salvar configuracoes",
            command=self.save_config,
        ).grid(row=0, column=1, padx=5, sticky="ew")

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

    def caminho_treino_plus_10(self):
        caminho = Path(self.treino_dir_var.get().strip() or "assets/treino_plus_10")
        if caminho.is_absolute():
            return caminho

        return BASE_DIR / caminho

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

    def diagnosticar_mouse_deteccao(self):
        if not self.save_config():
            return

        messagebox.showinfo(
            "Diagnostico",
            "A janela vai sumir por alguns segundos.\n\n"
            "Deixe o mouse sobre uma area que voce quer conferir.\n"
            "O app vai salvar um print do local atual do mouse, detectar o +10 e mover "
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

            templates = listar_templates_plus_10(self.config)
            resultado["total_templates"] = len(templates)
            detectados = []
            if templates:
                detectados = localizar_templates(
                    templates,
                    confianca=self.config["deteccao_imagem"]["confianca"],
                    regiao=self.config["deteccao_imagem"].get("regiao"),
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
                "Nenhum +10 detectado."
            )
            self.update_status("Diagnostico concluido: nenhum +10 detectado.", "orange")
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
            )
        except FileNotFoundError:
            erro = (
                "Template nao encontrado",
                "Capture primeiro o template +10 na aba Config conjunto diario.",
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
            mensagem = (
                f"+10 encontrado: {len(resultados)} resultado(s).\n"
                f"Templates usados: {total_templates}\n"
                f"Melhor score: {melhor['score']:.2f}\n"
                f"Coordenada: x={melhor['x']}, y={melhor['y']}"
            )
            self.update_status(
                f"+10 encontrado: {len(resultados)} resultado(s), melhor score {melhor['score']:.2f}.",
                "green",
            )
            messagebox.showinfo("Deteccao +10", mensagem, parent=self.root)
            return

        mensagem = (
            "Nenhum +10 encontrado com o template atual.\n\n"
            f"Templates usados: {total_templates}\n\n"
            "Tente capturar o template novamente com o mouse bem no centro do selo +10, "
            "ou reduza a confianca para 0.75."
        )
        self.update_status("Nenhum +10 encontrado com o template atual.", "orange")
        messagebox.showwarning("Deteccao +10", mensagem, parent=self.root)

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
            deteccao["ativada"] = self.deteccao_ativada_var.get()
            deteccao["usar_fallback_coordenadas"] = self.deteccao_fallback_var.get()
            deteccao["template_plus_10"] = (
                self.template_plus_10_var.get().strip() or "assets/plus_10.png"
            )
            deteccao["usar_treinamento"] = self.usar_treinamento_var.get()
            deteccao["treino_dir"] = (
                self.treino_dir_var.get().strip() or "assets/treino_plus_10"
            )
            deteccao["confianca"] = self.parse_float(
                self.confianca_plus_10_var, "Confianca +10"
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
            if deteccao["max_cards"] < 0:
                raise ValueError("Max cards nao pode ser negativo.")
            if deteccao["max_scrolls"] < 0:
                raise ValueError("Max scrolls nao pode ser negativo.")

            pesquisas = self.config["pesquisas"]
            pesquisas["desktop_coords"]["x"] = self.parse_int(
                self.desktop_x_var, "Desktop X"
            )
            pesquisas["desktop_coords"]["y"] = self.parse_int(
                self.desktop_y_var, "Desktop Y"
            )
            pesquisas["mobile_coords"]["x"] = self.parse_int(
                self.mobile_x_var, "Mobile X"
            )
            pesquisas["mobile_coords"]["y"] = self.parse_int(
                self.mobile_y_var, "Mobile Y"
            )
            pesquisas["search_count"] = self.parse_int(
                self.searches_var, "Numero de buscas"
            )
            pesquisas["use_mobile"] = self.use_mobile_var.get()
            pesquisas["executar_conjunto_diario"] = self.executar_conjunto_var.get()
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

    def set_running(self, running):
        state = "disabled" if running else "normal"
        self.root.after(0, lambda: self.start_button.config(state=state))
        self.root.after(0, lambda: self.conjunto_button.config(state=state))

    def start_fluxo_completo_thread(self):
        if not self.save_config():
            return

        self.exec_logger.iniciar("Fluxo completo")
        self.stop_automation.clear()
        self.set_running(True)
        self.status_com_log("Iniciando conjunto diario + pesquisas...")
        thread = threading.Thread(target=self.fluxo_completo, daemon=True)
        thread.start()

    def start_conjunto_thread(self):
        if not self.save_config():
            return

        self.exec_logger.iniciar("Config conjunto diario")
        self.stop_automation.clear()
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

            if self.config["pesquisas"]["executar_conjunto_diario"]:
                coordenadas = carregar_coordenadas(self.config)
                self.log_execucao(f"Coordenadas carregadas: {coordenadas}")
                concluido = executar_fluxo_inicial(
                    self.config,
                    coordenadas=coordenadas,
                    stop_event=self.stop_automation,
                    status_callback=self.status_com_log,
                )

                if not concluido:
                    self.status_com_log("Automacao interrompida.", "orange")
                    return

                self.status_com_log("Conjunto diario concluido. Iniciando pesquisas...")
                if not self.sleep_intervalo(
                    self.config["pesquisas"]["delay_apos_conjunto_diario"]
                ):
                    self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                    return

            self.automation_search_logic()
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
            if self.stop_automation.is_set():
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
            if self.stop_automation.is_set():
                self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                break

            self.log_execucao("Limpando barra de busca com Ctrl+A e Delete.")
            pa.hotkey("ctrl", "a")
            pa.press("delete")
            self.log_execucao("Digitando busca letra por letra.")
            self.write_text_letter_by_letter(sentence)

            if self.stop_automation.is_set():
                self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                break

            self.log_execucao("Pressionando Enter para pesquisar.")
            pa.press("enter")

            delay = random.uniform(delay_buscas["min"], delay_buscas["max"])
            self.log_execucao(f"Aguardando {delay:.2f}s ate a proxima busca.")
            if not self.sleep_interruptivel(delay):
                self.status_com_log("Automacao interrompida pelo usuario.", "orange")
                break
        else:
            self.status_com_log("Fluxo completo concluido com sucesso.", "green")

    def focar_barra_busca(self, pesquisas):
        if not pesquisas["use_mobile"] and pesquisas["usar_ctrl_l_desktop"]:
            self.log_execucao("Focando barra do Edge com Ctrl+L.")
            pa.hotkey("ctrl", "l")
        elif pesquisas["use_mobile"]:
            self.log_execucao(
                "Focando barra mobile por coordenada: "
                f"x={pesquisas['mobile_coords']['x']}, y={pesquisas['mobile_coords']['y']}"
            )
            clicar_mouse(pesquisas["mobile_coords"]["x"], pesquisas["mobile_coords"]["y"])
        else:
            self.log_execucao(
                "Focando barra desktop por coordenada: "
                f"x={pesquisas['desktop_coords']['x']}, y={pesquisas['desktop_coords']['y']}"
            )
            clicar_mouse(pesquisas["desktop_coords"]["x"], pesquisas["desktop_coords"]["y"])

        self.sleep_interruptivel(0.5)

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
            if self.stop_automation.is_set():
                break

            pa.write(letter)
            time.sleep(random.uniform(0.01, 0.03))

    def sleep_interruptivel(self, segundos):
        fim = time.time() + segundos
        while time.time() < fim:
            if self.stop_automation.is_set():
                return False
            time.sleep(min(0.1, fim - time.time()))
        return True

    def sleep_intervalo(self, intervalo):
        segundos = random.uniform(intervalo["min"], intervalo["max"])
        return self.sleep_interruptivel(segundos)

    def on_press(self, key):
        if key == keyboard.Key.esc:
            self.stop_automation.set()

    def start_keyboard_listener(self):
        listener = keyboard.Listener(on_press=self.on_press)
        listener.daemon = True
        listener.start()


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoRewardsApp(root)
    root.mainloop()
