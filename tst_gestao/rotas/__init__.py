"""Rotas do TST-GESTÃO, separadas por área (Blueprints)."""
from datetime import date

from flask import abort, request


def datas() -> tuple[date | None, date | None]:
    """Lê `ini`/`fim` (AAAA-MM-DD) da query string."""
    try:
        ini = date.fromisoformat(request.args["ini"]) if request.args.get("ini") else None
        fim = date.fromisoformat(request.args["fim"]) if request.args.get("fim") else None
    except ValueError:
        abort(400, "Período inválido.")
    return ini, fim
