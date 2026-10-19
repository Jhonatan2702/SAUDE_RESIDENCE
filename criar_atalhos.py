"""Gera o ícone (.ico) e os atalhos do TST-GESTÃO (Área de Trabalho e pasta do projeto). Sem terminal."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent
ICO = BASE / "tst_gestao" / "static" / "tst.ico"


def criar_icone() -> None:
    img = Image.open(BASE / "tst_gestao" / "static" / "logo.png").convert("RGBA")
    lado = max(img.size)
    quadro = Image.new("RGBA", (lado, lado), (0, 0, 0, 0))
    quadro.paste(img, ((lado - img.width) // 2, (lado - img.height) // 2))
    quadro.save(ICO, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])


def criar_atalhos() -> None:
    pythonw = BASE / ".venv" / "Scripts" / "pythonw.exe"
    destinos = [Path(os.environ["USERPROFILE"]) / "Desktop", BASE]
    onedrive = os.environ.get("OneDrive")
    if onedrive and (Path(onedrive) / "Desktop").is_dir():
        destinos.append(Path(onedrive) / "Desktop")
    ps = ["$w = New-Object -ComObject WScript.Shell"]
    for pasta in destinos:
        if pasta.is_dir():
            ps.append(
                f"$s = $w.CreateShortcut('{pasta / 'TST-GESTÃO.lnk'}'); $s.TargetPath = '{pythonw}'; "
                f"$s.Arguments = '\"{BASE / 'main.py'}\"'; $s.WorkingDirectory = '{BASE}'; "
                f"$s.IconLocation = '{ICO}'; $s.Description = 'TST-GESTÃO'; $s.Save()"
            )
    subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(ps)], check=True)


if __name__ == "__main__":
    criar_icone()
    criar_atalhos()
    print("Ícone e atalhos criados.")
