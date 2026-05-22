import argparse
import time

try:
    import pyautogui
except ModuleNotFoundError as exc:
    raise SystemExit(
        "pyautogui nao esta instalado. Instale com: pip install pyautogui"
    ) from exc


def main():
    parser = argparse.ArgumentParser(
        description="Move o mouse, faz clique press/release, espera e move novamente."
    )
    parser.add_argument("--x", type=int, required=True, help="Coordenada X inicial")
    parser.add_argument("--y", type=int, required=True, help="Coordenada Y inicial")
    parser.add_argument("--next-x", type=int, required=True, help="Proxima coordenada X")
    parser.add_argument("--next-y", type=int, required=True, help="Proxima coordenada Y")
    parser.add_argument("--sleep", type=float, default=1.0, help="Pausa em segundos")
    parser.add_argument("--duration", type=float, default=0.2, help="Duracao do movimento")
    parser.add_argument(
        "--button",
        default="left",
        choices=["left", "right", "middle"],
        help="Botao do mouse",
    )
    args = parser.parse_args()

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05

    pyautogui.moveTo(args.x, args.y, duration=args.duration)
    pyautogui.mouseDown(button=args.button)
    pyautogui.mouseUp(button=args.button)

    time.sleep(args.sleep)

    pyautogui.moveTo(args.next_x, args.next_y, duration=args.duration)


if __name__ == "__main__":
    main()
