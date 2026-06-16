import argparse
import ctypes
import json
import random
import re
import time
import unicodedata
from pathlib import Path
from ctypes import wintypes

from PIL import ImageChops, ImageStat

try:
    import cv2
    import numpy as np

    VISAO_ARRAY_DISPONIVEL = True
except Exception:
    cv2 = None
    np = None
    VISAO_ARRAY_DISPONIVEL = False

try:
    import pyautogui
except ModuleNotFoundError as exc:
    raise SystemExit(
        "pyautogui nao esta instalado. Instale com: pip install pyautogui"
    ) from exc

try:
    from deteccao_imagem import (
        capturar_tela,
        clicar_mouse,
        detectar_painel_rewards,
        detectar_scrollbar_thumb_em_imagem,
        get_mouse_position,
        localizar_templates,
        mover_mouse,
        obter_bbox_virtual,
        rolar_mouse,
        validar_sinal_mais_no_alvo,
    )

    DETECCAO_IMAGEM_DISPONIVEL = True
except Exception:
    capturar_tela = None
    clicar_mouse = None
    detectar_painel_rewards = None
    detectar_scrollbar_thumb_em_imagem = None
    get_mouse_position = None
    localizar_templates = None
    mover_mouse = None
    obter_bbox_virtual = None
    rolar_mouse = None
    validar_sinal_mais_no_alvo = None
    DETECCAO_IMAGEM_DISPONIVEL = False


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"
SW_RESTORE = 9
SW_MAXIMIZE = 3
WM_CLOSE = 0x0010
MONITORINFOF_PRIMARY = 1
MONITOR_DEFAULTTONEAREST = 2


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def carregar_config(caminho_config):
    with caminho_config.open("r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def obter_coordenada(coordenadas, nome):
    return coordenadas[nome]["x"], coordenadas[nome]["y"]


def esperar_se_pausado(stop_event):
    pause_event = getattr(stop_event, "pause_event", None)
    if pause_event is None:
        return True

    while pause_event.is_set():
        if stop_event is not None and stop_event.is_set():
            return False
        time.sleep(0.1)

    return stop_event is None or not stop_event.is_set()


def deve_parar(stop_event):
    if stop_event is None:
        return False

    if not esperar_se_pausado(stop_event):
        return True

    return stop_event.is_set()


def dormir(segundos, stop_event=None):
    restante = float(segundos)
    while restante > 0:
        if deve_parar(stop_event):
            return False
        pausa = min(0.1, restante)
        inicio = time.time()
        time.sleep(pausa)
        restante -= time.time() - inicio
    return True


def rect_para_dict(rect):
    return {
        "x": int(rect.left),
        "y": int(rect.top),
        "width": int(rect.right - rect.left),
        "height": int(rect.bottom - rect.top),
    }


def listar_monitores_windows():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    monitores = []

    monitor_enum_proc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )

    def visitar_monitor(hmonitor, _hdc, _rect, _lparam):
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            area = rect_para_dict(info.rcMonitor)
            trabalho = rect_para_dict(info.rcWork)
            monitores.append(
                {
                    **area,
                    "work_x": trabalho["x"],
                    "work_y": trabalho["y"],
                    "work_width": trabalho["width"],
                    "work_height": trabalho["height"],
                    "primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
                }
            )
        return True

    user32.EnumDisplayMonitors(0, 0, monitor_enum_proc(visitar_monitor), 0)
    return monitores


def obter_monitor_secundario():
    monitores = listar_monitores_windows()
    if len(monitores) < 2:
        return None

    secundarios = [monitor for monitor in monitores if not monitor.get("primary")]
    if secundarios:
        return sorted(secundarios, key=lambda item: (item["x"], item["y"]))[0]

    return sorted(monitores, key=lambda item: (item["x"], item["y"]))[1]


def obter_monitor_da_janela(hwnd):
    if not hwnd:
        return None

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hmonitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not hmonitor:
        return None

    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
        return None

    area = rect_para_dict(info.rcMonitor)
    trabalho = rect_para_dict(info.rcWork)
    return {
        **area,
        "work_x": trabalho["x"],
        "work_y": trabalho["y"],
        "work_width": trabalho["width"],
        "work_height": trabalho["height"],
        "primary": bool(info.dwFlags & MONITORINFOF_PRIMARY),
    }


def obter_janela_ativa():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    return user32.GetForegroundWindow()


def obter_titulo_janela(hwnd):
    if not hwnd:
        return ""

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    tamanho = user32.GetWindowTextLengthW(hwnd)
    if tamanho <= 0:
        return ""

    buffer = ctypes.create_unicode_buffer(tamanho + 1)
    user32.GetWindowTextW(hwnd, buffer, tamanho + 1)
    return buffer.value.strip()


def normalizar_titulo_janela(texto):
    texto = "" if texto is None else str(texto)
    texto = unicodedata.normalize("NFKC", texto)
    texto = "".join(
        caractere
        for caractere in texto
        if unicodedata.category(caractere) != "Cf"
    )
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip().lower()


def compactar_titulo_janela(texto):
    return re.sub(r"[^a-z0-9]+", "", normalizar_titulo_janela(texto))


def titulo_contem_parte(titulo, parte):
    titulo_normalizado = normalizar_titulo_janela(titulo)
    parte_normalizada = normalizar_titulo_janela(parte)
    if not parte_normalizada:
        return False

    if parte_normalizada in titulo_normalizado:
        return True

    parte_compacta = compactar_titulo_janela(parte)
    if not parte_compacta:
        return False

    return parte_compacta in compactar_titulo_janela(titulo)


def janela_parece_edge(hwnd, navegador=None):
    titulo = obter_titulo_janela(hwnd)
    if not titulo:
        return False

    navegador = navegador or {}
    partes = [
        navegador.get("titulo_janela", "Microsoft Edge"),
        "Microsoft Edge",
    ]
    return any(titulo_contem_parte(titulo, parte) for parte in partes)


def encontrar_janela_por_titulo(partes_titulo):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    partes = [str(parte).strip() for parte in partes_titulo if str(parte).strip()]
    if not partes:
        return None, None

    encontrados = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visitar_janela(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True

        tamanho = user32.GetWindowTextLengthW(hwnd)
        if tamanho <= 0:
            return True

        buffer = ctypes.create_unicode_buffer(tamanho + 1)
        user32.GetWindowTextW(hwnd, buffer, tamanho + 1)
        titulo = buffer.value.strip()
        if any(titulo_contem_parte(titulo, parte) for parte in partes):
            encontrados.append((hwnd, titulo))
            return False

        return True

    user32.EnumWindows(enum_proc(visitar_janela), 0)
    if not encontrados:
        return None, None

    return encontrados[0]


def janela_windows_valida(hwnd):
    if not hwnd:
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    return bool(user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd))


def encontrar_janela_edge(config, preferir_ativa=True):
    navegador = config.get("navegador", {})
    if preferir_ativa:
        hwnd_ativo = obter_janela_ativa()
        if janela_windows_valida(hwnd_ativo) and janela_parece_edge(hwnd_ativo, navegador):
            return hwnd_ativo, obter_titulo_janela(hwnd_ativo)

    titulo_config = navegador.get("titulo_janela", "Microsoft Edge")
    return encontrar_janela_por_titulo([titulo_config, "Microsoft Edge"])


def focar_janela_edge(hwnd, config, stop_event=None, status_callback=None):
    if deve_parar(stop_event):
        return False

    if not janela_windows_valida(hwnd):
        avisar(status_callback, "A janela armazenada do Edge nao existe mais.", "red")
        return False

    if not janela_parece_edge(hwnd, config.get("navegador", {})):
        avisar(status_callback, "A janela armazenada nao parece mais ser do Edge.", "red")
        return False

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    return dormir(0.4, stop_event)


def fechar_janela_edge(hwnd, timeout=10, stop_event=None, status_callback=None):
    if not janela_windows_valida(hwnd):
        return True

    titulo = obter_titulo_janela(hwnd) or "janela Edge"
    avisar(status_callback, f"Fechando Edge pelo X/fechamento da janela: {titulo}.", "orange")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    limite = time.time() + max(1.0, float(timeout))
    while time.time() < limite:
        if deve_parar(stop_event):
            return False
        if not janela_windows_valida(hwnd):
            avisar(status_callback, "Janela Edge fechada com sucesso.", "green")
            return True
        time.sleep(0.2)

    avisar(status_callback, "A janela Edge nao fechou dentro do timeout.", "red")
    return False


def mover_janela_para_monitor(hwnd, monitor):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    x = int(monitor.get("work_x", monitor["x"]))
    y = int(monitor.get("work_y", monitor["y"]))
    width = int(monitor.get("work_width", monitor["width"]))
    height = int(monitor.get("work_height", monitor["height"]))

    user32.ShowWindow(hwnd, SW_RESTORE)
    time.sleep(0.2)
    user32.MoveWindow(hwnd, x, y, width, height, True)
    time.sleep(0.2)
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    user32.SetForegroundWindow(hwnd)


def monitor_eh_secundario(hwnd):
    monitor = obter_monitor_da_janela(hwnd)
    return bool(monitor is not None and not monitor.get("primary"))


def centro_monitor(monitor):
    return (
        int(monitor["x"]) + int(monitor["width"]) // 2,
        int(monitor["y"]) + int(monitor["height"]) // 2,
    )


