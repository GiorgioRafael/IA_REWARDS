import ctypes
import sys
from pathlib import Path
from ctypes import wintypes

import cv2
import numpy as np
import mss
from PIL import Image, ImageGrab


if sys.platform == "win32":
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

    USER32 = ctypes.WinDLL("user32", use_last_error=True)
    GDI32 = ctypes.WinDLL("gdi32", use_last_error=True)
else:
    USER32 = None
    GDI32 = None


SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0
BI_RGB = 0
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


TEM_GET_PHYSICAL_CURSOR_POS = False
TEM_SET_PHYSICAL_CURSOR_POS = False


if sys.platform == "win32":
    USER32.GetSystemMetrics.argtypes = [ctypes.c_int]
    USER32.GetSystemMetrics.restype = ctypes.c_int
    USER32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    USER32.GetCursorPos.restype = wintypes.BOOL
    USER32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    USER32.SetCursorPos.restype = wintypes.BOOL
    try:
        USER32.GetPhysicalCursorPos.argtypes = [ctypes.POINTER(POINT)]
        USER32.GetPhysicalCursorPos.restype = wintypes.BOOL
        TEM_GET_PHYSICAL_CURSOR_POS = True
    except AttributeError:
        pass
    try:
        USER32.SetPhysicalCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        USER32.SetPhysicalCursorPos.restype = wintypes.BOOL
        TEM_SET_PHYSICAL_CURSOR_POS = True
    except AttributeError:
        pass
    USER32.mouse_event.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_ulong,
    ]
    USER32.mouse_event.restype = None
    USER32.GetDC.argtypes = [wintypes.HWND]
    USER32.GetDC.restype = wintypes.HDC
    USER32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    USER32.ReleaseDC.restype = ctypes.c_int

    GDI32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    GDI32.CreateCompatibleDC.restype = wintypes.HDC
    GDI32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    GDI32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    GDI32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
    GDI32.SelectObject.restype = wintypes.HANDLE
    GDI32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    GDI32.BitBlt.restype = wintypes.BOOL
    GDI32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(BITMAPINFO),
        wintypes.UINT,
    ]
    GDI32.GetDIBits.restype = ctypes.c_int
    GDI32.DeleteObject.argtypes = [wintypes.HANDLE]
    GDI32.DeleteObject.restype = wintypes.BOOL
    GDI32.DeleteDC.argtypes = [wintypes.HDC]
    GDI32.DeleteDC.restype = wintypes.BOOL


def obter_bbox_virtual():
    left = USER32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    top = USER32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    width = USER32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    height = USER32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return left, top, width, height


def _get_cursor_pos_logico():
    point = POINT()
    if not USER32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())

    return point.x, point.y


def _get_cursor_pos_fisico():
    point = POINT()
    if not USER32.GetPhysicalCursorPos(ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())

    return point.x, point.y


def get_mouse_position():
    if TEM_GET_PHYSICAL_CURSOR_POS:
        return _get_cursor_pos_fisico()

    return _get_cursor_pos_logico()


def get_mouse_position_debug():
    debug = {
        "logico": None,
        "fisico": None,
        "usando": "fisico" if TEM_GET_PHYSICAL_CURSOR_POS else "logico",
    }

    try:
        debug["logico"] = _get_cursor_pos_logico()
    except Exception:
        pass

    if TEM_GET_PHYSICAL_CURSOR_POS:
        try:
            debug["fisico"] = _get_cursor_pos_fisico()
        except Exception:
            pass

    return debug


def mover_mouse(x, y):
    if TEM_SET_PHYSICAL_CURSOR_POS:
        if not USER32.SetPhysicalCursorPos(int(x), int(y)):
            raise ctypes.WinError(ctypes.get_last_error())
        return

    if not USER32.SetCursorPos(int(x), int(y)):
        raise ctypes.WinError(ctypes.get_last_error())


