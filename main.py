"""Inicializador do TST-GESTÃO: servidor local, janela do aplicativo e ícone de bandeja."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
HOST, PORT = "127.0.0.1", 8765
URL = f"http://{HOST}:{PORT}/"
LOGO = BASE / "tst_gestao" / "static" / "logo.png"


def porta_em_uso() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((HOST, PORT)) == 0


def abrir_janela() -> None:
    candidatos = [
        Path(os.environ.get(v, "")) / rel
        for v in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")
        for rel in ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")
    ]
    for exe in candidatos:
        if exe.is_file():
            subprocess.Popen([str(exe), f"--app={URL}", "--window-size=1366,820"])
            return
    webbrowser.open(URL)


def registrar_erro() -> None:
    from tst_gestao.db import DATA_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "erro.log", "a", encoding="utf-8") as f:
        f.write(traceback.format_exc() + "\n")


def main() -> None:
    if porta_em_uso():
        abrir_janela()
        return

    from werkzeug.serving import make_server

    from tst_gestao.app import create_app

    servidor = make_server(HOST, PORT, create_app(), threaded=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()

    import pystray
    from PIL import Image

    def sair(icone, _item=None) -> None:
        servidor.shutdown()
        icone.stop()

    icone = pystray.Icon(
        "TST-GESTAO",
        Image.open(LOGO),
        "TST-GESTÃO",
        menu=pystray.Menu(
            pystray.MenuItem("Abrir TST-GESTÃO", lambda *_: abrir_janela(), default=True),
            pystray.MenuItem("Sair", sair),
        ),
    )
    threading.Timer(0.8, abrir_janela).start()
    icone.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        registrar_erro()
        raise