def forcar_edge_no_segundo_monitor(
    config,
    stop_event=None,
    status_callback=None,
    hwnd_preferido=None,
):
    navegador = config.get("navegador", {})
    if not navegador.get("forcar_segundo_monitor", False):
        return True

    if deve_parar(stop_event):
        return False

    monitor_destino = obter_monitor_secundario()
    if monitor_destino is None:
        avisar(
            status_callback,
            "Nao encontrei monitor secundario configurado no Windows. Vou continuar sem mover.",
            "orange",
        )
        return True

    hwnd = None
    titulo = None
    if janela_windows_valida(hwnd_preferido) and janela_parece_edge(hwnd_preferido, navegador):
        hwnd = hwnd_preferido
        titulo = obter_titulo_janela(hwnd) or "janela armazenada do Edge"
        avisar(status_callback, f"Usando janela Edge da sessao: {titulo}")
    elif navegador.get("buscar_titulo_janela", False):
        titulo_config = navegador.get("titulo_janela", "Microsoft Edge")
        partes_titulo = [titulo_config, "Microsoft Edge"]
        avisar(status_callback, "Buscando janela do Edge pelo titulo antes dos atalhos.")
        hwnd, titulo = encontrar_janela_por_titulo(partes_titulo)
        if hwnd is not None:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            if not dormir(0.4, stop_event):
                return False
        else:
            avisar(
                status_callback,
                "Nao encontrei a janela pelo titulo. Vou validar a janela ativa como fallback.",
                "orange",
            )
            if not dormir(0.2, stop_event):
                return False
            hwnd_ativo = obter_janela_ativa()
            titulo_ativo = obter_titulo_janela(hwnd_ativo)
            if janela_parece_edge(hwnd_ativo, navegador):
                hwnd = hwnd_ativo
                titulo = titulo_ativo or "janela ativa do Edge"
                avisar(status_callback, f"Janela ativa parece ser Edge: {titulo}")
            else:
                avisar(
                    status_callback,
                    f"Janela ativa nao parece ser Edge ({titulo_ativo or 'sem titulo'}). "
                    "Vou interromper para nao mover/clicar na janela errada.",
                    "red",
                )
                return False
    else:
        avisar(
            status_callback,
            "Busca por titulo desativada. Vou validar a janela ativa antes de mover.",
        )
        if not dormir(0.2, stop_event):
            return False
        hwnd_ativo = obter_janela_ativa()
        titulo_ativo = obter_titulo_janela(hwnd_ativo)
        if janela_parece_edge(hwnd_ativo, navegador):
            hwnd = hwnd_ativo
            titulo = titulo_ativo or "janela ativa do Edge"
            avisar(status_callback, f"Janela ativa parece ser Edge: {titulo}")
        else:
            avisar(
                status_callback,
                f"Janela ativa nao parece ser Edge ({titulo_ativo or 'sem titulo'}). "
                "Vou procurar o Edge pelo titulo como fallback.",
                "orange",
            )
            hwnd, titulo = encontrar_janela_por_titulo(["Microsoft Edge"])
            if hwnd is None:
                avisar(
                    status_callback,
                    "Nao encontrei a janela do Edge para mover ao segundo monitor.",
                    "red",
                )
                return False

    if hwnd is not None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        if not dormir(0.3, stop_event):
            return False

    hwnd_atual = hwnd or obter_janela_ativa()
    monitor_atual = obter_monitor_da_janela(hwnd_atual)
    ja_esta_no_secundario = bool(
        monitor_atual is not None and not monitor_atual.get("primary")
    )

    if monitor_atual is None:
        avisar(
            status_callback,
            "Nao consegui identificar o monitor atual da janela. Vou aplicar o fluxo completo de atalhos.",
            "orange",
        )
    elif ja_esta_no_secundario:
        avisar(
            status_callback,
            "Edge ja esta em um monitor secundario. Vou normalizar tamanho/posicao sem usar Win+Shift.",
            "green",
        )
    else:
        avisar(
            status_callback,
            "Edge esta no monitor principal. Vou enviar para o segundo monitor.",
        )

    if hwnd is not None:
        avisar(
            status_callback,
            "Ajustando Edge diretamente para o retangulo do monitor secundario pela API do Windows.",
        )
        mover_janela_para_monitor(hwnd, monitor_destino)
        if not dormir(0.5, stop_event):
            return False
        if monitor_eh_secundario(hwnd):
            avisar(status_callback, "Edge confirmado e normalizado no monitor secundario.", "green")
            return True

        avisar(
            status_callback,
            "Movimento direto nao foi confirmado. Vou tentar o atalho como fallback.",
            "orange",
        )
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        if not dormir(0.3, stop_event):
            return False

    direcao = "left"
    if monitor_atual is not None and monitor_destino is not None:
        atual_x, _atual_y = centro_monitor(monitor_atual)
        destino_x, _destino_y = centro_monitor(monitor_destino)
        direcao = "left" if destino_x < atual_x else "right"

    avisar(status_callback, "Aplicando atalho: Win+Shift+Up.")
    pyautogui.hotkey("win", "shift", "up")
    if not dormir(0.3, stop_event):
        return False

    avisar(status_callback, f"Aplicando atalho: Win+Shift+{direcao.title()}.")
    pyautogui.hotkey("win", "shift", direcao)
    if not dormir(0.5, stop_event):
        return False

    if hwnd is not None and not monitor_eh_secundario(hwnd):
        avisar(
            status_callback,
            "Falha ao confirmar Edge no monitor secundario depois dos atalhos. "
            "Vou interromper para nao clicar no monitor errado.",
            "red",
        )
        return False

    titulo_log = titulo if hwnd is not None else "janela ativa"
    avisar(status_callback, f"Edge movido/preparado no monitor secundario: {titulo_log}", "green")
    return dormir(0.5, stop_event)


def carregar_coordenadas(config):
    coordenadas = config["coordenadas"]

    coordenada_icone_extensao_x, coordenada_icone_extensao_y = obter_coordenada(
        coordenadas, "icone_extensao"
    )

    coordenada_double_click_scroll_x, coordenada_double_click_scroll_y = obter_coordenada(
        coordenadas, "double_click_scroll"
    )

    coordenada_card_1_x, coordenada_card_1_y = obter_coordenada(coordenadas, "card_1")

    coordenada_card_2_x, coordenada_card_2_y = obter_coordenada(coordenadas, "card_2")

    coordenada_card_3_x, coordenada_card_3_y = obter_coordenada(coordenadas, "card_3")

    coordenada_voltar_x, coordenada_voltar_y = obter_coordenada(coordenadas, "voltar")

    return {
        "icone_extensao": (
            coordenada_icone_extensao_x,
            coordenada_icone_extensao_y,
        ),
        "double_click_scroll": (
            coordenada_double_click_scroll_x,
            coordenada_double_click_scroll_y,
        ),
        "card_1": (coordenada_card_1_x, coordenada_card_1_y),
        "card_2": (coordenada_card_2_x, coordenada_card_2_y),
        "card_3": (coordenada_card_3_x, coordenada_card_3_y),
        "voltar": (coordenada_voltar_x, coordenada_voltar_y),
    }


def abrir_edge(config, stop_event=None, status_callback=None):
    tempos = config["tempos"]
    app_busca = config["app_busca"]

    if deve_parar(stop_event):
        return False

    limpar_cache_alvos_visuais(config)
    avisar(status_callback, "Pressionando tecla Windows.")
    pyautogui.press("win")
    if not dormir(tempos["apos_windows"], stop_event):
        return False

    avisar(status_callback, f"Digitando app no menu iniciar: {app_busca}")
    pyautogui.write(app_busca, interval=0.03)
    if not dormir(tempos["apos_digitar_app"], stop_event):
        return False

    avisar(status_callback, "Pressionando Enter para abrir o app.")
    pyautogui.press("enter")
    avisar(status_callback, f"Aguardando Edge abrir por {tempos['apos_enter']:.2f}s.")
    if not dormir(tempos["apos_enter"], stop_event):
        return False

    return forcar_edge_no_segundo_monitor(config, stop_event, status_callback)


def validar_coordenada(nome, x, y):
    if x is None or y is None:
        raise SystemExit(
            f"A coordenada '{nome}' ainda esta vazia no config.json. "
            "Preencha x e y antes de executar esta etapa."
        )


def esperar_intervalo(config, nome_tempo, stop_event=None, status_callback=None):
    intervalo = config["tempos"][nome_tempo]
    segundos = random.uniform(intervalo["min"], intervalo["max"])
    avisar(
        status_callback,
        f"Aguardando {segundos:.2f}s ({nome_tempo}: {intervalo['min']}-{intervalo['max']}s).",
    )
    return dormir(segundos, stop_event)


