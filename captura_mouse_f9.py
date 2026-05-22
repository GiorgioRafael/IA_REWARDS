import ctypes
import sys
import time
from ctypes import wintypes


if sys.platform != "win32":
    raise SystemExit("Este script funciona apenas no Windows.")


user32 = ctypes.WinDLL("user32", use_last_error=True)

HOTKEY_ID = 1
MOD_NOREPEAT = 0x4000
PM_REMOVE = 0x0001
VK_F9 = 0x78
WM_HOTKEY = 0x0312


class POINT(ctypes.Structure):
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


user32.RegisterHotKey.argtypes = (
    wintypes.HWND,
    wintypes.INT,
    wintypes.UINT,
    wintypes.UINT,
)
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = (wintypes.HWND, wintypes.INT)
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = (ctypes.POINTER(POINT),)
user32.GetCursorPos.restype = wintypes.BOOL
user32.PeekMessageW.argtypes = (
    ctypes.POINTER(wintypes.MSG),
    wintypes.HWND,
    wintypes.UINT,
    wintypes.UINT,
    wintypes.UINT,
)
user32.PeekMessageW.restype = wintypes.BOOL
user32.TranslateMessage.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.TranslateMessage.restype = wintypes.BOOL
user32.DispatchMessageW.argtypes = (ctypes.POINTER(wintypes.MSG),)
user32.DispatchMessageW.restype = wintypes.LPARAM


def get_mouse_position():
    point = POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())
    return point.x, point.y


def main():
    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, VK_F9):
        error_code = ctypes.get_last_error()
        raise SystemExit(
            "Nao foi possivel registrar a tecla F9. "
            f"Codigo do erro: {error_code}"
        )

    print("Pressione F9 para capturar a posicao atual do mouse.")
    print("Pressione Ctrl+C para sair.")

    msg = wintypes.MSG()

    try:
        while True:
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    x, y = get_mouse_position()
                    print(f"x={x}, y={y}", flush=True)

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

            time.sleep(0.03)
    except KeyboardInterrupt:
        print("\nEncerrando.")
    finally:
        user32.UnregisterHotKey(None, HOTKEY_ID)


if __name__ == "__main__":
    main()
