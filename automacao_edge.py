import argparse
import json
import random
import time
from pathlib import Path

from PIL import ImageChops, ImageStat

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
        localizar_templates,
        mover_mouse,
        obter_bbox_virtual,
        rolar_mouse,
    )

    DETECCAO_IMAGEM_DISPONIVEL = True
except Exception:
    capturar_tela = None
    clicar_mouse = None
    localizar_templates = None
    mover_mouse = None
    obter_bbox_virtual = None
    rolar_mouse = None
    DETECCAO_IMAGEM_DISPONIVEL = False


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "config.json"


def carregar_config(caminho_config):
    with caminho_config.open("r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def obter_coordenada(coordenadas, nome):
    return coordenadas[nome]["x"], coordenadas[nome]["y"]


def deve_parar(stop_event):
    return stop_event is not None and stop_event.is_set()


def dormir(segundos, stop_event=None):
    fim = time.time() + segundos
    while time.time() < fim:
        if deve_parar(stop_event):
            return False
        time.sleep(min(0.1, fim - time.time()))
    return True


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
    return dormir(tempos["apos_enter"], stop_event)


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


def clicar_coordenada(config, coordenadas, nome, stop_event=None, status_callback=None):
    if deve_parar(stop_event):
        return False

    x, y = coordenadas[nome]
    validar_coordenada(nome, x, y)

    avisar(status_callback, f"Movendo mouse para '{nome}': x={x}, y={y}.")
    mover_mouse(x, y)
    if not dormir(config["tempos"]["movimento_mouse"], stop_event):
        return False
    avisar(status_callback, f"Enviando clique em '{nome}'.")
    clicar_mouse()
    return True


def double_click_coordenada(config, coordenadas, nome, stop_event=None, status_callback=None):
    if deve_parar(stop_event):
        return False

    x, y = coordenadas[nome]
    validar_coordenada(nome, x, y)

    avisar(status_callback, f"Movendo mouse para double click '{nome}': x={x}, y={y}.")
    mover_mouse(x, y)
    if not dormir(config["tempos"]["movimento_mouse"], stop_event):
        return False
    avisar(status_callback, f"Enviando primeiro clique em '{nome}'.")
    clicar_mouse()
    if not dormir(0.05, stop_event):
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
        },
    )


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


def alvo_ja_clicado(alvo, alvos_clicados, margem=45):
    return any(
        abs(alvo["x"] - clicado["x"]) <= margem
        and abs(alvo["y"] - clicado["y"]) <= margem
        for clicado in alvos_clicados
    )


def localizar_alvo_plus_10(config, alvos_clicados, status_callback=None):
    deteccao = obter_config_deteccao(config)
    templates = listar_templates_plus_10(config)

    if not templates:
        avisar(status_callback, "Nenhum template +10 disponivel para deteccao.", "orange")
        return None

    avisar(
        status_callback,
        f"Rodando deteccao com {len(templates)} template(s), confianca {float(deteccao['confianca']):.2f}.",
    )
    resultados = localizar_templates(
        templates,
        confianca=float(deteccao["confianca"]),
        regiao=deteccao.get("regiao"),
        max_resultados=20,
    )
    avisar(status_callback, f"Deteccao retornou {len(resultados)} resultado(s).")

    for alvo in resultados:
        if not alvo_ja_clicado(alvo, alvos_clicados):
            avisar(
                status_callback,
                f"Melhor alvo +10: x={alvo['x']}, y={alvo['y']}, score={alvo['score']:.2f}.",
            )
            return alvo

    avisar(status_callback, "Todos os alvos encontrados ja foram clicados nessa execucao.")
    return None


def clicar_alvo_detectado(config, alvo, stop_event=None, status_callback=None):
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
    avisar(status_callback, "Enviando clique no card detectado.")
    clicar_mouse()
    return True


def focar_area_scroll(config, coordenadas, stop_event=None, status_callback=None):
    if deve_parar(stop_event):
        return False

    x, y = coordenadas["double_click_scroll"]
    validar_coordenada("double_click_scroll", x, y)

    avisar(status_callback, f"Clicando uma vez para focar a area de scroll: x={x}, y={y}.")
    clicar_mouse(x, y)
    return dormir(config["tempos"]["movimento_mouse"], stop_event)