def clicar_coordenada(
    config,
    coordenadas,
    nome,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if deve_parar(stop_event):
        return False

    x, y = coordenadas[nome]
    validar_coordenada(nome, x, y)

    avisar(status_callback, f"Movendo mouse para '{nome}': x={x}, y={y}.")
    mover_mouse(x, y)
    if not dormir(config["tempos"]["movimento_mouse"], stop_event):
        return False
    if not garantir_mouse_no_alvo(
        config,
        nome,
        x,
        y,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    ):
        return False
    avisar(status_callback, f"Enviando clique em '{nome}'.")
    clicar_mouse()
    return True


def double_click_coordenada(
    config,
    coordenadas,
    nome,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if deve_parar(stop_event):
        return False

    x, y = coordenadas[nome]
    validar_coordenada(nome, x, y)

    avisar(status_callback, f"Movendo mouse para double click '{nome}': x={x}, y={y}.")
    mover_mouse(x, y)
    if not dormir(config["tempos"]["movimento_mouse"], stop_event):
        return False
    if not garantir_mouse_no_alvo(
        config,
        nome,
        x,
        y,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    ):
        return False
    avisar(status_callback, f"Enviando primeiro clique em '{nome}'.")
    clicar_mouse()
    if not dormir(0.05, stop_event):
        return False
    if not garantir_mouse_no_alvo(
        config,
        nome,
        x,
        y,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    ):
        return False
    avisar(status_callback, f"Enviando segundo clique em '{nome}'.")
    clicar_mouse()
    return True


def resolver_caminho(caminho):
    caminho = Path(caminho)
    if caminho.is_absolute():
        return caminho

    return BASE_DIR / caminho


def obter_config_deteccao(config):
    return config.get(
        "deteccao_imagem",
        {
            "ativada": False,
            "usar_fallback_coordenadas": True,
            "usar_variacoes": False,
            "busca_flexivel": False,
            "confianca_flexivel": 0.78,
            "escalas_flexiveis": [0.9, 0.95, 1.0, 1.05, 1.1],
        },
    )


def obter_config_seguranca(config):
    return config.get(
        "seguranca_mouse",
        {
            "ativada": True,
            "margem_pixels": 35,
            "reabrir_extensao_ao_continuar": True,
        },
    )


def usar_versao_fixa(config):
    return bool(config.get("automacao", {}).get("usar_versao_fixa", True))


def limpar_cache_execucao(config):
    config["_runtime_cache"] = {
        "alvos_visuais": {},
        "painel_rewards": None,
    }


def limpar_cache_alvos_visuais(config):
    cache = obter_cache_execucao(config)
    cache["alvos_visuais"] = {}


def obter_cache_execucao(config):
    cache = config.setdefault("_runtime_cache", {})
    cache.setdefault("alvos_visuais", {})
    cache.setdefault("painel_rewards", None)
    return cache


def salvar_cache_alvo_visual(config, nome, x, y, alvo=None):
    cache_alvos = obter_cache_execucao(config)["alvos_visuais"]
    cache_alvos[nome] = {
        "x": int(x),
        "y": int(y),
        "score": float((alvo or {}).get("score", 0)),
        "template": (alvo or {}).get("template"),
    }


def copiar_regiao_painel(regiao):
    if regiao is None:
        return None

    copia = {
        "x": int(regiao["x"]),
        "y": int(regiao["y"]),
        "width": int(regiao["width"]),
        "height": int(regiao["height"]),
    }
    for chave in ("score", "logo_score", "close_score", "light_ratio", "origem"):
        if chave in regiao:
            copia[chave] = regiao.get(chave)
    return copia


def salvar_cache_painel_rewards(config, regiao):
    painel = copiar_regiao_painel(regiao)
    if painel is not None:
        obter_cache_execucao(config)["painel_rewards"] = painel
    return painel


def obter_cache_painel_rewards(config):
    return copiar_regiao_painel(obter_cache_execucao(config).get("painel_rewards"))


def mouse_dentro_da_margem(atual_x, atual_y, alvo_x, alvo_y, margem):
    return abs(atual_x - alvo_x) <= margem and abs(atual_y - alvo_y) <= margem


def garantir_mouse_no_alvo(
    config,
    nome,
    x,
    y,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
    estado=None,
    recuperar_callback=None,
):
    if deve_parar(stop_event):
        return False

    seguranca = obter_config_seguranca(config)
    if not seguranca.get("ativada", True) or safety_callback is None:
        return True

    margem = int(seguranca.get("margem_pixels", 35))
    atual_x, atual_y = get_mouse_position()
    if mouse_dentro_da_margem(atual_x, atual_y, int(x), int(y), margem):
        return True

    avisar(
        status_callback,
        "Mouse saiu da area esperada. Pausando para confirmacao do usuario.",
        "orange",
    )
    evento = {
        "nome": nome,
        "esperado": {"x": int(x), "y": int(y)},
        "atual": {"x": int(atual_x), "y": int(atual_y)},
        "margem": margem,
        "estado": estado or {},
        "recuperacao": recuperar_callback is not None,
    }
    continuar = safety_callback(evento)
    if not continuar:
        avisar(status_callback, "Usuario cancelou a execucao apos pausa de seguranca.", "orange")
        if stop_event is not None:
            stop_event.set()
        return False

    avisar(status_callback, "Usuario escolheu continuar. Reposicionando automacao...")
    if recuperar_callback is not None:
        if not recuperar_callback():
            return False

    mover_mouse(x, y)
    return dormir(config["tempos"]["movimento_mouse"], stop_event)


def listar_templates_plus_10(config):
    deteccao = obter_config_deteccao(config)
    templates = []

    template_principal = resolver_caminho(deteccao["template_plus_10"])
    if template_principal.exists():
        templates.append(template_principal)

    if deteccao.get("usar_treinamento", True):
        treino_dir = resolver_caminho(deteccao.get("treino_dir", "assets/treino_plus_10"))
        if treino_dir.exists():
            for template_path in sorted(treino_dir.glob("*.png")):
                if template_path.resolve() != template_principal.resolve():
                    templates.append(template_path)

    return templates


def listar_templates_plus_5(config):
    deteccao = obter_config_deteccao(config)
    templates = []

    template_principal = resolver_caminho(deteccao.get("template_plus_5", "assets/plus_5.png"))
    if template_principal.exists():
        templates.append(template_principal)

    if deteccao.get("usar_treinamento", True):
        treino_dir = resolver_caminho(deteccao.get("treino_dir_plus_5", "assets/treino_plus_5"))
        if treino_dir.exists():
            for template_path in sorted(treino_dir.glob("*.png")):
                if template_path.resolve() != template_principal.resolve():
                    templates.append(template_path)

    return templates


def listar_templates_bonus(config):
    deteccao = obter_config_deteccao(config)
    templates = []

    if deteccao.get("usar_plus_10", True):
        templates.extend(listar_templates_plus_10(config))

    if deteccao.get("usar_plus_5", True):
        templates.extend(listar_templates_plus_5(config))

    return templates


def normalizar_escalas_flexiveis(valor):
    if not valor:
        valor = [0.9, 0.95, 1.0, 1.05, 1.1]

    escalas = []
    for escala in valor:
        try:
            escala = round(float(escala), 4)
        except (TypeError, ValueError):
            continue

        if escala <= 0:
            continue

        if escala not in escalas:
            escalas.append(escala)

    return escalas or [0.9, 0.95, 1.0, 1.05, 1.1]


def obter_escalas_flexiveis(config_obj):
    return normalizar_escalas_flexiveis(
        config_obj.get("escalas_flexiveis") or config_obj.get("escalas")
    )


def obter_confianca_flexivel(config_obj, confianca_padrao):
    if config_obj.get("confianca_flexivel") is not None:
        try:
            return float(config_obj["confianca_flexivel"])
        except (TypeError, ValueError):
            pass

    return max(0.68, float(confianca_padrao) - 0.12)


def usar_variacoes_deteccao(config, alvo_config=None):
    deteccao = obter_config_deteccao(config)
    if not bool(deteccao.get("usar_variacoes", False)):
        return False

    if alvo_config is not None and alvo_config.get("usar_variacoes") is False:
        return False

    return True


def obter_config_alvo_visual(config, nome):
    alvos = config.get("alvos_visuais", {})
    alvo = alvos.get(nome)
    if alvo is None:
        alvo = {}

    padroes = {
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
            "capture_width": 36,
            "capture_height": 36,
            "click_offset_x": 0,
            "click_offset_y": 0,
            "regiao": {"x": None, "y": None, "width": None, "height": None},
        },
    }
    config_padrao = padroes.get(nome, {})
    resultado = dict(config_padrao)
    resultado.update(alvo)
    return resultado


def listar_templates_alvo_visual(config, nome):
    alvo = obter_config_alvo_visual(config, nome)
    templates = []

    template = alvo.get("template")
    if template:
        template_principal = resolver_caminho(template)
        if template_principal.exists():
            templates.append(template_principal)
    else:
        template_principal = None

    treino_dir = alvo.get("treino_dir")
    if treino_dir:
        treino_path = resolver_caminho(treino_dir)
        if treino_path.exists():
            for template_path in sorted(treino_path.glob("*.png")):
                if template_principal is not None and template_path.resolve() == template_principal.resolve():
                    continue
                templates.append(template_path)

    return templates


def obter_config_edge_tracker(config):
    return config.get(
        "edge_tracker",
        {
            "treino_dir": "assets/treino_edge_tracker_estados",
            "estados_minutos": [0, 5, 10, 15, 20, 25, 30],
            "total_minutos": 30,
            "confianca": 0.82,
            "capture_width": 130,
            "capture_height": 42,
        },
    )


def listar_templates_tracker_estado(config, minutos):
    tracker = obter_config_edge_tracker(config)
    base_dir = resolver_caminho(tracker.get("treino_dir", "assets/treino_edge_tracker_estados"))
    estado_dir = base_dir / str(int(minutos))
    if not estado_dir.exists():
        return []

    return sorted(estado_dir.glob("*.png"))


def detectar_estado_tracker_edge(
    config,
    status_callback=None,
    stop_event=None,
    usar_regiao_painel=True,
):
    if deve_parar(stop_event):
        return None

    tracker = obter_config_edge_tracker(config)
    estados = [int(valor) for valor in tracker.get("estados_minutos", [0, 5, 10, 15, 20, 25, 30])]
    templates = []
    template_para_estado = {}

    for minutos in estados:
        for template_path in listar_templates_tracker_estado(config, minutos):
            templates.append(template_path)
            template_para_estado[str(template_path)] = minutos

    if not templates:
        avisar(
            status_callback,
            "Nenhum template de estado do tracker Edge encontrado. Treine os estados 0/30, 5/30 ... 30/30.",
            "orange",
        )
        return None

    regiao = obter_regiao_painel_rewards(config, status_callback) if usar_regiao_painel else None
    confianca = float(tracker.get("confianca", 0.82))
    avisar(
        status_callback,
        "Classificando tempo do Edge com "
        f"{len(templates)} template(s), confianca {confianca:.2f}, sem parada por match forte.",
    )
    resultados = localizar_templates(
        templates,
        confianca=confianca,
        regiao=regiao,
        max_resultados=50,
        parar_score=None,
        stop_event=stop_event,
    )
    if deve_parar(stop_event):
        return None

    if not resultados:
        avisar(status_callback, "Nao consegui identificar o estado do tracker Edge.", "orange")
        return None

    melhor = max(resultados, key=lambda item: item["score"])
    minutos = template_para_estado.get(melhor.get("template"))
    if minutos is None:
        minutos = 0

    total = int(tracker.get("total_minutos", 30))
    faltam = max(0, total - int(minutos))
    completo = int(minutos) >= total
    avisar(
        status_callback,
        "Tracker Edge identificado: "
        f"{minutos}/{total} min, faltam {faltam} min, score={melhor['score']:.2f}.",
        "green" if completo else "blue",
    )
    return {
        "minutos": int(minutos),
        "total": total,
        "faltam": faltam,
        "completo": completo,
        "score": float(melhor["score"]),
        "x": int(melhor["x"]),
        "y": int(melhor["y"]),
        "template": melhor.get("template"),
    }


def detectar_estado_rewards_atual(config, status_callback=None, stop_event=None):
    if deve_parar(stop_event):
        return {"estado": "interrompido", "ok": False}

    hwnd_ativo = obter_janela_ativa()
    titulo = obter_titulo_janela(hwnd_ativo)
    titulo_normalizado = normalizar_titulo_janela(titulo)
    edge_ativo = janela_windows_valida(hwnd_ativo) and janela_parece_edge(
        hwnd_ativo,
        config.get("navegador", {}),
    )

    x_exibir = y_exibir = None
    if listar_templates_alvo_visual(config, "exibir_painel"):
        x_exibir, y_exibir, _alvo = detectar_alvo_visual_visivel_e_cachear(
            config,
            "exibir_painel",
            status_callback=status_callback,
            stop_event=stop_event,
        )

    painel = obter_regiao_painel_rewards(
        config,
        status_callback,
        permitir_cache_sem_deteccao=False,
    )

    if x_exibir is not None and y_exibir is not None:
        estado = {
            "estado": "popup_rewards_ok",
            "ok": True,
            "titulo": titulo,
            "painel": painel,
            "anchor_exibir_painel": {"x": int(x_exibir), "y": int(y_exibir)},
        }
    elif "rewards" in titulo_normalizado:
        estado = {
            "estado": "pagina_rewards_completa",
            "ok": False,
            "titulo": titulo,
            "painel": painel,
        }
    elif painel is not None:
        estado = {
            "estado": "popup_rewards_ok_sem_exibir_painel",
            "ok": True,
            "titulo": titulo,
            "painel": painel,
        }
    elif edge_ativo:
        estado = {
            "estado": "edge_normal",
            "ok": False,
            "titulo": titulo,
            "painel": None,
        }
    else:
        estado = {
            "estado": "desconhecido",
            "ok": False,
            "titulo": titulo,
            "painel": painel,
        }

    painel_log = estado.get("painel")
    painel_desc = (
        f"x={painel_log['x']}, y={painel_log['y']}, "
        f"w={painel_log['width']}, h={painel_log['height']}"
        if painel_log is not None
        else "sem painel"
    )
    avisar(
        status_callback,
        "Estado Rewards detectado: "
        f"{estado['estado']} ({painel_desc}; titulo={titulo or 'sem titulo'}).",
        "green" if estado.get("ok") else "orange",
    )
    return estado


def abrir_ver_tudo_e_detectar_tracker_edge(
    config,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if deve_parar(stop_event):
        return None

    avisar(status_callback, "Procurando botao 'Ver tudo/Mostrar mais' para abrir detalhes do Rewards.")
    if not procurar_e_clicar_alvo_visual_com_scroll(
        config,
        "ver_tudo",
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    ):
        return None

    if not dormir(0.8, stop_event):
        return None

    return detectar_estado_tracker_edge(config, status_callback, stop_event)


def localizar_alvo_visual_no_painel(config, nome, status_callback=None, stop_event=None):
    if deve_parar(stop_event):
        return None

    alvo_config = obter_config_alvo_visual(config, nome)
    regiao = normalizar_regiao_manual(alvo_config.get("regiao"))
    if regiao is None:
        regiao = obter_regiao_painel_rewards(config, status_callback)

    if regiao is not None:
        avisar(
            status_callback,
            f"Busca do alvo '{nome}' limitada ao painel Rewards: "
            f"x={regiao['x']}, y={regiao['y']}, "
            f"w={regiao['width']}, h={regiao['height']}.",
        )

    return localizar_alvo_visual(
        config,
        nome,
        status_callback,
        regiao=regiao,
        stop_event=stop_event,
    )


def clicar_resultado_alvo_visual(
    config,
    nome,
    alvo,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if deve_parar(stop_event):
        return False

    alvo_config = obter_config_alvo_visual(config, nome)
    x = int(alvo["x"]) + int(alvo_config.get("click_offset_x", 0))
    y = int(alvo["y"]) + int(alvo_config.get("click_offset_y", 0))
    avisar(
        status_callback,
        f"Clicando alvo visual '{nome}' encontrado na busca com scroll: x={x}, y={y}.",
    )
    mover_mouse(x, y)
    if not dormir(config["tempos"]["movimento_mouse"], stop_event):
        return False
    if not garantir_mouse_no_alvo(
        config,
        nome,
        x,
        y,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    ):
        return False

    clicar_mouse()
    return True


def procurar_e_clicar_alvo_visual_com_scroll(
    config,
    nome,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if deve_parar(stop_event):
        return False

    if not listar_templates_alvo_visual(config, nome):
        avisar(status_callback, f"Nenhum template treinado para '{nome}'.", "orange")
        return False

    coordenadas = carregar_coordenadas(config)
    deteccao = obter_config_deteccao(config)
    limite_scrolls = int(deteccao.get("max_scrolls", 40))
    scroll_focado = False

    for tentativa in range(0, limite_scrolls + 1):
        if deve_parar(stop_event):
            return False

        avisar(
            status_callback,
            f"Procurando alvo '{nome}' no painel (posicao {tentativa}/{limite_scrolls}).",
        )
        alvo = localizar_alvo_visual_no_painel(
            config,
            nome,
            status_callback,
            stop_event=stop_event,
        )
        if alvo is not None:
            return clicar_resultado_alvo_visual(
                config,
                nome,
                alvo,
                stop_event=stop_event,
                status_callback=status_callback,
                safety_callback=safety_callback,
            )

        if tentativa >= limite_scrolls:
            break

        if not scroll_focado:
            avisar(status_callback, "Alvo nao visivel. Focando scroll do painel para continuar procurando.")
            if not focar_area_scroll(
                config,
                coordenadas,
                stop_event=stop_event,
                status_callback=status_callback,
                safety_callback=safety_callback,
            ):
                return False
            scroll_focado = True

        avisar(status_callback, f"Alvo '{nome}' nao encontrado. Rolando painel e tentando novamente.")
        resultado_scroll = rolar_area_extensao(
            config,
            coordenadas,
            stop_event=stop_event,
            status_callback=status_callback,
            safety_callback=safety_callback,
        )
        if not resultado_scroll.get("ok"):
            return False
        if resultado_scroll.get("fim_scroll"):
            avisar(
                status_callback,
                f"Fim do painel detectado antes de encontrar o alvo '{nome}'.",
                "orange",
            )
            break

    avisar(status_callback, f"Alvo '{nome}' nao encontrado depois de rolar o painel.", "red")
    return False


def localizar_alvo_visual(config, nome, status_callback=None, regiao=None, stop_event=None):
    if deve_parar(stop_event):
        return None

    alvo_config = obter_config_alvo_visual(config, nome)
    templates = listar_templates_alvo_visual(config, nome)
    if not templates:
        avisar(
            status_callback,
            f"Nenhum template treinado para '{nome}'. Use Iniciar treino antes.",
            "orange",
        )
        return None

    regiao_config = regiao or normalizar_regiao_manual(alvo_config.get("regiao"))
    if regiao_config is None:
        regiao_config = obter_regiao_padrao_alvo_visual(nome, config)
        if regiao_config is not None:
            avisar(
                status_callback,
                f"Busca do alvo '{nome}' limitada a area provavel: "
                f"x={regiao_config['x']}, y={regiao_config['y']}, "
                f"w={regiao_config['width']}, h={regiao_config['height']}.",
            )
        else:
            avisar(status_callback, f"Busca do alvo '{nome}' usando a tela inteira.")
    confianca = float(alvo_config.get("confianca", 0.82))
    score_forte = alvo_config.get("score_forte", 0.95)
    avisar(
        status_callback,
        f"Rodando deteccao do alvo '{nome}' com {len(templates)} template(s), "
        f"confianca {confianca:.2f}, match forte {float(score_forte):.2f}.",
    )
    resultados = localizar_templates(
        templates,
        confianca=confianca,
        regiao=regiao_config,
        max_resultados=10,
        parar_score=score_forte,
        stop_event=stop_event,
    )
    avisar(status_callback, f"Alvo '{nome}' retornou {len(resultados)} resultado(s).")
    if deve_parar(stop_event):
        return None

    if not resultados and usar_variacoes_deteccao(config, alvo_config):
        escalas = obter_escalas_flexiveis(alvo_config)
        confianca_flexivel = obter_confianca_flexivel(alvo_config, confianca)
        avisar(
            status_callback,
            f"Alvo '{nome}' nao encontrado no tamanho original. "
            f"Tentando busca flexivel com escalas {escalas} e confianca {confianca_flexivel:.2f}.",
            "orange",
        )
        resultados = localizar_templates(
            templates,
            confianca=confianca_flexivel,
            regiao=regiao_config,
            max_resultados=10,
            parar_score=score_forte,
            escalas=escalas,
            stop_event=stop_event,
        )
        avisar(
            status_callback,
            f"Busca flexivel do alvo '{nome}' retornou {len(resultados)} resultado(s).",
        )
        if deve_parar(stop_event):
            return None

        if not resultados:
            avisar(
                status_callback,
                f"Alvo '{nome}' ainda nao encontrado. Tentando busca flexivel em tons de cinza.",
                "orange",
            )
            resultados = localizar_templates(
                templates,
                confianca=confianca_flexivel,
                regiao=regiao_config,
                max_resultados=10,
                parar_score=score_forte,
                escalas=escalas,
                tons_cinza=True,
                stop_event=stop_event,
            )
            avisar(
                status_callback,
                f"Busca flexivel em tons de cinza do alvo '{nome}' retornou {len(resultados)} resultado(s).",
            )
            if deve_parar(stop_event):
                return None

    if not resultados:
        if not usar_variacoes_deteccao(config, alvo_config):
            avisar(
                status_callback,
                f"Alvo '{nome}' nao encontrado. Variacoes de tamanho/cor estao desativadas.",
                "orange",
            )
        return None

    melhor = max(resultados, key=lambda item: float(item.get("score", 0)))
    avisar(
        status_callback,
        f"Melhor alvo '{nome}': x={melhor['x']}, y={melhor['y']}, "
        f"score={melhor['score']:.2f}, escala={float(melhor.get('scale', 1.0)):.2f}.",
    )
    return melhor


def clicar_alvo_visual(
    config,
    nome,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
    regiao=None,
):
    if deve_parar(stop_event):
        return False

    alvo_config = obter_config_alvo_visual(config, nome)
    cache_alvos = obter_cache_execucao(config)["alvos_visuais"]
    cache = cache_alvos.get(nome)
    if cache is not None:
        x = int(cache["x"])
        y = int(cache["y"])
        avisar(
            status_callback,
            f"Usando coordenada em cache para alvo visual '{nome}': x={x}, y={y}.",
        )
    else:
        alvo = localizar_alvo_visual(
            config,
            nome,
            status_callback,
            regiao=regiao,
            stop_event=stop_event,
        )
        if alvo is None:
            return False

        x = int(alvo["x"]) + int(alvo_config.get("click_offset_x", 0))
        y = int(alvo["y"]) + int(alvo_config.get("click_offset_y", 0))
        salvar_cache_alvo_visual(config, nome, x, y, alvo)
        avisar(
            status_callback,
            f"Coordenada do alvo visual '{nome}' salva no cache desta execucao.",
        )

    avisar(status_callback, f"Clicando alvo visual '{nome}': x={x}, y={y}.")
    mover_mouse(x, y)
    if not dormir(config["tempos"]["movimento_mouse"], stop_event):
        return False
    if not garantir_mouse_no_alvo(
        config,
        nome,
        x,
        y,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    ):
        return False
    clicar_mouse()
    return True


def obter_coordenada_alvo_visual(
    config,
    nome,
    status_callback=None,
    regiao=None,
    stop_event=None,
):
    alvo_config = obter_config_alvo_visual(config, nome)
    cache_alvos = obter_cache_execucao(config)["alvos_visuais"]
    cache = cache_alvos.get(nome)
    if cache is not None:
        return int(cache["x"]), int(cache["y"]), True

    alvo = localizar_alvo_visual(
        config,
        nome,
        status_callback,
        regiao=regiao,
        stop_event=stop_event,
    )
    if alvo is None:
        return None, None, False

    x = int(alvo["x"]) + int(alvo_config.get("click_offset_x", 0))
    y = int(alvo["y"]) + int(alvo_config.get("click_offset_y", 0))
    salvar_cache_alvo_visual(config, nome, x, y, alvo)
    return x, y, False


def detectar_alvo_visual_visivel_e_cachear(
    config,
    nome,
    status_callback=None,
    regiao=None,
    stop_event=None,
):
    alvo_config = obter_config_alvo_visual(config, nome)
    alvo = localizar_alvo_visual(
        config,
        nome,
        status_callback=status_callback,
        regiao=regiao,
        stop_event=stop_event,
    )
    if alvo is None:
        return None, None, None

    x = int(alvo["x"]) + int(alvo_config.get("click_offset_x", 0))
    y = int(alvo["y"]) + int(alvo_config.get("click_offset_y", 0))
    salvar_cache_alvo_visual(config, nome, x, y, alvo)
    return x, y, alvo


def abrir_extensao_rewards(
    config,
    coordenadas,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if usar_versao_fixa(config):
        avisar(status_callback, "Abrindo extensao pela versao fixa.")
        return clicar_coordenada(
            config,
            coordenadas,
            "icone_extensao",
            stop_event=stop_event,
            status_callback=status_callback,
            safety_callback=safety_callback,
        )

    avisar(status_callback, "Abrindo extensao por deteccao de imagem.")
    return clicar_alvo_visual(
        config,
        "icone_extensao",
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    )


def voltar_card_rewards(
    config,
    coordenadas,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if usar_versao_fixa(config):
        return clicar_coordenada(
            config,
            coordenadas,
            "voltar",
            stop_event,
            status_callback,
            safety_callback,
        )

    return clicar_alvo_visual(
        config,
        "voltar",
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    )


def garantir_painel_rewards_visivel(
    config,
    coordenadas,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if deve_parar(stop_event):
        return False

    if listar_templates_alvo_visual(config, "exibir_painel"):
        x_exibir, y_exibir, _alvo = detectar_alvo_visual_visivel_e_cachear(
            config,
            "exibir_painel",
            status_callback=status_callback,
            stop_event=stop_event,
        )
        if x_exibir is not None and y_exibir is not None:
            avisar(status_callback, "Painel Rewards ainda esta visivel depois do card.")
            obter_regiao_painel_rewards(config, status_callback)
            return True

    painel_atual = obter_regiao_painel_rewards(
        config,
        status_callback,
        permitir_cache_sem_deteccao=False,
    )
    if painel_atual is not None:
        avisar(
            status_callback,
            "Painel Rewards confirmado pelo detector automatico depois do card.",
        )
        return True

    avisar(
        status_callback,
        "Painel Rewards nao esta visivel depois de voltar do card. Reabrindo a extensao.",
        "orange",
    )
    if not abrir_extensao_rewards(
        config,
        coordenadas,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    ):
        return False

    if not esperar_intervalo(config, "apos_icone_extensao", stop_event, status_callback):
        return False

    estado = detectar_estado_rewards_atual(
        config,
        status_callback=status_callback,
        stop_event=stop_event,
    )
    if estado.get("ok") and str(estado.get("estado", "")).startswith("popup_rewards_ok"):
        avisar(status_callback, "Painel Rewards reaberto com sucesso.", "green")
        return True

    avisar(
        status_callback,
        f"Nao consegui confirmar o painel Rewards apos reabrir: {estado.get('estado')}.",
        "red",
    )
    return False


def alvo_ja_clicado(alvo, alvos_clicados, margem=45):
    return any(
        abs(alvo["x"] - clicado["x"]) <= margem
        and abs(alvo["y"] - clicado["y"]) <= margem
        for clicado in alvos_clicados
    )


def localizar_badges_bonus_por_cor(regiao, status_callback=None):
    if (
        regiao is None
        or capturar_tela is None
        or not VISAO_ARRAY_DISPONIVEL
    ):
        return []

    try:
        imagem, offset_x, offset_y = capturar_tela(regiao)
        arr = np.array(imagem.convert("RGB"))
    except Exception as exc:
        avisar(status_callback, f"Busca de bonus por cor falhou ao capturar painel: {exc}", "orange")
        return []

    altura, largura = arr.shape[:2]
    if altura <= 0 or largura <= 0:
        return []

    inicio_x = max(0, int(largura * 0.58))
    roi = arr[:, inicio_x:largura]
    r = roi[:, :, 0]
    g = roi[:, :, 1]
    b = roi[:, :, 2]
    mask = (
        (r < 85)
        & (g > 70)
        & (g < 175)
        & (b > 75)
        & (b < 190)
        & ((g.astype(np.int16) - r.astype(np.int16)) > 15)
        & ((b.astype(np.int16) - r.astype(np.int16)) > 20)
    ).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)

    num_labels, _labels, stats, _centros = cv2.connectedComponentsWithStats(mask, 8)
    candidatos = []
    for label in range(1, num_labels):
        x, y, width, height, area = stats[label]
        if width < 22 or width > 88:
            continue
        if height < 18 or height > 48:
            continue
        if area < 180:
            continue

        global_x = int(offset_x + inicio_x + x + width / 2)
        global_y = int(offset_y + y + height / 2)
        candidatos.append(
            {
                "x": global_x,
                "y": global_y,
                "width": int(width),
                "height": int(height),
                "score": 0.86,
                "template": "detector_cor_selo_bonus",
            }
        )

    candidatos.sort(key=lambda item: (item["y"], -item["score"]))
    if candidatos:
        avisar(
            status_callback,
            f"Busca de bonus por cor encontrou {len(candidatos)} selo(s) candidato(s).",
        )
    return candidatos


def localizar_alvo_bonus(config, alvos_clicados, status_callback=None, stop_event=None):
    if deve_parar(stop_event):
        return None

    deteccao = obter_config_deteccao(config)
    templates_plus_10 = listar_templates_plus_10(config) if deteccao.get("usar_plus_10", True) else []
    templates_plus_5 = listar_templates_plus_5(config) if deteccao.get("usar_plus_5", True) else []
    templates = templates_plus_10 + templates_plus_5

    if deteccao.get("usar_plus_5", True) and not templates_plus_5:
        avisar(
            status_callback,
            "Atencao: +5 esta ativado, mas nao ha template treinado em treino_plus_5. "
            "Vou depender apenas do detector por cor/geometria para +5.",
            "orange",
        )

    if not templates:
        avisar(status_callback, "Nenhum template +10/+5 disponivel para deteccao.", "orange")
        return None

    avisar(
        status_callback,
        f"Rodando deteccao +10/+5 com {len(templates)} template(s), confianca {float(deteccao['confianca']):.2f}.",
    )
    regiao_deteccao = normalizar_regiao_manual(deteccao.get("regiao"))
    if regiao_deteccao is None and deteccao.get("usar_painel_para_deteccao", True):
        regiao_deteccao = obter_regiao_painel_rewards(config, status_callback)

    if regiao_deteccao is not None:
        avisar(
            status_callback,
            "Busca de bonus limitada ao painel Rewards: "
            f"x={regiao_deteccao['x']}, y={regiao_deteccao['y']}, "
            f"w={regiao_deteccao['width']}, h={regiao_deteccao['height']}.",
        )

    def escolher_alvo(resultados):
        ignorados_clicados = 0
        ignorados_invalidos = 0

        for alvo in resultados:
            if deve_parar(stop_event):
                return None, ignorados_clicados, ignorados_invalidos

            if alvo_ja_clicado(alvo, alvos_clicados):
                ignorados_clicados += 1
                continue

            if deteccao.get("validar_sinal_mais", True):
                valido, detalhes = validar_sinal_mais_no_alvo(alvo)
                if not valido:
                    ignorados_invalidos += 1
                    avisar(
                        status_callback,
                        "Alvo ignorado: parece selo concluido/sem '+'. "
                        f"x={alvo['x']}, y={alvo['y']}, score={alvo['score']:.2f}, "
                        f"motivo={detalhes.get('motivo')}, "
                        f"h={detalhes.get('linha_max')}/{detalhes.get('limite_horizontal')}, "
                        f"v={detalhes.get('coluna_max')}/{detalhes.get('limite_vertical')}.",
                        "orange",
                    )
                    continue

                avisar(
                    status_callback,
                    "Alvo validado como bonus com '+': "
                    f"x={alvo['x']}, y={alvo['y']}, "
                    f"h={detalhes.get('linha_max')}/{detalhes.get('limite_horizontal')}, "
                    f"v={detalhes.get('coluna_max')}/{detalhes.get('limite_vertical')}.",
                )

            avisar(
                status_callback,
                f"Melhor alvo bonus: x={alvo['x']}, y={alvo['y']}, score={alvo['score']:.2f}, template={alvo.get('template')}.",
            )
            return alvo, ignorados_clicados, ignorados_invalidos

        return None, ignorados_clicados, ignorados_invalidos

    resultados = localizar_templates(
        templates,
        confianca=float(deteccao["confianca"]),
        regiao=regiao_deteccao,
        max_resultados=20,
        parar_score=deteccao.get("score_forte", 0.95),
        stop_event=stop_event,
    )
    avisar(status_callback, f"Deteccao retornou {len(resultados)} resultado(s).")
    if deve_parar(stop_event):
        return None

    alvo, ignorados_clicados, ignorados_invalidos = escolher_alvo(resultados)
    if deve_parar(stop_event):
        return None
    if alvo is not None:
        return alvo

    if deteccao.get("score_forte") is not None:
        avisar(
            status_callback,
            "Nenhum bonus novo no primeiro passe. Refazendo busca completa antes de rolar.",
            "orange",
        )
        resultados = localizar_templates(
            templates,
            confianca=float(deteccao["confianca"]),
            regiao=regiao_deteccao,
            max_resultados=20,
            parar_score=None,
            stop_event=stop_event,
        )
        avisar(status_callback, f"Deteccao completa retornou {len(resultados)} resultado(s).")
        if deve_parar(stop_event):
            return None

        alvo, ignorados_clicados, ignorados_invalidos = escolher_alvo(resultados)
        if deve_parar(stop_event):
            return None
        if alvo is not None:
            return alvo

    candidatos_cor = localizar_badges_bonus_por_cor(regiao_deteccao, status_callback)
    if candidatos_cor:
        alvo, ignorados_clicados, ignorados_invalidos = escolher_alvo(candidatos_cor)
        if deve_parar(stop_event):
            return None
        if alvo is not None:
            return alvo

    if usar_variacoes_deteccao(config, deteccao):
        escalas = obter_escalas_flexiveis(deteccao)
        confianca_flexivel = obter_confianca_flexivel(
            deteccao,
            float(deteccao["confianca"]),
        )
        avisar(
            status_callback,
            "Nenhum bonus novo no tamanho original. "
            f"Tentando busca flexivel com escalas {escalas} e confianca {confianca_flexivel:.2f}.",
            "orange",
        )
        resultados = localizar_templates(
            templates,
            confianca=confianca_flexivel,
            regiao=regiao_deteccao,
            max_resultados=20,
            parar_score=None,
            escalas=escalas,
            stop_event=stop_event,
        )
        avisar(status_callback, f"Deteccao flexivel retornou {len(resultados)} resultado(s).")
        if deve_parar(stop_event):
            return None

        alvo, ignorados_clicados, ignorados_invalidos = escolher_alvo(resultados)
        if deve_parar(stop_event):
            return None
        if alvo is not None:
            return alvo

        avisar(
            status_callback,
            "Nenhum bonus novo na busca flexivel colorida. Tentando em tons de cinza.",
            "orange",
        )
        resultados = localizar_templates(
            templates,
            confianca=confianca_flexivel,
            regiao=regiao_deteccao,
            max_resultados=20,
            parar_score=None,
            escalas=escalas,
            tons_cinza=True,
            stop_event=stop_event,
        )
        avisar(status_callback, f"Deteccao flexivel em tons de cinza retornou {len(resultados)} resultado(s).")
        if deve_parar(stop_event):
            return None

        alvo, ignorados_clicados, ignorados_invalidos = escolher_alvo(resultados)
        if deve_parar(stop_event):
            return None
        if alvo is not None:
            return alvo
    else:
        avisar(
            status_callback,
            "Nenhum bonus novo encontrado. Variacoes de tamanho/cor estao desativadas.",
            "orange",
        )

    avisar(
        status_callback,
        "Nenhum bonus novo aproveitavel nesta area "
        f"(ja clicados: {ignorados_clicados}, sem '+': {ignorados_invalidos}).",
        "orange",
    )
    return None


def localizar_alvo_plus_10(config, alvos_clicados, status_callback=None, stop_event=None):
    return localizar_alvo_bonus(config, alvos_clicados, status_callback, stop_event)


def clicar_alvo_detectado(
    config,
    alvo,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if deve_parar(stop_event):
        return False

    deteccao = obter_config_deteccao(config)
    offset_x = int(deteccao["click_offset_x"])
    offset_y = int(deteccao["click_offset_y"])
    x = alvo["x"] + offset_x
    y = alvo["y"] + offset_y

    avisar(
        status_callback,
        f"Movendo mouse para alvo detectado: x={x}, y={y} (offset {offset_x}, {offset_y}).",
    )
    mover_mouse(x, y)
    if not dormir(config["tempos"]["movimento_mouse"], stop_event):
        return False
    if not garantir_mouse_no_alvo(
        config,
        "card_detectado",
        x,
        y,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    ):
        return False
    avisar(status_callback, "Enviando clique no card detectado.")
    clicar_mouse()
    return True


def focar_area_scroll(
    config,
    coordenadas,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    if deve_parar(stop_event):
        return False

    if not usar_versao_fixa(config) and listar_templates_alvo_visual(config, "exibir_painel"):
        avisar(
            status_callback,
            "Focando area de scroll pelo alvo treinado 'Exibir painel'.",
        )
        if clicar_alvo_visual(
            config,
            "exibir_painel",
            stop_event=stop_event,
            status_callback=status_callback,
            safety_callback=safety_callback,
        ):
            return True

        avisar(
            status_callback,
            "Nao consegui usar 'Exibir painel'. Vou tentar pelo painel detectado automaticamente.",
            "orange",
        )

    x, y, painel = obter_alvo_area_scroll(
        config,
        coordenadas,
        status_callback=status_callback,
        para_clique=True,
        stop_event=stop_event,
    )
    if x is None or y is None:
        return False

    if painel is None:
        avisar(status_callback, f"Clicando uma vez para focar a area de scroll: x={x}, y={y}.")
    elif painel.get("origem") == "exibir_painel":
        avisar(status_callback, f"Clicando abaixo de 'Exibir painel' para focar o scroll: x={x}, y={y}.")
    else:
        avisar(
            status_callback,
            f"Clicando uma vez no topo seguro do painel detectado: x={x}, y={y}.",
        )
    mover_mouse(x, y)
    if not dormir(config["tempos"]["movimento_mouse"], stop_event):
        return False
    if not garantir_mouse_no_alvo(
        config,
        "area_scroll",
        x,
        y,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    ):
        return False
    clicar_mouse()
    return True


def posicionar_mouse_area_scroll(
    config,
    coordenadas,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
    estado=None,
    recuperar_callback=None,
):
    if deve_parar(stop_event):
        return False

    x, y, painel = obter_alvo_area_scroll(
        config,
        coordenadas,
        status_callback=status_callback,
        para_clique=False,
        stop_event=stop_event,
    )
    if x is None or y is None:
        return False

    if painel is None:
        avisar(status_callback, f"Movendo mouse para a area de scroll sem clicar: x={x}, y={y}.")
    elif painel.get("origem") == "exibir_painel":
        avisar(status_callback, f"Movendo mouse abaixo de 'Exibir painel': x={x}, y={y}.")
    else:
        avisar(status_callback, f"Movendo mouse para dentro do painel detectado: x={x}, y={y}.")
    mover_mouse(x, y)
    if not dormir(config["tempos"]["movimento_mouse"], stop_event):
        return False
    return garantir_mouse_no_alvo(
        config,
        "area_scroll",
        x,
        y,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
        estado=estado,
        recuperar_callback=recuperar_callback,
    )


def normalizar_regiao_manual(regiao):
    if not regiao:
        return None

    valores = (regiao.get("x"), regiao.get("y"), regiao.get("width"), regiao.get("height"))
    if any(valor is None for valor in valores):
        return None

    x, y, width, height = valores
    if width <= 0 or height <= 0:
        return None

    return {
        "x": int(x),
        "y": int(y),
        "width": int(width),
        "height": int(height),
    }


def limitar_regiao_virtual(x, y, width, height):
    virtual_x, virtual_y, virtual_width, virtual_height = obter_bbox_virtual()
    virtual_right = virtual_x + virtual_width
    virtual_bottom = virtual_y + virtual_height

    left = max(int(x), virtual_x)
    top = max(int(y), virtual_y)
    right = min(int(x + width), virtual_right)
    bottom = min(int(y + height), virtual_bottom)

    if right - left < 80 or bottom - top < 80:
        return None

    return {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }


def ponto_dentro_regiao(x, y, regiao, margem=0):
    if regiao is None:
        return False

    return (
        int(regiao["x"]) - margem <= int(x) <= int(regiao["x"] + regiao["width"]) + margem
        and int(regiao["y"]) - margem <= int(y) <= int(regiao["y"] + regiao["height"]) + margem
    )


def calcular_sobreposicao_regioes(a, b):
    if a is None or b is None:
        return 0.0

    left = max(int(a["x"]), int(b["x"]))
    top = max(int(a["y"]), int(b["y"]))
    right = min(int(a["x"] + a["width"]), int(b["x"] + b["width"]))
    bottom = min(int(a["y"] + a["height"]), int(b["y"] + b["height"]))
    if right <= left or bottom <= top:
        return 0.0

    intersecao = (right - left) * (bottom - top)
    area_a = int(a["width"]) * int(a["height"])
    area_b = int(b["width"]) * int(b["height"])
    menor_area = max(1, min(area_a, area_b))
    return intersecao / menor_area


def regioes_painel_compativeis(referencia, candidato):
    if referencia is None or candidato is None:
        return True

    sobreposicao = calcular_sobreposicao_regioes(referencia, candidato)
    if sobreposicao >= 0.45:
        return True

    centro_ref_x = int(referencia["x"]) + int(referencia["width"]) // 2
    centro_ref_y = int(referencia["y"]) + int(referencia["height"]) // 2
    centro_cand_x = int(candidato["x"]) + int(candidato["width"]) // 2
    centro_cand_y = int(candidato["y"]) + int(candidato["height"]) // 2
    margem_x = max(140, min(int(referencia["width"]), int(candidato["width"])) // 2)
    margem_y = max(180, min(int(referencia["height"]), int(candidato["height"])) // 2)
    return (
        abs(centro_ref_x - centro_cand_x) <= margem_x
        and abs(centro_ref_y - centro_cand_y) <= margem_y
    )


def obter_anchor_exibir_painel(config):
    cache = obter_cache_execucao(config).get("alvos_visuais", {})
    alvo = cache.get("exibir_painel")
    if not alvo:
        return None

    try:
        return int(alvo["x"]), int(alvo["y"])
    except (KeyError, TypeError, ValueError):
        return None


def derivar_regiao_painel_por_exibir_painel(config, status_callback=None):
    anchor = obter_anchor_exibir_painel(config)
    if anchor is None:
        return None

    x, y = anchor
    deteccao = obter_config_deteccao(config)
    largura = int(deteccao.get("painel_anchor_width", 560))
    altura = int(deteccao.get("painel_anchor_height", 1120))
    offset_x = int(deteccao.get("painel_anchor_x_offset", -380))
    offset_y = int(deteccao.get("painel_anchor_y_offset", -280))
    regiao = limitar_regiao_virtual(x + offset_x, y + offset_y, largura, altura)
    if regiao is None:
        return None

    regiao.update(
        {
            "score": None,
            "logo_score": None,
            "close_score": None,
            "light_ratio": None,
            "origem": "exibir_painel_anchor",
        }
    )
    avisar(
        status_callback,
        "Regiao do painel derivada de 'Exibir painel': "
        f"anchor=({x},{y}), x={regiao['x']}, y={regiao['y']}, "
        f"w={regiao['width']}, h={regiao['height']}.",
        "orange",
    )
    return regiao


def obter_regiao_topo_janela_ativa(config=None):
    hwnd = obter_janela_ativa()
    if not janela_windows_valida(hwnd):
        return None

    if config is not None and not janela_parece_edge(hwnd, config.get("navegador", {})):
        return None

    rect = wintypes.RECT()
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None

    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if width <= 0 or height <= 0:
        return None

    return limitar_regiao_virtual(
        int(rect.left),
        int(rect.top),
        width,
        min(190, height),
    )


def obter_regiao_padrao_alvo_visual(nome, config=None):
    virtual_x, virtual_y, virtual_width, virtual_height = obter_bbox_virtual()
    topo_janela = obter_regiao_topo_janela_ativa(config)
    topo = topo_janela or {
        "x": virtual_x,
        "y": virtual_y,
        "width": virtual_width,
        "height": min(190, virtual_height),
    }

    if nome == "icone_extensao":
        largura = min(topo["width"], max(420, int(topo["width"] * 0.38)))
        return {
            "x": int(topo["x"] + topo["width"] - largura),
            "y": int(topo["y"]),
            "width": int(largura),
            "height": int(topo["height"]),
        }

    if nome == "voltar":
        largura = min(topo["width"], max(260, int(topo["width"] * 0.30)))
        return {
            "x": int(topo["x"]),
            "y": int(topo["y"]),
            "width": int(largura),
            "height": int(topo["height"]),
        }

    if nome == "brotato_icone_barra":
        altura = min(150, virtual_height)
        return {
            "x": virtual_x,
            "y": virtual_y + virtual_height - altura,
            "width": virtual_width,
            "height": altura,
        }

    return None


def detectar_painel_automatico_ativado(config):
    deteccao = obter_config_deteccao(config)
    return bool(deteccao.get("detectar_painel_automatico", True))


def cor_hex_para_rgb(valor, padrao=(118, 118, 118)):
    if not isinstance(valor, str):
        return padrao

    texto = valor.strip().lstrip("#")
    if len(texto) != 6:
        return padrao

    try:
        return tuple(int(texto[indice : indice + 2], 16) for indice in (0, 2, 4))
    except ValueError:
        return padrao


def detectar_painel_atual(config, status_callback=None):
    if not detectar_painel_automatico_ativado(config):
        return None

    if detectar_painel_rewards is None:
        avisar(status_callback, "Detector automatico do painel nao esta disponivel.", "orange")
        return None

    try:
        painel = detectar_painel_rewards()
    except Exception as exc:
        avisar(status_callback, f"Falha ao detectar painel Rewards: {exc}", "orange")
        return None

    if painel is None:
        avisar(status_callback, "Painel Rewards nao encontrado automaticamente.", "orange")
        return None

    regiao = limitar_regiao_virtual(
        painel["x"],
        painel["y"],
        painel["width"],
        painel["height"],
    )
    if regiao is None:
        avisar(status_callback, "Painel Rewards detectado ficou fora da area util.", "orange")
        return None

    regiao.update(
        {
            "score": painel.get("score"),
            "logo_score": painel.get("logo_score"),
            "close_score": painel.get("close_score"),
            "light_ratio": painel.get("light_ratio"),
            "origem": painel.get("origem"),
        }
    )
    avisar(
        status_callback,
        "Painel Rewards detectado automaticamente: "
        f"x={regiao['x']}, y={regiao['y']}, "
        f"w={regiao['width']}, h={regiao['height']}, "
        f"score={float(regiao.get('score') or 0):.2f}, "
        f"origem={regiao.get('origem')}, "
        f"logo={float(regiao.get('logo_score') or 0):.2f}, "
        f"fechar={float(regiao.get('close_score') or 0):.2f}.",
    )
    return regiao


def obter_regiao_painel_rewards(config, status_callback=None, permitir_cache_sem_deteccao=True):
    anchor = obter_anchor_exibir_painel(config)
    painel_cache = obter_cache_painel_rewards(config)
    painel = detectar_painel_atual(config, status_callback)
    if painel is not None:
        if painel_cache is not None and not regioes_painel_compativeis(painel_cache, painel):
            avisar(
                status_callback,
                "Painel detectado automaticamente mudou para uma regiao distante. "
                f"Detectado=({painel['x']},{painel['y']},{painel['width']},{painel['height']}), "
                f"cache=({painel_cache['x']},{painel_cache['y']},{painel_cache['width']},{painel_cache['height']}). "
                "Vou ignorar esse salto para evitar scroll fora do Rewards.",
                "orange",
            )
            painel_anchor = derivar_regiao_painel_por_exibir_painel(config, status_callback)
            if painel_anchor is not None:
                return salvar_cache_painel_rewards(config, painel_anchor)
            return painel_cache if permitir_cache_sem_deteccao else None

        if anchor is not None and not ponto_dentro_regiao(anchor[0], anchor[1], painel, margem=80):
            avisar(
                status_callback,
                "Painel detectado automaticamente nao contem o ponto de 'Exibir painel'. "
                f"Painel=({painel['x']},{painel['y']},{painel['width']},{painel['height']}), "
                f"anchor=({anchor[0]},{anchor[1]}). Vou ignorar esse painel.",
                "orange",
            )
            painel_anchor = derivar_regiao_painel_por_exibir_painel(config, status_callback)
            if painel_anchor is not None:
                return salvar_cache_painel_rewards(config, painel_anchor)
            return None

        return salvar_cache_painel_rewards(config, painel)

    painel_anchor = derivar_regiao_painel_por_exibir_painel(config, status_callback)
    if painel_anchor is not None:
        return salvar_cache_painel_rewards(config, painel_anchor)

    if painel_cache is not None and permitir_cache_sem_deteccao:
        avisar(
            status_callback,
            "Detector automatico nao encontrou painel agora. Mantendo ultima regiao Rewards confiavel em cache.",
            "orange",
        )
        return painel_cache

    return None


def obter_alvo_area_scroll(
    config,
    coordenadas,
    status_callback=None,
    para_clique=False,
    stop_event=None,
):
    if deve_parar(stop_event):
        return None, None, None

    if not usar_versao_fixa(config) and listar_templates_alvo_visual(config, "exibir_painel"):
        x, y, cache = obter_coordenada_alvo_visual(
            config,
            "exibir_painel",
            status_callback=status_callback,
            stop_event=stop_event,
        )
        if x is not None and y is not None:
            origem = "cache" if cache else "deteccao"
            avisar(
                status_callback,
                f"Area de scroll ancorada em 'Exibir painel' ({origem}): x={x}, y={y}.",
            )
            return int(x), int(y), {"origem": "exibir_painel"}

        avisar(
            status_callback,
            "Template 'Exibir painel' existe, mas nao foi localizado. Usando detector automatico do painel.",
            "orange",
        )

    painel = obter_regiao_painel_rewards(config, status_callback)
    if painel is not None:
        if para_clique:
            x = painel["x"] + max(60, painel["width"] - 90)
            y = painel["y"] + min(34, max(20, painel["height"] // 12))
        else:
            x = painel["x"] + max(70, min(painel["width"] - 55, painel["width"] // 2))
            y = painel["y"] + max(120, min(painel["height"] - 80, painel["height"] // 2))

        return int(x), int(y), painel

    if not usar_versao_fixa(config):
        avisar(
            status_callback,
            "Painel Rewards nao foi detectado. A nova versao nao vai usar coordenada fixa para scroll.",
            "red",
        )
        return None, None, None

    x, y = coordenadas["double_click_scroll"]
    validar_coordenada("double_click_scroll", x, y)
    return int(x), int(y), None


def obter_regiao_detector_fim_scroll(config, coordenadas, status_callback=None):
    deteccao = obter_config_deteccao(config)
    if deteccao.get("usar_painel_para_scroll", True):
        painel = obter_regiao_painel_rewards(config, status_callback)
        if painel is not None:
            return painel
        if not usar_versao_fixa(config):
            return None

    regiao_manual = normalizar_regiao_manual(deteccao.get("scroll_end_region"))
    if regiao_manual is not None:
        return regiao_manual

    x, y = coordenadas["double_click_scroll"]
    validar_coordenada("double_click_scroll", x, y)

    width = int(deteccao.get("scroll_end_width", 700))
    height = int(deteccao.get("scroll_end_height", 850))
    x_offset = int(deteccao.get("scroll_end_x_offset", -620))
    y_offset = int(deteccao.get("scroll_end_y_offset", -360))

    return limitar_regiao_virtual(x + x_offset, y + y_offset, width, height)


def capturar_assinatura_scroll(config, coordenadas, status_callback=None):
    regiao = obter_regiao_detector_fim_scroll(config, coordenadas, status_callback)
    if regiao is None:
        avisar(status_callback, "Nao consegui montar regiao para detector de fim do scroll.", "orange")
        return None, None

    imagem, _, _ = capturar_tela(regiao)
    proporcao = regiao["height"] / max(1, regiao["width"])
    assinatura = imagem.convert("L").resize((160, max(80, int(160 * proporcao))))
    thumb = None
    deteccao = obter_config_deteccao(config)
    if deteccao.get("usar_scrollbar_por_cor", True) and detectar_scrollbar_thumb_em_imagem is not None:
        thumb = detectar_scrollbar_thumb_em_imagem(
            imagem,
            regiao["x"],
            regiao["y"],
            cor=cor_hex_para_rgb(deteccao.get("scrollbar_color", "#767676")),
            tolerancia=int(deteccao.get("scrollbar_tolerance", 28)),
            altura_min=int(deteccao.get("scrollbar_min_height", 35)),
        )

    estado = {
        "assinatura": assinatura,
        "regiao": regiao,
        "thumb": thumb,
    }
    return estado, regiao


def calcular_diferenca_scroll(antes, depois):
    diferenca = ImageChops.difference(antes, depois)
    estatistica = ImageStat.Stat(diferenca)
    return float(estatistica.mean[0])


def analisar_estado_scroll(config, antes, depois, direcao, status_callback=None):
    deteccao = obter_config_deteccao(config)
    thumb_antes = antes.get("thumb") if antes else None
    thumb_depois = depois.get("thumb") if depois else None
    regiao = depois.get("regiao") if depois else None

    if thumb_antes is not None and thumb_depois is not None and regiao is not None:
        delta = int(thumb_depois["center_y"] - thumb_antes["center_y"])
        delta_min = int(deteccao.get("scrollbar_min_delta", 2))
        margem_fim = int(deteccao.get("scrollbar_end_margin", 12))
        top_regiao = regiao["y"]
        bottom_regiao = regiao["y"] + regiao["height"]
        no_fim_baixo = thumb_depois["bottom"] >= bottom_regiao - margem_fim
        no_fim_topo = thumb_depois["y"] <= top_regiao + margem_fim
        moveu_thumb = abs(delta) > delta_min
        fim_scroll = not moveu_thumb

        if direcao < 0 and no_fim_baixo:
            fim_scroll = True
        elif direcao > 0 and no_fim_topo:
            fim_scroll = True

        avisar(
            status_callback,
            "Scroll interno detectado por barra cinza: "
            f"antes_y={thumb_antes['center_y']}, depois_y={thumb_depois['center_y']}, "
            f"delta={delta}, fim={fim_scroll}.",
        )
        if fim_scroll:
            avisar(status_callback, "Detector da barra interna indicou fim do scroll.", "orange")

        return {
            "fim_scroll": fim_scroll,
            "mudou": moveu_thumb,
            "diferenca": float(delta),
            "modo": "scrollbar",
        }

    if deteccao.get("usar_scrollbar_por_cor", True) and deteccao.get("usar_painel_para_scroll", True):
        avisar(
            status_callback,
            "Nao consegui confirmar a barra interna do painel. "
            "Nao vou declarar fim do scroll usando apenas mudanca visual da pagina.",
            "orange",
        )
        return {
            "fim_scroll": False,
            "mudou": True,
            "diferenca": None,
            "modo": "scrollbar_indisponivel",
        }

    if antes is None or depois is None:
        return {
            "fim_scroll": False,
            "mudou": True,
            "diferenca": None,
            "modo": "indisponivel",
        }

    assinatura_antes = antes.get("assinatura")
    assinatura_depois = depois.get("assinatura")
    if assinatura_antes is None or assinatura_depois is None:
        return {
            "fim_scroll": False,
            "mudou": True,
            "diferenca": None,
            "modo": "indisponivel",
        }

    diferenca = calcular_diferenca_scroll(assinatura_antes, assinatura_depois)
    limite = float(deteccao.get("scroll_end_threshold", 1.0))
    fim_scroll = diferenca <= limite
    mudou = not fim_scroll
    avisar(
        status_callback,
        f"Diferenca visual do painel apos scroll: {diferenca:.2f} (fim se <= {limite:.2f}).",
    )
    if fim_scroll:
        avisar(status_callback, "Detector visual do painel indicou fim do scroll.", "orange")

    return {
        "fim_scroll": fim_scroll,
        "mudou": mudou,
        "diferenca": diferenca,
        "modo": "visual_painel",
    }


def painel_extensao_parece_visivel(config, coordenadas, status_callback=None):
    try:
        painel = obter_regiao_painel_rewards(config, status_callback)
        if painel is not None:
            avisar(status_callback, "Painel Rewards visivel pelo detector automatico.")
            return True

        if not usar_versao_fixa(config):
            return False

        x, y = coordenadas["double_click_scroll"]
        regiao = limitar_regiao_virtual(x - 420, y - 280, 520, 700)
        if regiao is None:
            return False

        imagem, _, _ = capturar_tela(regiao)
        cinza = imagem.convert("L")
        histograma = cinza.histogram()
        total = max(1, sum(histograma))
        branco_ratio = sum(histograma[220:]) / total
        media = ImageStat.Stat(cinza).mean[0]
        visivel = branco_ratio >= 0.18 or media >= 155
        avisar(
            status_callback,
            "Check painel Rewards: "
            f"branco={branco_ratio:.2f}, media={media:.1f}, visivel={visivel}.",
        )
        return visivel
    except Exception as exc:
        avisar(status_callback, f"Nao consegui checar se a extensao esta visivel: {exc}", "orange")
        return False


def rolar_sem_checks(config, stop_event=None, status_callback=None, total_ticks=None):
    deteccao = obter_config_deteccao(config)
    scroll_total = int(deteccao["scroll_amount"])
    if scroll_total == 0:
        return dormir(0.15, stop_event)

    direcao = 1 if scroll_total > 0 else -1
    total_passos = abs(scroll_total) if total_ticks is None else int(total_ticks)
    for indice in range(1, total_passos + 1):
        if deve_parar(stop_event):
            return False
        avisar(status_callback, f"Replay scroll {indice}/{total_passos}.")
        rolar_mouse(direcao)
        if not dormir(0.12, stop_event):
            return False

    return dormir(0.25, stop_event)


def recuperar_estado_scroll(
    config,
    coordenadas,
    scrolls_concluidos,
    ticks_parciais=0,
    stop_event=None,
    status_callback=None,
):
    avisar(
        status_callback,
        "Recuperando estado da extensao com "
        f"{scrolls_concluidos} scroll(s) concluido(s) e {ticks_parciais} tick(s) parcial(is).",
        "orange",
    )

    if obter_config_seguranca(config).get("reabrir_extensao_ao_continuar", True):
        if not painel_extensao_parece_visivel(config, coordenadas, status_callback):
            avisar(status_callback, "Painel nao parece visivel. Clicando no icone da extensao.")
            if not abrir_extensao_rewards(
                config,
                coordenadas,
                stop_event=stop_event,
                status_callback=status_callback,
                safety_callback=None,
            ):
                return False
            if not esperar_intervalo(
                config,
                "apos_icone_extensao",
                stop_event,
                status_callback,
            ):
                return False
        else:
            avisar(status_callback, "Painel parece visivel. Nao vou clicar no icone para evitar fechar.")

    if not focar_area_scroll(
        config,
        coordenadas,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=None,
    ):
        return False

    if not posicionar_mouse_area_scroll(
        config,
        coordenadas,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=None,
    ):
        return False

    for indice in range(1, int(scrolls_concluidos) + 1):
        avisar(status_callback, f"Restaurando posicao do painel: scroll {indice}/{scrolls_concluidos}.")
        if not rolar_sem_checks(config, stop_event, status_callback):
            return False

    if int(ticks_parciais) > 0:
        avisar(status_callback, f"Restaurando ticks parciais: {ticks_parciais}.")
        if not rolar_sem_checks(config, stop_event, status_callback, total_ticks=ticks_parciais):
            return False

    avisar(status_callback, "Estado do painel restaurado. Continuando fluxo.")
    return True


def rolar_area_extensao(
    config,
    coordenadas,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
    estado=None,
    recuperar_callback=None,
):
    if deve_parar(stop_event):
        return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

    deteccao = obter_config_deteccao(config)
    detectar_fim = bool(deteccao.get("detectar_fim_scroll", True))
    estado_antes_detector = None
    regiao_detector = None

    if not posicionar_mouse_area_scroll(
        config,
        coordenadas,
        stop_event,
        status_callback,
        safety_callback,
        estado,
        recuperar_callback,
    ):
        return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

    x, y = get_mouse_position()

    if deteccao.get("usar_painel_para_scroll", True):
        painel_mouse = obter_regiao_painel_rewards(config, status_callback)
        if painel_mouse is not None and not ponto_dentro_regiao(x, y, painel_mouse, margem=40):
            avisar(
                status_callback,
                "Mouse nao esta dentro do painel Rewards antes do scroll. "
                f"mouse=({x},{y}); painel=({painel_mouse['x']},{painel_mouse['y']},"
                f"{painel_mouse['width']},{painel_mouse['height']}).",
                "red",
            )
            return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

    if detectar_fim:
        try:
            estado_antes_detector, regiao_detector = capturar_assinatura_scroll(
                config,
                coordenadas,
                status_callback,
            )
            if regiao_detector is not None:
                avisar(
                    status_callback,
                    "Detector de fim do scroll usando regiao "
                    f"x={regiao_detector['x']}, y={regiao_detector['y']}, "
                    f"w={regiao_detector['width']}, h={regiao_detector['height']}.",
                )
        except Exception as exc:
            avisar(status_callback, f"Detector de fim do scroll falhou antes do scroll: {exc}", "orange")

    scroll_total = int(deteccao["scroll_amount"])
    if scroll_total == 0:
        avisar(status_callback, "Scroll configurado como 0. Apenas aguardando painel.")
        ok = dormir(0.4, stop_event)
        return {"ok": ok, "fim_scroll": False, "mudou": False, "diferenca": None}

    direcao = 1 if scroll_total > 0 else -1
    avisar(status_callback, f"Rolando mouse em {abs(scroll_total)} passo(s), direcao={direcao}.")
    total_passos = abs(scroll_total)
    if estado is not None:
        estado["ticks_parciais"] = 0
    for indice in range(1, total_passos + 1):
        if deve_parar(stop_event):
            return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

        if not garantir_mouse_no_alvo(
            config,
            "area_scroll",
            x,
            y,
            stop_event=stop_event,
            status_callback=status_callback,
            safety_callback=safety_callback,
            estado=estado,
            recuperar_callback=recuperar_callback,
        ):
            return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}
        avisar(status_callback, f"Scroll do mouse {indice}/{total_passos}.")
        rolar_mouse(direcao)
        if not dormir(0.18, stop_event):
            return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}
        if estado is not None:
            estado["ticks_parciais"] = indice

    if not dormir(0.45, stop_event):
        return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

    fim_scroll = False
    mudou = True
    diferenca = None
    modo_detector = None
    if detectar_fim and estado_antes_detector is not None:
        try:
            estado_depois_detector, _ = capturar_assinatura_scroll(config, coordenadas, status_callback)
            analise = analisar_estado_scroll(
                config,
                estado_antes_detector,
                estado_depois_detector,
                direcao,
                status_callback,
            )
            fim_scroll = bool(analise["fim_scroll"])
            mudou = bool(analise["mudou"])
            diferenca = analise.get("diferenca")
            modo_detector = analise.get("modo")
        except Exception as exc:
            avisar(status_callback, f"Detector de fim do scroll falhou depois do scroll: {exc}", "orange")

    return {
        "ok": True,
        "fim_scroll": fim_scroll,
        "mudou": mudou,
        "diferenca": diferenca,
        "modo_detector": modo_detector,
    }


def executar_cards_por_imagem(
    config,
    coordenadas,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    deteccao = obter_config_deteccao(config)

    if not deteccao.get("ativada", False):
        return None

    if not DETECCAO_IMAGEM_DISPONIVEL:
        avisar(status_callback, "Deteccao de imagem indisponivel. Verifique OpenCV/Pillow.", "red")
        return None

    templates = listar_templates_bonus(config)
    if not templates:
        avisar(
            status_callback,
            "Nenhum template +10/+5 encontrado. Capture ou treine primeiro.",
            "orange",
        )
        return None

    max_cards = max(0, int(deteccao["max_cards"]))
    limite_scrolls = int(deteccao.get("max_scrolls", 40))
    alvos_clicados = []
    cards_executados = 0
    scrolls = 0
    estado_scroll = {"scrolls_concluidos": 0, "ticks_parciais": 0, "cards_executados": 0}

    def recuperar_scroll_atual():
        return recuperar_estado_scroll(
            config,
            coordenadas,
            estado_scroll["scrolls_concluidos"],
            ticks_parciais=estado_scroll.get("ticks_parciais", 0),
            stop_event=stop_event,
            status_callback=status_callback,
        )

    avisar(
        status_callback,
        f"Rolando painel e procurando cards com +10/+5 ate o fim do scroll (limite de seguranca: {limite_scrolls}).",
    )

    if not focar_area_scroll(config, coordenadas, stop_event, status_callback, safety_callback):
        return False

    fim_scroll_detectado = False
    conferindo_apos_card = False
    while True:
        if deve_parar(stop_event):
            return False

        if conferindo_apos_card:
            avisar(
                status_callback,
                "Voltamos do card. Procurando outro +10/+5 na mesma area antes de rolar ou finalizar...",
            )
        else:
            avisar(status_callback, "Procurando +10/+5 na area visivel antes de rolar...")
        alvo = localizar_alvo_bonus(
            config,
            alvos_clicados,
            status_callback,
            stop_event=stop_event,
        )
        if alvo is not None:
            if max_cards and cards_executados >= max_cards:
                avisar(
                    status_callback,
                    "Ainda existe bonus visivel, mas o limite de seguranca de cards "
                    f"foi atingido ({max_cards}). Aumente 'Max cards' para executar mais.",
                    "orange",
                )
                break

            conferindo_apos_card = False
            cards_executados += 1
            estado_scroll["cards_executados"] = cards_executados
            alvos_clicados.append({"x": alvo["x"], "y": alvo["y"]})

            avisar(
                status_callback,
                f"Card bonus encontrado ({cards_executados}/{max_cards}). Clicando...",
            )
            if not clicar_alvo_detectado(config, alvo, stop_event, status_callback, safety_callback):
                return False

            if not esperar_intervalo(config, "apos_card_detectado", stop_event, status_callback):
                return False

            if not voltar_card_rewards(
                config,
                coordenadas,
                stop_event,
                status_callback,
                safety_callback,
            ):
                return False

            if not esperar_intervalo(
                config,
                "apos_voltar_card_detectado",
                stop_event,
                status_callback,
            ):
                return False

            if not garantir_painel_rewards_visivel(
                config,
                coordenadas,
                stop_event=stop_event,
                status_callback=status_callback,
                safety_callback=safety_callback,
            ):
                return False

            avisar(status_callback, "Painel Rewards confirmado depois de voltar do card.")
            conferindo_apos_card = True
            continue

        if conferindo_apos_card:
            avisar(status_callback, "Nenhum outro +10/+5 encontrado na mesma area apos voltar.")
            conferindo_apos_card = False

        if fim_scroll_detectado:
            avisar(status_callback, "Fim do scroll detectado e nenhum +10/+5 novo encontrado.", "orange")
            break

        if max_cards and cards_executados >= max_cards:
            avisar(
                status_callback,
                f"Limite de seguranca de cards atingido ({max_cards}) depois de conferir a area atual.",
                "orange",
            )
            break

        if scrolls >= limite_scrolls:
            avisar(
                status_callback,
                f"Limite de seguranca de scrolls atingido ({limite_scrolls}). Encerrando busca.",
                "orange",
            )
            break

        avisar(status_callback, "Nenhum +10/+5 visivel nesta posicao. Agora vou rolar.")
        scrolls += 1
        avisar(status_callback, f"Rolando painel ({scrolls}/{limite_scrolls})...")
        resultado_scroll = rolar_area_extensao(
            config,
            coordenadas,
            stop_event,
            status_callback,
            safety_callback,
            estado_scroll,
            recuperar_scroll_atual,
        )
        if not resultado_scroll["ok"]:
            return False

        if resultado_scroll.get("mudou"):
            estado_scroll["scrolls_concluidos"] += 1
            alvos_clicados = []
        estado_scroll["ticks_parciais"] = 0
        fim_scroll_detectado = bool(resultado_scroll.get("fim_scroll"))
        if (
            fim_scroll_detectado
            and resultado_scroll.get("modo_detector") == "visual_painel"
            and scrolls < int(deteccao.get("scroll_visual_min_scrolls", 2))
        ):
            avisar(
                status_callback,
                "Detector visual indicou fim cedo demais. Vou ignorar e tentar mais scrolls.",
                "orange",
            )
            fim_scroll_detectado = False

    if cards_executados == 0:
        avisar(status_callback, "Nenhum card com +10/+5 encontrado. Seguindo sem clicar.", "orange")
    else:
        avisar(status_callback, f"{cards_executados} card(s) bonus executado(s).", "green")

    return True


def executar_cards_por_coordenadas(
    config,
    coordenadas,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
):
    avisar(status_callback, "Abrindo area dos cards...")
    if not double_click_coordenada(
        config,
        coordenadas,
        "double_click_scroll",
        stop_event,
        status_callback,
        safety_callback,
    ):
        return False
    if not esperar_intervalo(config, "apos_double_click_scroll", stop_event, status_callback):
        return False

    avisar(status_callback, "Executando card 1...")
    if not clicar_coordenada(config, coordenadas, "card_1", stop_event, status_callback, safety_callback):
        return False
    if not esperar_intervalo(config, "apos_card_1", stop_event, status_callback):
        return False

    if not clicar_coordenada(config, coordenadas, "voltar", stop_event, status_callback, safety_callback):
        return False

    avisar(status_callback, "Executando card 2...")
    if not clicar_coordenada(config, coordenadas, "card_2", stop_event, status_callback, safety_callback):
        return False
    if not esperar_intervalo(config, "apos_card_2", stop_event, status_callback):
        return False

    if not clicar_coordenada(config, coordenadas, "voltar", stop_event, status_callback, safety_callback):
        return False
    if not esperar_intervalo(config, "apos_voltar_card_2", stop_event, status_callback):
        return False

    avisar(status_callback, "Executando card 3...")
    if not clicar_coordenada(config, coordenadas, "card_3", stop_event, status_callback, safety_callback):
        return False
    if not esperar_intervalo(config, "apos_card_3", stop_event, status_callback):
        return False

    return clicar_coordenada(config, coordenadas, "voltar", stop_event, status_callback, safety_callback)


def avisar(status_callback, mensagem, cor="blue"):
    if status_callback is not None:
        status_callback(mensagem, cor)


def executar_fluxo_inicial(
    config,
    coordenadas=None,
    stop_event=None,
    status_callback=None,
    safety_callback=None,
    edge_ja_aberto=False,
    painel_ja_aberto=False,
):
    if coordenadas is None:
        coordenadas = carregar_coordenadas(config)

    if edge_ja_aberto:
        avisar(status_callback, "Edge ja esta aberto. Pulando nova abertura do navegador.")
    else:
        avisar(status_callback, "Abrindo o Microsoft Edge...")
        if not abrir_edge(config, stop_event, status_callback):
            return False

    if painel_ja_aberto:
        avisar(status_callback, "Painel Rewards ja esta aberto e validado. Pulando clique no icone da extensao.")
    else:
        avisar(status_callback, "Clicando no icone da extensao...")
        if not abrir_extensao_rewards(
            config,
            coordenadas,
            stop_event,
            status_callback,
            safety_callback,
        ):
            return False
        if not esperar_intervalo(config, "apos_icone_extensao", stop_event, status_callback):
            return False

    resultado_imagem = executar_cards_por_imagem(
        config,
        coordenadas,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    )

    if resultado_imagem is not None:
        return resultado_imagem

    if not usar_versao_fixa(config):
        avisar(
            status_callback,
            "Versao por imagem ativa e nao foi possivel executar por deteccao. Treine os alvos necessarios.",
            "red",
        )
        return False

    if not obter_config_deteccao(config).get("usar_fallback_coordenadas", True):
        return False

    avisar(status_callback, "Usando fluxo antigo por coordenadas...", "orange")
    return executar_cards_por_coordenadas(
        config,
        coordenadas,
        stop_event=stop_event,
        status_callback=status_callback,
        safety_callback=safety_callback,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Automacao inicial: abre o Edge e executa cliques configurados."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Caminho do arquivo JSON de configuracao.",
    )
    args = parser.parse_args()

    config = carregar_config(args.config)
    coordenadas = carregar_coordenadas(config)

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05

    executar_fluxo_inicial(config, coordenadas)
    print("Fluxo concluido.")


if __name__ == "__main__":
    main()
