"""Área do administrador: usuários e integração com a URL (espelho e monitor de alterações)."""
from __future__ import annotations

from flask import Blueprint, abort, jsonify, render_template, request, session
from werkzeug.security import generate_password_hash

from .. import atualizador, config, espelho
from ..db import NIVEIS, ErroIntegridade, connect
from ..seguranca import exige

bp = Blueprint("admin", __name__)


# ---------------------------------------------------------------- usuários
@bp.get("/usuarios")
@exige("admin")
def usuarios():
    return render_template("usuarios.html", ativa="usuarios")


@bp.get("/api/usuarios")
@exige("admin")
def api_usuarios():
    with connect() as conn:
        rows = conn.execute("SELECT id, usuario, nome, nivel, ativo FROM usuarios ORDER BY LOWER(nome)")
        return jsonify([dict(r) for r in rows])


@bp.route("/api/usuarios", methods=["POST"])
@bp.route("/api/usuarios/<int:uid>", methods=["PUT"])
@exige("admin")
def api_usuario_salvar(uid=None):
    d = request.get_json(silent=True) or {}
    usuario, nome, nivel = (d.get("usuario") or "").strip(), (d.get("nome") or "").strip(), d.get("nivel")
    senha, ativo = d.get("senha") or "", 1 if d.get("ativo", 1) in (1, True, "1") else 0
    if not usuario or not nome or nivel not in NIVEIS:
        return jsonify(erro="Informe usuário, nome e perfil de acesso."), 400
    if (uid is None or senha) and len(senha) < 6:
        return jsonify(erro="A senha deve ter ao menos 6 caracteres."), 400
    try:
        with connect() as conn:
            if uid is None:
                conn.execute("INSERT INTO usuarios (usuario, nome, senha_hash, nivel, ativo, trocar_senha) VALUES (?,?,?,?,?,1)",
                             (usuario, nome, generate_password_hash(senha), nivel, ativo))
            else:
                if not conn.execute("SELECT 1 FROM usuarios WHERE id = ?", (uid,)).fetchone():
                    abort(404)
                if uid == session["uid"] and (nivel != "admin" or not ativo):
                    return jsonify(erro="Você não pode rebaixar ou desativar a própria conta."), 400
                conn.execute("UPDATE usuarios SET usuario=?, nome=?, nivel=?, ativo=? WHERE id=?", (usuario, nome, nivel, ativo, uid))
                if senha:
                    conn.execute("UPDATE usuarios SET senha_hash=?, trocar_senha=1 WHERE id=?", (generate_password_hash(senha), uid))
                if not conn.execute("SELECT 1 FROM usuarios WHERE nivel='admin' AND ativo=1").fetchone():
                    conn.rollback()
                    return jsonify(erro="Deve existir ao menos um administrador ativo."), 400
    except ErroIntegridade:
        return jsonify(erro="Este nome de usuário já existe."), 409
    return jsonify(ok=True)


@bp.delete("/api/usuarios/<int:uid>")
@exige("admin")
def api_usuario_excluir(uid):
    if uid == session["uid"]:
        return jsonify(erro="Você não pode excluir a própria conta."), 400
    with connect() as conn:
        conn.execute("DELETE FROM usuarios WHERE id = ?", (uid,))
    return jsonify(ok=True)


# ---------------------------------------------------------------- integração com a URL
@bp.get("/integracao")
@exige("admin")
def integracao():
    return render_template("integracao.html", ativa="integracao", url=espelho.url(), intervalo=espelho.INTERVALO // 60,
                           url_por_ambiente=bool(__import__("os").environ.get("TST_DADOSBI_URL")))


@bp.get("/api/integracao/status")
@exige("admin")
def integracao_status():
    return jsonify(espelho.status())


@bp.post("/api/integracao/sincronizar")
@exige("admin")
def integracao_sincronizar():
    try:
        return jsonify(espelho.sincronizar())
    except RuntimeError as exc:
        return jsonify(erro=str(exc)), 409 if "em andamento" in str(exc) else 502


@bp.get("/api/integracao/monitor")
@exige("admin")
def integracao_monitor():
    return jsonify(espelho.monitor())


@bp.post("/api/integracao/alertas/<int:alerta_id>/reconhecer")
@exige("admin")
def integracao_alerta_reconhecer(alerta_id):
    if not espelho.reconhecer_alerta(alerta_id):
        return jsonify(erro="Alerta não encontrado ou já reconhecido."), 404
    return jsonify(ok=True)


# ---------------------------------------------------------------- URL da Saúde Residence (fica só neste computador)
@bp.post("/api/integracao/url")
@exige("admin")
def integracao_url():
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")) or len(url) > 1000:
        return jsonify(erro="Informe um endereço que comece com http:// ou https://."), 400
    config.gravar(url_dadosbi=url)
    return jsonify(ok=True)


# ---------------------------------------------------------------- atualizações do sistema (sempre a pedido do admin)
@bp.get("/api/atualizacao")
@exige("admin")
def atualizacao_estado():
    return jsonify(atualizador.estado())


@bp.post("/api/atualizacao/verificar")
@exige("admin")
def atualizacao_verificar():
    return jsonify(atualizador.verificar())


@bp.post("/api/atualizacao/aplicar")
@exige("admin")
def atualizacao_aplicar():
    try:
        return jsonify(atualizador.aplicar())
    except atualizador.ErroAtualizacao as exc:
        return jsonify(erro=str(exc)), 409
    except OSError:
        return jsonify(erro="Não foi possível baixar ou instalar a atualização. Nada foi alterado; tente novamente."), 502