def posicionar_mouse_area_scroll(config, coordenadas, stop_event=None, status_callback=None):
    if deve_parar(stop_event):
        return False

    x, y = coordenadas["double_click_scroll"]
    validar_coordenada("double_click_scroll", x, y)

    avisar(status_callback, f"Movendo mouse para a area de scroll sem clicar: x={x}, y={y}.")
    mover_mouse(x, y)
    return dormir(config["tempos"]["movimento_mouse"], stop_event)


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


def obter_regiao_detector_fim_scroll(config, coordenadas):
    deteccao = obter_config_deteccao(config)
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
    regiao = obter_regiao_detector_fim_scroll(config, coordenadas)
    if regiao is None:
        avisar(status_callback, "Nao consegui montar regiao para detector de fim do scroll.", "orange")
        return None, None

    imagem, _, _ = capturar_tela(regiao)
    proporcao = regiao["height"] / max(1, regiao["width"])
    assinatura = imagem.convert("L").resize((160, max(80, int(160 * proporcao))))
    return assinatura, regiao


def calcular_diferenca_scroll(antes, depois):
    diferenca = ImageChops.difference(antes, depois)
    estatistica = ImageStat.Stat(diferenca)
    return float(estatistica.mean[0])


def rolar_area_extensao(config, coordenadas, stop_event=None, status_callback=None):
    if deve_parar(stop_event):
        return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

    deteccao = obter_config_deteccao(config)
    detectar_fim = bool(deteccao.get("detectar_fim_scroll", True))
    assinatura_antes = None
    regiao_detector = None

    if not posicionar_mouse_area_scroll(config, coordenadas, stop_event, status_callback):
        return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

    if detectar_fim:
        try:
            assinatura_antes, regiao_detector = capturar_assinatura_scroll(
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
    for indice in range(1, total_passos + 1):
        if deve_parar(stop_event):
            return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

        avisar(status_callback, f"Scroll do mouse {indice}/{total_passos}.")
        rolar_mouse(direcao)
        if not dormir(0.18, stop_event):
            return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

    if not dormir(0.45, stop_event):
        return {"ok": False, "fim_scroll": False, "mudou": False, "diferenca": None}

    fim_scroll = False
    mudou = True
    diferenca = None
    if detectar_fim and assinatura_antes is not None:
        try:
            assinatura_depois, _ = capturar_assinatura_scroll(config, coordenadas, status_callback)
            if assinatura_depois is not None:
                diferenca = calcular_diferenca_scroll(assinatura_antes, assinatura_depois)
                limite = float(deteccao.get("scroll_end_threshold", 1.0))
                fim_scroll = diferenca <= limite
                mudou = not fim_scroll
                avisar(
                    status_callback,
                    f"Diferenca visual apos scroll: {diferenca:.2f} (fim se <= {limite:.2f}).",
                )
                if fim_scroll:
                    avisar(status_callback, "Detector indicou fim do scroll.", "orange")
        except Exception as exc:
            avisar(status_callback, f"Detector de fim do scroll falhou depois do scroll: {exc}", "orange")

    return {
        "ok": True,
        "fim_scroll": fim_scroll,
        "mudou": mudou,
        "diferenca": diferenca,
    }


def executar_cards_por_imagem(config, coordenadas, stop_event=None, status_callback=None):
    deteccao = obter_config_deteccao(config)

    if not deteccao.get("ativada", False):
        return None

    if not DETECCAO_IMAGEM_DISPONIVEL:
        avisar(status_callback, "Deteccao de imagem indisponivel. Verifique OpenCV/Pillow.", "red")
        return None

    templates = listar_templates_plus_10(config)
    if not templates:
        avisar(
            status_callback,
            "Nenhum template +10 encontrado. Capture ou treine primeiro.",
            "orange",
        )
        return None

    max_cards = int(deteccao["max_cards"])
    limite_scrolls = int(deteccao.get("max_scrolls", 40))
    alvos_clicados = []
    cards_executados = 0
    scrolls = 0

    avisar(
        status_callback,
        f"Rolando painel e procurando cards com +10 ate o fim do scroll (limite de seguranca: {limite_scrolls}).",
    )

    if not focar_area_scroll(config, coordenadas, stop_event, status_callback):
        return False

    while cards_executados < max_cards:
        if deve_parar(stop_event):
            return False

        if scrolls >= limite_scrolls:
            avisar(
                status_callback,
                f"Limite de seguranca de scrolls atingido ({limite_scrolls}). Encerrando busca.",
                "orange",
            )
            break

        scrolls += 1
        avisar(status_callback, f"Rolando painel ({scrolls}/{limite_scrolls})...")
        resultado_scroll = rolar_area_extensao(config, coordenadas, stop_event, status_callback)
        if not resultado_scroll["ok"]:
            return False

        if resultado_scroll.get("mudou"):
            alvos_clicados = []

        avisar(status_callback, "Procurando +10 na area visivel...")
        alvo = localizar_alvo_plus_10(config, alvos_clicados, status_callback)
        if alvo is None:
            if resultado_scroll.get("fim_scroll"):
                avisar(status_callback, "Fim do scroll detectado e nenhum +10 novo encontrado.", "orange")
                break

            avisar(status_callback, "Nenhum +10 encontrado depois desse scroll.", "orange")
            continue

        cards_executados += 1
        alvos_clicados.append({"x": alvo["x"], "y": alvo["y"]})

        avisar(
            status_callback,
            f"Card +10 encontrado ({cards_executados}/{max_cards}). Clicando...",
        )
        if not clicar_alvo_detectado(config, alvo, stop_event, status_callback):
            return False

        if not esperar_intervalo(config, "apos_card_detectado", stop_event, status_callback):
            return False

        if not clicar_coordenada(config, coordenadas, "voltar", stop_event, status_callback):
            return False

        if not esperar_intervalo(
            config,
            "apos_voltar_card_detectado",
            stop_event,
            status_callback,
        ):
            return False

    if cards_executados == 0:
        avisar(status_callback, "Nenhum card com +10 encontrado. Seguindo sem clicar.", "orange")
    else:
        avisar(status_callback, f"{cards_executados} card(s) +10 executado(s).", "green")

    return True


def executar_cards_por_coordenadas(config, coordenadas, stop_event=None, status_callback=None):
    avisar(status_callback, "Abrindo area dos cards...")
    if not double_click_coordenada(
        config,
        coordenadas,
        "double_click_scroll",
        stop_event,
        status_callback,
    ):
        return False
    if not esperar_intervalo(config, "apos_double_click_scroll", stop_event, status_callback):
        return False

    avisar(status_callback, "Executando card 1...")
    if not clicar_coordenada(config, coordenadas, "card_1", stop_event, status_callback):
        return False
    if not esperar_intervalo(config, "apos_card_1", stop_event, status_callback):
        return False

    if not clicar_coordenada(config, coordenadas, "voltar", stop_event, status_callback):
        return False

    avisar(status_callback, "Executando card 2...")
    if not clicar_coordenada(config, coordenadas, "card_2", stop_event, status_callback):
        return False
    if not esperar_intervalo(config, "apos_card_2", stop_event, status_callback):
        return False

    if not clicar_coordenada(config, coordenadas, "voltar", stop_event, status_callback):
        return False
    if not esperar_intervalo(config, "apos_voltar_card_2", stop_event, status_callback):
        return False

    avisar(status_callback, "Executando card 3...")
    if not clicar_coordenada(config, coordenadas, "card_3", stop_event, status_callback):
        return False
    if not esperar_intervalo(config, "apos_card_3", stop_event, status_callback):
        return False

    return clicar_coordenada(config, coordenadas, "voltar", stop_event, status_callback)


def avisar(status_callback, mensagem, cor="blue"):
    if status_callback is not None:
        status_callback(mensagem, cor)


def executar_fluxo_inicial(config, coordenadas=None, stop_event=None, status_callback=None):
    if coordenadas is None:
        coordenadas = carregar_coordenadas(config)

    avisar(status_callback, "Abrindo o Microsoft Edge...")
    if not abrir_edge(config, stop_event, status_callback):
        return False

    avisar(status_callback, "Clicando no icone da extensao...")
    if not clicar_coordenada(config, coordenadas, "icone_extensao", stop_event, status_callback):
        return False
    if not esperar_intervalo(config, "apos_icone_extensao", stop_event, status_callback):
        return False

    resultado_imagem = executar_cards_por_imagem(
        config,
        coordenadas,
        stop_event=stop_event,
        status_callback=status_callback,
    )

    if resultado_imagem is not None:
        return resultado_imagem

    if not obter_config_deteccao(config).get("usar_fallback_coordenadas", True):
        return False

    avisar(status_callback, "Usando fluxo antigo por coordenadas...", "orange")
    return executar_cards_por_coordenadas(
        config,
        coordenadas,
        stop_event=stop_event,
        status_callback=status_callback,
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