def clicar_mouse(x=None, y=None, button="left"):
    if x is not None and y is not None:
        mover_mouse(x, y)

    if button == "left":
        down, up = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP
    elif button == "right":
        down, up = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif button == "middle":
        down, up = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    else:
        raise ValueError(f"Botao de mouse invalido: {button}")

    USER32.mouse_event(down, 0, 0, 0, 0)
    USER32.mouse_event(up, 0, 0, 0, 0)


def rolar_mouse(passos):
    USER32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(passos) * WHEEL_DELTA, 0)


def normalizar_regiao(regiao):
    if not regiao:
        return None

    valores = (regiao.get("x"), regiao.get("y"), regiao.get("width"), regiao.get("height"))
    if any(valor is None for valor in valores):
        return None

    x, y, width, height = valores
    if width <= 0 or height <= 0:
        return None

    return int(x), int(y), int(width), int(height)


def capturar_tela_mss(regiao=None):
    regiao_normalizada = normalizar_regiao(regiao)

    with mss.mss() as sct:
        if regiao_normalizada is None:
            monitor = sct.monitors[0]
            x = int(monitor["left"])
            y = int(monitor["top"])
            width = int(monitor["width"])
            height = int(monitor["height"])
        else:
            x, y, width, height = regiao_normalizada
            monitor = {
                "left": x,
                "top": y,
                "width": width,
                "height": height,
            }

        screenshot = sct.grab(monitor)
        imagem = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        return imagem, x, y


def capturar_tela_gdi(regiao=None):
    if sys.platform != "win32":
        raise OSError("Captura GDI disponivel apenas no Windows.")

    regiao_normalizada = normalizar_regiao(regiao)
    if regiao_normalizada is None:
        x, y, width, height = obter_bbox_virtual()
    else:
        x, y, width, height = regiao_normalizada

    screen_dc = USER32.GetDC(None)
    if not screen_dc:
        raise ctypes.WinError(ctypes.get_last_error())

    mem_dc = GDI32.CreateCompatibleDC(screen_dc)
    if not mem_dc:
        USER32.ReleaseDC(None, screen_dc)
        raise ctypes.WinError(ctypes.get_last_error())

    bitmap = GDI32.CreateCompatibleBitmap(screen_dc, width, height)
    if not bitmap:
        GDI32.DeleteDC(mem_dc)
        USER32.ReleaseDC(None, screen_dc)
        raise ctypes.WinError(ctypes.get_last_error())

    old_bitmap = GDI32.SelectObject(mem_dc, bitmap)

    try:
        if not GDI32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, x, y, SRCCOPY):
            raise ctypes.WinError(ctypes.get_last_error())

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = -height
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        buffer = ctypes.create_string_buffer(width * height * 4)
        linhas = GDI32.GetDIBits(
            mem_dc,
            bitmap,
            0,
            height,
            buffer,
            ctypes.byref(bmi),
            DIB_RGB_COLORS,
        )
        if linhas != height:
            raise ctypes.WinError(ctypes.get_last_error())

        imagem = Image.frombuffer(
            "RGB",
            (width, height),
            buffer,
            "raw",
            "BGRX",
            0,
            1,
        ).copy()
    finally:
        GDI32.SelectObject(mem_dc, old_bitmap)
        GDI32.DeleteObject(bitmap)
        GDI32.DeleteDC(mem_dc)
        USER32.ReleaseDC(None, screen_dc)

    return imagem, x, y


def capturar_tela_imagegrab(regiao=None):
    virtual_left, virtual_top, _, _ = obter_bbox_virtual()
    imagem = ImageGrab.grab(all_screens=True)

    regiao_normalizada = normalizar_regiao(regiao)
    if regiao_normalizada is None:
        return imagem, virtual_left, virtual_top

    x, y, width, height = regiao_normalizada
    crop_left = x - virtual_left
    crop_top = y - virtual_top
    crop_right = crop_left + width
    crop_bottom = crop_top + height
    return imagem.crop((crop_left, crop_top, crop_right, crop_bottom)), x, y


