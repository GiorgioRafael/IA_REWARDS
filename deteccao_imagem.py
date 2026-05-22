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


def localizar_template(template_path, confianca=0.85, regiao=None, max_resultados=10):
    template_path = Path(template_path)
    if not template_path.exists():
        raise FileNotFoundError(f"Template nao encontrado: {template_path}")

    tela, offset_x, offset_y = capturar_tela(regiao)
    template = Image.open(template_path).convert("RGB")

    tela_cv = cv2.cvtColor(np.array(tela.convert("RGB")), cv2.COLOR_RGB2BGR)
    template_cv = cv2.cvtColor(np.array(template), cv2.COLOR_RGB2BGR)
    template_height, template_width = template_cv.shape[:2]
    tela_height, tela_width = tela_cv.shape[:2]

    if template_width > tela_width or template_height > tela_height:
        return []

    resultado = cv2.matchTemplate(tela_cv, template_cv, cv2.TM_CCOEFF_NORMED)
    pontos_y, pontos_x = np.where(resultado >= confianca)

    candidatos = []
    for x, y in zip(pontos_x, pontos_y):
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
            }
        )

    candidatos.sort(key=lambda item: item["score"], reverse=True)

    filtrados = []
    distancia_x = max(10, template_width // 2)
    distancia_y = max(10, template_height // 2)

    for candidato in candidatos:
        duplicado = any(
            abs(candidato["x"] - item["x"]) <= distancia_x
            and abs(candidato["y"] - item["y"]) <= distancia_y
            for item in filtrados
        )

        if duplicado:
            continue

        filtrados.append(candidato)
        if len(filtrados) >= max_resultados:
            break

    filtrados.sort(key=lambda item: (item["y"], item["x"]))
    return filtrados


def localizar_templates(template_paths, confianca=0.85, regiao=None, max_resultados=10):
    resultados = []

    for template_path in template_paths:
        for resultado in localizar_template(
            template_path,
            confianca=confianca,
            regiao=regiao,
            max_resultados=max_resultados,
        ):
            resultado["template"] = str(template_path)
            resultados.append(resultado)

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
