"""Microsoft Rewards: deteccao visual local e fluxo independente do painel Edge."""
import argparse
import ctypes
import json
import os
import threading
import time
import sys
from ctypes import wintypes
from pathlib import Path

# Deve preceder Pillow/pyautogui: o processo standalone tambem usa pixels fisicos.
if sys.platform == "win32":
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))

import cv2
import numpy as np
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
ASSETS = BASE_DIR / "assets" / "rewards_app"


class RewardsAppError(RuntimeError):
    pass


class DetectorRewardsApp:
    """Templates RGB em varias escalas; os selos verdes nunca sao pendentes."""

    def __init__(self, assets=ASSETS, confidence=0.88):
        self.confidence = confidence
        self.templates = {}
        for name in ("ganhar", "continuar", "plus10", "voltar", "pesquisa"):
            files = sorted(Path(assets).glob(f"{name}_*.png"))
            if not files:
                raise RewardsAppError(f"Treino visual ausente: {name} em {assets}")
            self.templates[name] = [np.array(Image.open(p).convert("RGB")) for p in files]

    def find(self, image, name):
        rgb = np.array(image.convert("RGB"))
        h, w = rgb.shape[:2]
        # Cabecalho e toolbar sao procurados apenas no topo da janela do app.
        area = rgb[:min(h, 300 if name == "pesquisa" else 180)] if name in ("ganhar", "voltar", "pesquisa") else rgb
        matches = []
        for template in self.templates[name]:
            seen = set()
            for scale in (0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0):
                th, tw = template.shape[:2]
                size = (round(tw * scale), round(th * scale))
                if size in seen or size[0] > area.shape[1] or size[1] > area.shape[0]:
                    continue
                seen.add(size)
                scaled = cv2.resize(template, size, interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
                scores = cv2.matchTemplate(area, scaled, cv2.TM_CCOEFF_NORMED)
                for _ in range(30):
                    _, score, _, (x, y) = cv2.minMaxLoc(scores)
                    if score < self.confidence:
                        break
                    bw, bh = size
                    roi = area[y:y + bh, x:x + bw].astype(np.int16)
                    green = (roi[:, :, 1] > roi[:, :, 0] + 25) & (roi[:, :, 1] > roi[:, :, 2] + 20)
                    if name != "plus10" or (y > 85 and green.mean() < 0.04):
                        matches.append(dict(x=x + bw // 2, y=y + bh // 2, width=bw, height=bh, score=float(score)))
                    scores[max(0, y - bh // 2):y + bh // 2 + 1, max(0, x - bw // 2):x + bw // 2 + 1] = -1
        result = []
        for match in sorted(matches, key=lambda m: -m["score"]):
            if not any(abs(match["x"] - m["x"]) < max(match["width"], m["width"]) and abs(match["y"] - m["y"]) < max(match["height"], m["height"]) for m in result):
                result.append(match)
        return sorted(result, key=lambda m: (m["y"], m["x"]))


def mesma_pagina(before, after, threshold=1.2):
    """Ignora cabecalho, scrollbar e rodape flutuante na confirmacao de fim."""
    def signature(im):
        w, h = im.size
        return np.array(im.convert("L").crop((20, min(100, h // 3), w - 30, h - 70)).resize((160, 100)), dtype=np.float32)
    return before.size == after.size and float(np.abs(signature(before) - signature(after)).mean()) < threshold


class FluxoRewardsApp:
    """Driver injetavel permite testar navegacao, falhas e parada sem clicar no PC."""

    def __init__(self, driver, detector, config=None, log=None):
        self.driver = driver
        self.detector = detector
        self.config = config or {}
        self.log = log or (lambda message: None)
        self.clicks = 0

    def wait_for(self, name):
        deadline = time.monotonic() + self.config.get("timeout_segundos", 35)
        while time.monotonic() < deadline:
            image = self.driver.capture()
            matches = self.detector.find(image, name)
            if matches:
                return image, matches[0]
            self.driver.wait(0.7)
        raise RewardsAppError(f"Timeout aguardando {name}; nao vou clicar sem confirmar a tela.")

    def earning(self):
        image, target = self.wait_for("ganhar")
        self.driver.click(target)
        self.driver.wait(2)
        self.driver.home()
        self.driver.wait(1)
        for _ in range(self.config.get("max_scrolls", 60)):
            image = self.driver.capture()
            if not self.detector.find(image, "ganhar"):
                raise RewardsAppError("A aba Ganhar deixou de estar visivel.")
            section = self.detector.find(image, "continuar")
            if section:
                self.log("Secao Continuar ganhando localizada visualmente.")
                return image, section[0]["y"] + section[0]["height"] // 2
            self.driver.scroll()
            self.driver.wait(0.8)
        raise RewardsAppError("Secao Continuar ganhando nao encontrada dentro do limite de scroll.")

    def run(self):
        self.driver.open()
        # Recupera uma pesquisa deixada aberta pela execucao anterior.
        image = self.driver.capture()
        if not self.detector.find(image, "ganhar") and self.detector.find(image, "pesquisa"):
            _, back = self.wait_for("voltar")
            self.driver.click(back)
            self.driver.wait(2)
        image, section_y = self.earning()
        stable = 0
        scrolls = 0
        visits = {}
        while True:
            if not self.detector.find(image, "ganhar"):
                raise RewardsAppError("Tela de Rewards perdida durante a busca.")
            badges = [b for b in self.detector.find(image, "plus10") if b["y"] > section_y]
            if badges:
                if self.clicks >= self.config.get("max_cards", 30):
                    raise RewardsAppError("Limite de cards atingido com +10 ainda pendente.")
                badge = badges[0]
                # Identidade visual do texto acima do selo, independente da posicao na pagina.
                x, y = badge["x"], badge["y"]
                card = np.array(image.convert("L").crop((max(0, x - 12), max(85, y - 100), min(image.width, x + 220), y - 16)).resize((32, 12)))
                identity = tuple((card // 32).flatten())
                visits[identity] = visits.get(identity, 0) + 1
                if visits[identity] > self.config.get("max_tentativas_card", 2):
                    raise RewardsAppError("O mesmo card continua +10 apos as tentativas; credito nao confirmado.")
                self.log(f"Abrindo card +10 #{self.clicks + 1} (score {badge['score']:.3f}).")
                self.driver.click(badge)
                self.wait_for("pesquisa")
                self.driver.wait(self.config.get("espera_pesquisa_segundos", 5))
                _, back = self.wait_for("voltar")
                self.driver.click(back)
                self.wait_for("ganhar")
                self.driver.wait(self.config.get("espera_retorno_segundos", 2))
                self.clicks += 1
                # Reencontra a secao mesmo se o app perdeu a posicao do scroll.
                image, section_y = self.earning()
                stable = scrolls = 0
                continue
            if scrolls >= self.config.get("max_scrolls", 60):
                raise RewardsAppError("Limite de scroll atingido sem confirmar o fim da pagina.")
            self.driver.scroll()
            self.driver.wait(1)
            after = self.driver.capture()
            stable = stable + 1 if mesma_pagina(image, after) else 0
            image = after
            section_y = 85
            scrolls += 1
            if stable >= self.config.get("confirmacoes_fim", 3):
                # A ultima tela precisa ser novamente examinada, inclusive por carregamento tardio.
                if not self.detector.find(image, "ganhar"):
                    raise RewardsAppError("Fim de scroll fora do Rewards.")
                if self.detector.find(image, "plus10"):
                    continue
                self.log(f"Concluido: fim da pagina confirmado sem +10 pendente; {self.clicks} card(s) aberto(s).")
                return {"status": "ok", "cards_abertos": self.clicks, "fim_confirmado": True}


class WindowsRewardsDriver:
    def __init__(self, config, stop_event=None):
        from automacao_edge import deve_parar, dormir
        self.config = config
        self.stop = stop_event
        self.should_stop = deve_parar
        self.sleep = dormir
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        # O fluxo integrado roda em uma thread; nao dependa do contexto DPI do Tk.
        self.user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        self.user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
        self.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        for name in ("IsWindow", "IsWindowVisible", "SetForegroundWindow"):
            getattr(self.user32, name).argtypes = [wintypes.HWND]
            getattr(self.user32, name).restype = wintypes.BOOL
        self.user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        self.user32.GetWindowRect.restype = wintypes.BOOL
        self.user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self.user32.GetForegroundWindow.restype = wintypes.HWND
        self.hwnd = None
        self.bounds = None

    def wait(self, seconds):
        if not self.sleep(seconds, self.stop):
            raise RewardsAppError("Execucao interrompida.")

    def check(self):
        if self.should_stop(self.stop):
            raise RewardsAppError("Execucao interrompida.")
        if not self.hwnd or not self.user32.IsWindow(self.hwnd):
            raise RewardsAppError("Janela do Microsoft Rewards fechada.")
        if self.user32.GetForegroundWindow() != self.hwnd:
            raise RewardsAppError("Foco saiu do Microsoft Rewards; interrompendo para evitar cliques em outro app.")

    def open(self):
        from automacao_edge import obter_nome_executavel_janela
        def find():
            found = []
            callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def visit(hwnd, _):
                title = ctypes.create_unicode_buffer(512)
                self.user32.GetWindowTextW(hwnd, title, 512)
                if title.value == "Microsoft Rewards" and self.user32.IsWindowVisible(hwnd):
                    # Nao aceita uma aba do navegador com o mesmo titulo.
                    if obter_nome_executavel_janela(hwnd).lower() == "microsoft-rewards-desktop.exe":
                        found.append(hwnd)
                return True
            self.user32.EnumWindows(callback_type(visit), 0)
            if len(found) > 1:
                raise RewardsAppError("Mais de uma janela do app Microsoft Rewards encontrada.")
            return found[0] if found else None
        self.hwnd = find()
        if not self.hwnd:
            os.startfile("shell:AppsFolder\\" + self.config["app_id"])
            deadline = time.monotonic() + self.config.get("timeout_segundos", 35)
            while not self.hwnd and time.monotonic() < deadline:
                self.wait(0.5)
                self.hwnd = find()
        if not self.hwnd:
            raise RewardsAppError("O app Microsoft Rewards nao abriu.")
        self.user32.ShowWindow(self.hwnd, 9)
        self.user32.SetForegroundWindow(self.hwnd)
        self.wait(2)
        self.check()

    def capture(self):
        from deteccao_imagem import capturar_tela
        self.check()
        rect = wintypes.RECT()
        if not self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            raise RewardsAppError("Nao foi possivel ler os limites da janela.")
        self.bounds = (rect.left, rect.top, rect.right, rect.bottom)
        image, _, _ = capturar_tela(dict(x=rect.left, y=rect.top, width=rect.right - rect.left, height=rect.bottom - rect.top))
        return image

    def click(self, target):
        from deteccao_imagem import clicar_mouse
        self.check()
        rect = wintypes.RECT()
        self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        if self.bounds != (rect.left, rect.top, rect.right, rect.bottom):
            raise RewardsAppError("Janela mudou de posicao desde a deteccao.")
        clicar_mouse(rect.left + target["x"], rect.top + target["y"])

    def home(self):
        import pyautogui
        self.check()
        pyautogui.hotkey("ctrl", "home")

    def scroll(self):
        from deteccao_imagem import mover_mouse, rolar_mouse
        self.check()
        left, top, right, bottom = self.bounds
        mover_mouse(right - 60, top + (bottom - top) // 2)
        rolar_mouse(self.config.get("scroll_passos", -4))


def executar_rewards_app(config, stop_event=None, status_callback=None):
    from app_config import DEFAULT_CONFIG
    settings = dict(DEFAULT_CONFIG["rewards_app"], **config.get("rewards_app", {}))
    def log(message):
        if status_callback:
            status_callback("Microsoft Rewards: " + message, "blue")
    return FluxoRewardsApp(WindowsRewardsDriver(settings, stop_event), DetectorRewardsApp(confidence=settings["confianca"]), settings, log).run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Executa somente os cards do app Rewards, sem desligar o PC.")
    parser.add_argument("--config", type=Path, default=BASE_DIR / "config.json")
    args = parser.parse_args()
    stop = threading.Event()
    from pynput import keyboard
    listener = keyboard.Listener(on_press=lambda key: stop.set() if key == keyboard.Key.esc else None)
    listener.start()
    try:
        result = executar_rewards_app(json.loads(args.config.read_text(encoding="utf-8")), stop, lambda msg, color: print(msg, flush=True))
        print(json.dumps(result, ensure_ascii=False))
    except (RewardsAppError, KeyboardInterrupt) as exc:
        print(f"FALHA: {exc}", flush=True)
        raise SystemExit(1)
    finally:
        listener.stop()
