"""Configurações locais (dados/config.json): ficam só no computador do cliente, nunca no executável.

Hoje guarda a URL da Saúde Residence. Ela não fica no código porque o executável é publicado para atualização
automática e a URL dá acesso a dados de pacientes.
"""
from __future__ import annotations

import json
import os

from .banco import DATA_DIR

ARQUIVO = DATA_DIR / "config.json"


def ler() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def gravar(**valores) -> dict:
    atual = ler()
    atual.update({k: v for k, v in valores.items() if v is not None})
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = ARQUIVO.with_suffix(".tmp")
    tmp.write_text(json.dumps(atual, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ARQUIVO)
    return atual
