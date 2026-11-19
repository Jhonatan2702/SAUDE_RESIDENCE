"""Login, logout e troca de senha."""
from __future__ import annotations

import secrets

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import connect
from ..seguranca import pagina_inicial, usuario_atual

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        with connect() as conn:
            u = conn.execute("SELECT * FROM usuarios WHERE LOWER(usuario) = LOWER(?) AND ativo = 1",
                             (request.form.get("usuario", "").strip(),)).fetchone()
        if u and check_password_hash(u["senha_hash"], request.form.get("senha", "")):
            session.clear()
            session["uid"] = u["id"]
            session["csrf"] = secrets.token_hex(16)
            return redirect(url_for("auth.inicio"))
        erro = "Usuário ou senha inválidos."
    return render_template("login.html", erro=erro)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.get("/")
def inicio():
    """Cada perfil abre na sua própria página."""
    return redirect(pagina_inicial())


@bp.get("/ajuda")
def ajuda():
    """Guia de uso: primeiros passos, rotinas, o que cada tela responde, glossário e perguntas frequentes."""
    from ..fonte import JANELA_ATRASO, JANELA_TERAPIA
    from ..rotas.paineis import ABAS_OPERACIONAL, ABAS_PAINEL
    return render_template("ajuda.html", ativa="ajuda", abas_painel=ABAS_PAINEL, abas_operacional=ABAS_OPERACIONAL,
                           janela=JANELA_TERAPIA, atraso=JANELA_ATRASO)


@bp.get("/perfil")
def perfil():
    return render_template("perfil.html", ativa="perfil")


@bp.post("/api/senha")
def api_senha():
    d = request.get_json(silent=True) or {}
    u = usuario_atual()
    nova = d.get("nova", "")
    if not check_password_hash(u["senha_hash"], d.get("atual", "")):
        return jsonify(erro="Senha atual incorreta."), 400
    if len(nova) < 6 or nova == "admin":
        return jsonify(erro="A nova senha deve ter ao menos 6 caracteres e não pode ser 'admin'."), 400
    with connect() as conn:
        conn.execute("UPDATE usuarios SET senha_hash = ?, trocar_senha = 0 WHERE id = ?", (generate_password_hash(nova), u["id"]))
    return jsonify(ok=True)
