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
            "click_offset_x": 0,
            "click_offset_y": 0,
            "regiao": {"x": None, "y": None, "width": None, "height": None},
        },
        "voltar": {
            "template": "assets/alvos/voltar.png",
            "treino_dir": "assets/treino_voltar",
            "confianca": 0.82,
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


def localizar_alvo_visual(config, nome, status_callback=None, regiao=None):
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
    confianca = float(alvo_config.get("confianca", 0.82))
    avisar(
        status_callback,
        f"Rodando deteccao do alvo '{nome}' com {len(templates)} template(s), confianca {confianca:.2f}.",
    )
    resultados = localizar_templates(
        templates,
        confianca=confianca,
        regiao=regiao_config,
        max_resultados=10,
    )
    avisar(status_callback, f"Alvo '{nome}' retornou {len(resultados)} resultado(s).")
    if not resultados:
        return None

    melhor = resultados[0]
    avisar(
        status_callback,
        f"Melhor alvo '{nome}': x={melhor['x']}, y={melhor['y']}, score={melhor['score']:.2f}.",
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

    alvo = localizar_alvo_visual(config, nome, status_callback, regiao=regiao)
    if alvo is None:
        return False

    alvo_config = obter_config_alvo_visual(config, nome)
    x = int(alvo["x"]) + int(alvo_config.get("click_offset_x", 0))
    y = int(alvo["y"]) + int(alvo_config.get("click_offset_y", 0))

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


def alvo_ja_clicado(alvo, alvos_clicados, margem=45):
    return any(
        abs(alvo["x"] - clicado["x"]) <= margem
        and abs(alvo["y"] - clicado["y"]) <= margem
        for clicado in alvos_clicados
    )


def localizar_alvo_bonus(config, alvos_clicados, status_callback=None):
    deteccao = obter_config_deteccao(config)
    templates = listar_templates_bonus(config)

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

    resultados = localizar_templates(
        templates,
        confianca=float(deteccao["confianca"]),
        regiao=regiao_deteccao,
        max_resultados=20,
    )
    avisar(status_callback, f"Deteccao retornou {len(resultados)} resultado(s).")

    for alvo in resultados:
        if not alvo_ja_clicado(alvo, alvos_clicados):
            if deteccao.get("validar_sinal_mais", True):
                valido, detalhes = validar_sinal_mais_no_alvo(alvo)
                if not valido:
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
            return alvo

    avisar(status_callback, "Todos os alvos encontrados ja foram clicados nessa execucao.")
    return None


def localizar_alvo_plus_10(config, alvos_clicados, status_callback=None):
    return localizar_alvo_bonus(config, alvos_clicados, status_callback)


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

    x, y, painel = obter_alvo_area_scroll(
        config,
        coordenadas,
        status_callback=status_callback,
        para_clique=True,
    )
    if x is None or y is None:
        return False

    if painel is None:
        avisar(status_callback, f"Clicando uma vez para focar a area de scroll: x={x}, y={y}.")
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
    )
    if x is None or y is None:
        return False

    if painel is None:
        avisar(status_callback, f"Movendo mouse para a area de scroll sem clicar: x={x}, y={y}.")
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
            "light_ratio": painel.get("light_ratio"),
            "origem": painel.get("origem"),
        }
    )
    avisar(
        status_callback,
        "Painel Rewards detectado automaticamente: "
        f"x={regiao['x']}, y={regiao['y']}, "
        f"w={regiao['width']}, h={regiao['height']}, "
        f"score={float(regiao.get('score') or 0):.2f}.",
    )
    return regiao


def obter_regiao_painel_rewards(config, status_callback=None):
    painel = detectar_painel_atual(config, status_callback)
    if painel is not None:
        return painel

    return None


def obter_alvo_area_scroll(config, coordenadas, status_callback=None, para_clique=False):
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

    max_cards = int(deteccao["max_cards"])
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

        avisar(status_callback, "Procurando +10/+5 na area visivel...")
        alvo = localizar_alvo_bonus(config, alvos_clicados, status_callback)
        if alvo is None:
            if resultado_scroll.get("fim_scroll"):
                avisar(status_callback, "Fim do scroll detectado e nenhum +10/+5 novo encontrado.", "orange")
                break

            avisar(status_callback, "Nenhum +10/+5 encontrado depois desse scroll.", "orange")
            continue

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
):
    if coordenadas is None:
        coordenadas = carregar_coordenadas(config)

    avisar(status_callback, "Abrindo o Microsoft Edge...")
    if not abrir_edge(config, stop_event, status_callback):
        return False

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
