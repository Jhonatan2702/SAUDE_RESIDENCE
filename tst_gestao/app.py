"""Aplicação Flask do TST-GESTÃO: painéis sobre o espelho da URL Saúde Residence."""
from __future__ import annotations

import os
import secrets

from flask import Flask, jsonify, render_template, request, session

from . import atualizador, espelho, versao
from .db import DATA_DIR, PERFIS, init_db
from .rotas import admin, auth, paineis
from .seguranca import nivel_atual, proteger, usuario_atual


def _chave_secreta() -> str:
    if os.environ.get("SECRET_KEY"):  # hospedagem: o disco é apagado a cada reinício, a chave vem do ambiente
        return os.environ["SECRET_KEY"]
    arquivo = DATA_DIR / ".secret_key"
    if not arquivo.exists():
        arquivo.write_text(secrets.token_hex(32))
    return arquivo.read_text()


def create_app() -> Flask:
    init_db()
    app = Flask(__name__)
    app.secret_key = _chave_secreta()
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True, MAX_CONTENT_LENGTH=2_000_000)
    if os.environ.get("TST_HOSPEDADO"):  # atrás do proxy HTTPS do Render
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        app.config.update(SESSION_COOKIE_SECURE=True)

    @app.get("/saude", endpoint="saude")
    def saude():
        """Verificação de vida para o Render e para o serviço que mantém o site acordado (não abre o banco)."""
        from datetime import datetime

        return {"ok": True, "versao": versao.VERSAO, "hora": datetime.now().isoformat(timespec="minutes")}

    app.before_request(proteger)
    for bp in (auth.bp, paineis.bp, admin.bp):
        app.register_blueprint(bp)

    @app.context_processor
    def contexto():
        u = usuario_atual()
        sinc = None
        if u:
            try:
                sinc = espelho.status()
            except Exception:  # o cabeçalho nunca deve derrubar a página
                sinc = None
        nova = atualizador.estado()["disponivel"] if u and nivel_atual() >= 3 else None
        return {"usuario": u, "csrf_token": session.get("csrf", ""), "nivel": nivel_atual(), "perfis": PERFIS, "sinc": sinc,
                "versao": versao.VERSAO, "nova_versao": nova}

    def erro(codigo: int, mensagem: str):
        if request.path.startswith("/api/"):
            return jsonify(erro=mensagem), codigo
        return render_template("erro.html", codigo=codigo, mensagem=mensagem), codigo

    @app.errorhandler(400)
    def requisicao_invalida(e):
        return erro(400, getattr(e, "description", None) or "Requisição inválida.")

    @app.errorhandler(403)
    def proibido(_):
        return erro(403, "Seu perfil de acesso não permite abrir esta área.")

    @app.errorhandler(404)
    def nao_encontrado(_):
        return erro(404, "Página ou registro não encontrado.")

    return app
