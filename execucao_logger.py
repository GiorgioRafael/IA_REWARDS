import subprocess
import threading
from datetime import datetime
from pathlib import Path

from app_config import LOGS_DIR


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
