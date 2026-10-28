"""Inicializador do TST-GESTÃO: servidor local, janela do aplicativo e ícone de bandeja."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import traceback
import webbrowser
import logging
from pathlib import Path

BASE = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", BASE))
BIND_HOST, PORT = "0.0.0.0", 8765
LOCAL_HOST = "127.0.0.1"
URL = f"http://{LOCAL_HOST}:{PORT}/"
LOGO = RESOURCE_DIR / "tst_gestao" / "static" / "logo.png"


def porta_em_uso() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((LOCAL_HOST, PORT)) == 0


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


def configurar_log_servidor(app) -> None:
    from tst_gestao.db import DATA_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    arquivo = DATA_DIR / "erro.log"
    handler = logging.FileHandler(arquivo, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.ERROR)
    logging.getLogger("werkzeug").addHandler(handler)


def main() -> None:
    if porta_em_uso():
        abrir_janela()
        return

    from werkzeug.serving import make_server

    from tst_gestao.app import create_app

    app = create_app()
    configurar_log_servidor(app)
    from tst_gestao.integracoes import iniciar_sincronizacao_dadosbi

    iniciar_sincronizacao_dadosbi(app.logger)
    servidor = make_server(BIND_HOST, PORT, app, threaded=True)
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