def capturar_tela(regiao=None):
    try:
        return capturar_tela_mss(regiao)
    except Exception:
        pass

    try:
        return capturar_tela_gdi(regiao)
    except Exception:
        return capturar_tela_imagegrab(regiao)


def normalizar_escalas_template(escalas):
    if not escalas:
        return [1.0]

    resultado = []
    for escala in escalas:
        try:
            valor = round(float(escala), 4)
        except (TypeError, ValueError):
            continue

        if valor <= 0:
            continue

        if valor not in resultado:
            resultado.append(valor)

    return resultado or [1.0]


def cancelamento_solicitado(stop_event):
    return stop_event is not None and stop_event.is_set()


def _localizar_template_em_imagem(
    template_path,
    tela,
    offset_x,
    offset_y,
    confianca=0.85,
    max_resultados=10,
    escalas=None,
    tons_cinza=False,
    stop_event=None,
):
    if cancelamento_solicitado(stop_event):
        return []

    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"Template nao encontrado: {template_path}")

    template = Image.open(template_path).convert("RGB")
    if cancelamento_solicitado(stop_event):
        return []

    if tons_cinza:
        tela_cv = cv2.cvtColor(np.array(tela.convert("RGB")), cv2.COLOR_RGB2GRAY)
        template_original_cv = cv2.cvtColor(np.array(template), cv2.COLOR_RGB2GRAY)
    else:
        tela_cv = cv2.cvtColor(np.array(tela.convert("RGB")), cv2.COLOR_RGB2BGR)
        template_original_cv = cv2.cvtColor(np.array(template), cv2.COLOR_RGB2BGR)
    template_original_height, template_original_width = template_original_cv.shape[:2]
    tela_height, tela_width = tela_cv.shape[:2]

    if template_original_width > tela_width or template_original_height > tela_height:
        return []

    candidatos = []
    dimensoes_usadas = set()
    for escala in normalizar_escalas_template(escalas):
        if cancelamento_solicitado(stop_event):
            return []

        template_width = max(1, int(round(template_original_width * escala)))
        template_height = max(1, int(round(template_original_height * escala)))
        dimensao = (template_width, template_height)
        if dimensao in dimensoes_usadas:
            continue
        dimensoes_usadas.add(dimensao)

        if template_width > tela_width or template_height > tela_height:
            continue

        if dimensao == (template_original_width, template_original_height):
            template_cv = template_original_cv
        else:
            interpolacao = cv2.INTER_AREA if escala < 1 else cv2.INTER_CUBIC
            template_cv = cv2.resize(
                template_original_cv,
                dimensao,
                interpolation=interpolacao,
            )

        resultado = cv2.matchTemplate(tela_cv, template_cv, cv2.TM_CCOEFF_NORMED)
        if cancelamento_solicitado(stop_event):
            return []

        pontos_y, pontos_x = np.where(resultado >= confianca)

        for x, y in zip(pontos_x, pontos_y):
            if cancelamento_solicitado(stop_event):
                return []

            score = float(resultado[y, x])
            centro_x = offset_x + int(x + template_width / 2)
            centro_y = offset_y + int(y + template_height / 2)
            candidatos.append(
                {
                    "x": centro_x,
                    "y": centro_y,
                    "score": score,
                    "width": template_width,
                    "height": template_height,
                    "scale": escala,
                }
            )

    candidatos.sort(key=lambda item: item["score"], reverse=True)

    filtrados = []

    for candidato in candidatos:
        duplicado = any(
            abs(candidato["x"] - item["x"])
            <= max(10, max(candidato["width"], item["width"]) // 2)
            and abs(candidato["y"] - item["y"])
            <= max(10, max(candidato["height"], item["height"]) // 2)
            for item in filtrados
        )

        if duplicado:
            continue

        filtrados.append(candidato)
        if len(filtrados) >= max_resultados:
            break

    filtrados.sort(key=lambda item: (item["y"], item["x"]))
    return filtrados


def localizar_template(
    template_path,
    confianca=0.85,
    regiao=None,
    max_resultados=10,
    escalas=None,
    tons_cinza=False,
    stop_event=None,
):
    if cancelamento_solicitado(stop_event):
        return []

    tela, offset_x, offset_y = capturar_tela(regiao)
    if cancelamento_solicitado(stop_event):
        return []

    return _localizar_template_em_imagem(
        template_path,
        tela,
        offset_x,
        offset_y,
        confianca=confianca,
        max_resultados=max_resultados,
        escalas=escalas,
        tons_cinza=tons_cinza,
        stop_event=stop_event,
    )


def localizar_templates(
    template_paths,
    confianca=0.85,
    regiao=None,
    max_resultados=10,
    parar_score=None,
    escalas=None,
    tons_cinza=False,
    stop_event=None,
):
    if cancelamento_solicitado(stop_event):
        return []

    resultados = []
    tela, offset_x, offset_y = capturar_tela(regiao)
    if cancelamento_solicitado(stop_event):
        return []

    for template_path in template_paths:
        if cancelamento_solicitado(stop_event):
            return []

        resultados_template = _localizar_template_em_imagem(
            template_path,
            tela,
            offset_x,
            offset_y,
            confianca=confianca,
            max_resultados=max_resultados,
            escalas=escalas,
            tons_cinza=tons_cinza,
            stop_event=stop_event,
        )

        for resultado in resultados_template:
            resultado["template"] = str(template_path)
            resultados.append(resultado)

        if parar_score is not None and resultados_template:
            melhor_score = max(resultado["score"] for resultado in resultados_template)
            if melhor_score >= float(parar_score):
                break

    resultados.sort(key=lambda item: item["score"], reverse=True)

    filtrados = []
    for resultado in resultados:
        duplicado = any(
            abs(resultado["x"] - item["x"]) <= max(10, resultado["width"] // 2)
            and abs(resultado["y"] - item["y"]) <= max(10, resultado["height"] // 2)
            for item in filtrados
        )

        if duplicado:
            continue

        filtrados.append(resultado)
        if len(filtrados) >= max_resultados:
            break

    filtrados.sort(key=lambda item: (item["y"], item["x"]))
    return filtrados


def _contar_pixels_cor(regiao, condicao):
    if regiao.size == 0:
        return 0

    mascara = condicao(regiao)
    return int(mascara.sum())


def _pontuar_logo_microsoft(arr, x, y, width, height):
    top = arr[
        y : min(arr.shape[0], y + min(110, height)),
        x : min(arr.shape[1], x + min(240, width)),
    ]
    if top.size == 0:
        return 0

    vermelho = _contar_pixels_cor(
        top,
        lambda item: (
            (item[:, :, 0] > 190)
            & (item[:, :, 1] < 130)
            & (item[:, :, 2] < 130)
        ),
    )
    verde = _contar_pixels_cor(
        top,
        lambda item: (
            (item[:, :, 1] > 130)
            & (item[:, :, 0] < 170)
            & (item[:, :, 2] < 170)
        ),
    )
    azul = _contar_pixels_cor(
        top,
        lambda item: (
            (item[:, :, 2] > 130)
            & (item[:, :, 0] < 150)
            & (item[:, :, 1] < 180)
        ),
    )
    amarelo = _contar_pixels_cor(
        top,
        lambda item: (
            (item[:, :, 0] > 190)
            & (item[:, :, 1] > 130)
            & (item[:, :, 2] < 140)
        ),
    )

    cores_presentes = sum(valor >= 8 for valor in (vermelho, verde, azul, amarelo))
    if cores_presentes == 4:
        return 1.0
    if cores_presentes == 3:
        return 0.55
    return 0.0


def _segmentos_true(valores):
    segmentos = []
    inicio = None
    for indice, ativo in enumerate(valores):
        if ativo and inicio is None:
            inicio = indice
        elif not ativo and inicio is not None:
            segmentos.append((inicio, indice))
            inicio = None

    if inicio is not None:
        segmentos.append((inicio, len(valores)))

    return segmentos


def _fechar_lacunas_1d(valores, kernel_tamanho):
    kernel = np.ones((1, int(kernel_tamanho)), dtype=np.uint8)
    mask = valores.astype(np.uint8).reshape(1, -1) * 255
    fechado = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    return fechado.reshape(-1) > 0


def _escolher_segmento_contendo(segmentos, ponto):
    contendo = [segmento for segmento in segmentos if segmento[0] <= ponto < segmento[1]]
    if contendo:
        return max(contendo, key=lambda item: item[1] - item[0])

    if not segmentos:
        return None

    return min(segmentos, key=lambda item: min(abs(item[0] - ponto), abs(item[1] - ponto)))


def _pontuar_fechamento_painel(arr, x, y, width, height):
    tela_altura, tela_largura = arr.shape[:2]
    if width <= 0 or height <= 0:
        return 0.0

    topo = arr[y : min(tela_altura, y + min(120, height)), x : min(tela_largura, x + width)]
    if topo.size == 0:
        return 0.0

    direita = topo[:, max(0, topo.shape[1] - 90) : topo.shape[1]]
    escuro = (
        (direita[:, :, 0] < 90)
        & (direita[:, :, 1] < 90)
        & (direita[:, :, 2] < 90)
    )
    linhas = escuro.sum(axis=1)
    colunas = escuro.sum(axis=0)
    tem_traco_horizontal = linhas.max(initial=0) >= 6
    tem_traco_vertical = colunas.max(initial=0) >= 6
    return 1.0 if tem_traco_horizontal and tem_traco_vertical else 0.0


def _adicionar_candidato_painel(candidatos, arr, light_mask, x, y, width, height, origem):
    tela_altura, tela_largura = arr.shape[:2]
    if width < 280 or width > min(900, tela_largura):
        return
    if height < 300 or height > tela_altura:
        return

    area = width * height
    if area < tela_altura * tela_largura * 0.015:
        return

    recorte_light = light_mask[y : y + height, x : x + width]
    light_ratio = float(recorte_light.mean() / 255.0) if recorte_light.size else 0.0
    if light_ratio < 0.18:
        return

    logo_score = _pontuar_logo_microsoft(arr, x, y, width, height)
    close_score = _pontuar_fechamento_painel(arr, x, y, width, height)
    altura_score = min(1.0, height / max(1, tela_altura * 0.55))
    largura_preferida = 1.0 - min(1.0, abs(width - 470) / 470)
    topo_score = 1.0 - min(1.0, y / max(1, tela_altura * 0.45))
    lado_score = x / max(1, tela_largura)
    vertical_score = min(1.0, height / max(1, width * 1.6))

    score = (
        logo_score * 4.0
        + close_score * 1.6
        + altura_score * 2.2
        + largura_preferida * 1.3
        + topo_score * 1.1
        + lado_score * 0.6
        + vertical_score * 0.8
        + min(1.0, light_ratio * 1.8)
    )

    candidatos.append(
        {
            "x": int(x),
            "y": int(y),
            "width": int(width),
            "height": int(height),
            "score": float(score),
            "logo_score": float(logo_score),
            "close_score": float(close_score),
            "light_ratio": float(light_ratio),
            "origem": origem,
        }
    )


def _candidatos_painel_por_projecao(arr, light_mask):
    candidatos = []
    altura, largura = light_mask.shape
    col_ratio = light_mask.mean(axis=0) / 255.0
    colunas = col_ratio >= 0.36

    inicio = None
    segmentos = []
    for indice, ativo in enumerate(colunas):
        if ativo and inicio is None:
            inicio = indice
        elif not ativo and inicio is not None:
            segmentos.append((inicio, indice))
            inicio = None
    if inicio is not None:
        segmentos.append((inicio, largura))

    for x0, x1 in segmentos:
        width = x1 - x0
        if width < 260 or width > min(950, largura):
            continue

        row_ratio = light_mask[:, x0:x1].mean(axis=1) / 255.0
        linhas = row_ratio >= 0.22
        y_inicio = None
        for indice, ativo in enumerate(linhas):
            if ativo and y_inicio is None:
                y_inicio = indice
            elif not ativo and y_inicio is not None:
                height = indice - y_inicio
                _adicionar_candidato_painel(
                    candidatos,
                    arr,
                    light_mask,
                    x0,
                    y_inicio,
                    width,
                    height,
                    "projecao",
                )
                y_inicio = None
        if y_inicio is not None:
            _adicionar_candidato_painel(
                candidatos,
                arr,
                light_mask,
                x0,
                y_inicio,
                width,
                altura - y_inicio,
                "projecao",
            )

    return candidatos


def _candidatos_painel_por_logo(arr, light_mask):
    candidatos = []
    altura, largura = arr.shape[:2]
    vermelho = (
        (arr[:, :, 0] > 190)
        & (arr[:, :, 1] < 130)
        & (arr[:, :, 2] < 130)
    ).astype(np.uint8) * 255

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(vermelho, 8)
    larguras_provaveis = (360, 420, 480, 540, 620)

    for label in range(1, num_labels):
        x, y, width, height, area = stats[label]
        if area < 8 or area > 600:
            continue
        if width < 4 or width > 45 or height < 4 or height > 45:
            continue

        janela_x0 = max(0, x - 12)
        janela_y0 = max(0, y - 12)
        janela_x1 = min(largura, x + 58)
        janela_y1 = min(altura, y + 58)
        janela = arr[janela_y0:janela_y1, janela_x0:janela_x1]
        if janela.size == 0:
            continue

        logo_score = _pontuar_logo_microsoft(
            arr,
            janela_x0,
            janela_y0,
            janela_x1 - janela_x0,
            janela_y1 - janela_y0,
        )
        if logo_score < 1.0:
            continue

        logo_centro_x = int((janela_x0 + janela_x1) / 2)
        logo_centro_y = int((janela_y0 + janela_y1) / 2)
        header_y0 = max(0, janela_y0 - 28)
        header_y1 = min(altura, janela_y0 + 170)
        faixa_header = light_mask[header_y0:header_y1, :]
        if faixa_header.size:
            colunas = (faixa_header.mean(axis=0) / 255.0) >= 0.34
            colunas = _fechar_lacunas_1d(colunas, 41)
            segmento_x = _escolher_segmento_contendo(
                _segmentos_true(colunas),
                logo_centro_x,
            )
        else:
            segmento_x = None

        if segmento_x is not None:
            panel_x0, panel_x1 = segmento_x
            panel_width = panel_x1 - panel_x0
            if 280 <= panel_width <= min(900, largura):
                linhas = (light_mask[:, panel_x0:panel_x1].mean(axis=1) / 255.0) >= 0.16
                linhas = _fechar_lacunas_1d(linhas, 71)
                segmento_y = _escolher_segmento_contendo(
                    _segmentos_true(linhas),
                    logo_centro_y,
                )
                if segmento_y is not None:
                    panel_y0, panel_y1 = segmento_y
                    panel_y0 = max(0, min(panel_y0, janela_y0 - 18))
                    panel_height = panel_y1 - panel_y0
                    _adicionar_candidato_painel(
                        candidatos,
                        arr,
                        light_mask,
                        panel_x0,
                        panel_y0,
                        panel_width,
                        panel_height,
                        "logo_expandido",
                    )

        panel_x = max(0, janela_x0 - 14)
        panel_y = max(0, janela_y0 - 12)
        panel_height = min(altura - panel_y, max(360, int(altura * 0.82)))

        for panel_width in larguras_provaveis:
            width_final = min(panel_width, largura - panel_x)
            _adicionar_candidato_painel(
                candidatos,
                arr,
                light_mask,
                panel_x,
                panel_y,
                width_final,
                panel_height,
                "logo",
            )

    return candidatos


def detectar_painel_rewards():
    imagem, offset_x, offset_y = capturar_tela()
    arr = np.array(imagem.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)

    light = (
        ((gray >= 222) & (hsv[:, :, 1] <= 85))
        | ((gray >= 238) & (hsv[:, :, 1] <= 125))
    ).astype(np.uint8) * 255

    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (31, 31))
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    mask = cv2.morphologyEx(light, cv2.MORPH_CLOSE, kernel_close, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open, iterations=1)

    candidatos = []
    contornos, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contorno in contornos:
        x, y, width, height = cv2.boundingRect(contorno)
        _adicionar_candidato_painel(
            candidatos,
            arr,
            light,
            x,
            y,
            width,
            height,
            "contorno",
        )

    candidatos.extend(_candidatos_painel_por_projecao(arr, light))
    candidatos.extend(_candidatos_painel_por_logo(arr, light))
    if not candidatos:
        return None

    candidatos_com_logo = [item for item in candidatos if item.get("logo_score", 0) >= 1.0]
    if candidatos_com_logo:
        candidatos = candidatos_com_logo

    candidatos.sort(key=lambda item: item["score"], reverse=True)
    melhor = candidatos[0]
    return {
        "x": offset_x + melhor["x"],
        "y": offset_y + melhor["y"],
        "width": melhor["width"],
        "height": melhor["height"],
        "score": melhor["score"],
        "logo_score": melhor["logo_score"],
        "close_score": melhor.get("close_score", 0.0),
        "light_ratio": melhor["light_ratio"],
        "origem": melhor["origem"],
    }


def detectar_scrollbar_thumb_em_imagem(
    imagem,
    offset_x,
    offset_y,
    cor=(118, 118, 118),
    tolerancia=28,
    altura_min=35,
    faixa_direita=32,
):
    arr = np.array(imagem.convert("RGB"))
    altura, largura = arr.shape[:2]
    if altura <= 0 or largura <= 0:
        return None

    faixa_busca = min(
        largura,
        max(int(faixa_direita), min(160, max(48, largura // 3))),
    )
    x0 = max(0, largura - faixa_busca)
    roi = arr[:, x0:largura]
    alvo = np.array(cor, dtype=np.int16)
    diff = np.abs(roi.astype(np.int16) - alvo).max(axis=2)
    canais_max = roi.max(axis=2)
    canais_min = roi.min(axis=2)
    cinza_neutro = (
        (canais_max >= max(0, cor[0] - tolerancia - 10))
        & (canais_max <= min(255, cor[0] + tolerancia + 20))
        & ((canais_max - canais_min) <= 22)
    )
    mask = ((diff <= int(tolerancia)) | cinza_neutro).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    candidatos = []
    for label in range(1, num_labels):
        x, y, width, height, area = stats[label]
        if height < int(altura_min):
            continue
        if width < 2 or width > faixa_direita:
            continue
        if area < height * 1.6:
            continue

        candidatos.append(
            {
                "x": int(offset_x + x0 + x),
                "y": int(offset_y + y),
                "width": int(width),
                "height": int(height),
                "area": int(area),
                "center_y": int(offset_y + y + height / 2),
                "bottom": int(offset_y + y + height),
            }
        )

    if not candidatos:
        return None

    candidatos.sort(key=lambda item: (item["height"], item["area"]), reverse=True)
    return candidatos[0]


def maior_sequencia_true(valores):
    maior = 0
    atual = 0
    for valor in valores:
        if valor:
            atual += 1
            maior = max(maior, atual)
        else:
            atual = 0

    return maior


def validar_sinal_mais_no_alvo(alvo, margem=6):
    largura = int(alvo["width"])
    altura = int(alvo["height"])
    regiao = {
        "x": int(alvo["x"] - largura / 2 - margem),
        "y": int(alvo["y"] - altura / 2 - margem),
        "width": int(largura + margem * 2),
        "height": int(altura + margem * 2),
    }

    imagem, _, _ = capturar_tela(regiao)
    arr = np.array(imagem.convert("RGB"))

    teal = (
        (arr[:, :, 0] < 90)
        & (arr[:, :, 1] > 60)
        & (arr[:, :, 2] > 70)
    )
    ys, xs = np.where(teal)
    if len(xs) == 0 or len(ys) == 0:
        return False, {"motivo": "sem selo azul", "teal_pixels": 0}

    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    badge = arr[y0:y1, x0:x1]
    if badge.size == 0:
        return False, {"motivo": "recorte vazio"}

    branco = (
        (badge[:, :, 0] > 180)
        & (badge[:, :, 1] > 180)
        & (badge[:, :, 2] > 180)
    )

    badge_altura, badge_largura = branco.shape
    sx0 = max(0, int(badge_largura * 0.10))
    sx1 = min(badge_largura, int(badge_largura * 0.44))
    sy0 = max(0, int(badge_altura * 0.15))
    sy1 = min(badge_altura, int(badge_altura * 0.85))
    simbolo = branco[sy0:sy1, sx0:sx1]

    if simbolo.size == 0:
        return False, {"motivo": "regiao do simbolo vazia"}

    altura_simbolo, largura_simbolo = simbolo.shape
    linhas = simbolo.sum(axis=1)
    colunas = simbolo.sum(axis=0)

    linha_max = int(linhas.max()) if linhas.size else 0
    coluna_max = int(colunas.max()) if colunas.size else 0
    linha_idx = int(linhas.argmax()) if linhas.size else 0
    coluna_idx = int(colunas.argmax()) if colunas.size else 0

    limite_horizontal = max(6, int(largura_simbolo * 0.45))
    limite_vertical = max(6, int(altura_simbolo * 0.35))
    tem_horizontal = linha_max >= limite_horizontal
    tem_vertical = coluna_max >= limite_vertical

    janela = simbolo[
        max(0, linha_idx - 2) : min(altura_simbolo, linha_idx + 3),
        max(0, coluna_idx - 2) : min(largura_simbolo, coluna_idx + 3),
    ]
    cruzamento = int(janela.sum()) >= 4

    linha_longa = maior_sequencia_true(linhas >= max(3, limite_horizontal // 2))
    coluna_longa = maior_sequencia_true(colunas >= max(3, limite_vertical // 2))
    valido = tem_horizontal and tem_vertical and cruzamento

    detalhes = {
        "motivo": "ok" if valido else "sem geometria de +",
        "linha_max": linha_max,
        "coluna_max": coluna_max,
        "limite_horizontal": limite_horizontal,
        "limite_vertical": limite_vertical,
        "cruzamento": cruzamento,
        "linha_longa": linha_longa,
        "coluna_longa": coluna_longa,
        "badge": (x0, y0, x1 - x0, y1 - y0),
    }
    return valido, detalhes


def capturar_template_em_coordenada(destino, x, y, largura=70, altura=36):
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    regiao = {
        "x": int(x - largura / 2),
        "y": int(y - altura / 2),
        "width": int(largura),
        "height": int(altura),
    }
    imagem, _, _ = capturar_tela(regiao)
    imagem.save(destino)
    return destino


def capturar_template_em_volta_do_mouse(destino, largura=70, altura=36):
    x, y = get_mouse_position()
    return capturar_template_em_coordenada(destino, x, y, largura, altura)
