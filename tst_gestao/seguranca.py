"""Sessão, perfis de acesso e proteção CSRF."""
from __future__ import annotations

import secrets
from functools import wraps

from flask import abort, g, jsonify, redirect, request, session, url_for

from .db import NIVEIS, connect

LIVRES = {"auth.login", "static"}
TROCA_SENHA = {"auth.perfil", "auth.logout", "auth.api_senha"}


def usuario_atual():
    if "usuario" not in g:
        uid = session.get("uid")
        u = None
        if uid:
            with connect() as conn:
                u = conn.execute("SELECT * FROM usuarios WHERE id = ? AND ativo = 1", (uid,)).fetchone()
        g.usuario = u
    return g.usuario


def nivel_atual() -> int:
    u = usuario_atual()
    return NIVEIS.get(u["nivel"], 0) if u else 0


def exige(perfil: str):
    """Libera a rota para o perfil indicado e para os perfis acima dele."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if nivel_atual() < NIVEIS[perfil]:
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def pagina_inicial() -> str:
    return url_for("paineis.painel") if nivel_atual() >= NIVEIS["gestor"] else url_for("paineis.operacional")


def proteger():
    """before_request: CSRF em toda escrita, login obrigatório e troca de senha no primeiro acesso."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    if request.method in ("POST", "PUT", "DELETE"):
        token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
        if not token or not secrets.compare_digest(token, session["csrf"]):
            abort(400, "Token inválido. Recarregue a página.")
    if request.endpoint in LIVRES or request.endpoint is None:
        return None
    u = usuario_atual()
    if not u:
        if request.path.startswith("/api/"):
            return jsonify(erro="Sessão expirada."), 401
        return redirect(url_for("auth.login"))
    if u["trocar_senha"] and request.endpoint not in TROCA_SENHA:
        if request.path.startswith("/api/"):
            return jsonify(erro="Defina uma nova senha antes de continuar."), 403
        return redirect(url_for("auth.perfil"))
    return None
