"""Painel BI (gestor+) e Painel operacional (todos os perfis)."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, jsonify, render_template, request

from .. import fichas, notificacoes
from .. import operacional as op
from .. import painel as pn
from ..seguranca import exige
from . import datas

bp = Blueprint("paineis", __name__)

ABAS_PAINEL = [
    ("geral", "Visão geral"), ("mapa", "Mapa por bairro"), ("terapias", "Terapias"), ("complexidade", "Complexidade"),
    ("movimentacao", "Movimentação e mortalidade"), ("perfil", "Perfil dos pacientes"), ("profissionais", "Profissionais"),
]
ABAS_OPERACIONAL = [
    ("relatorios", "Relatórios pendentes", "relatorios"), ("profissional", "Profissional × atendimento", "profissional"),
    ("abrangencia", "Região de abrangência", "bairro"), ("fichas", "Fichas realizadas no App", "prontuario"),
    ("precos", "Tabela de preços", "dinheiro"),
]


@bp.get("/painel")
@exige("gestor")
def painel():
    return render_template("painel.html", ativa="painel", abas=ABAS_PAINEL, hoje=date.today().isoformat())


@bp.get("/api/painel")
@exige("gestor")
def api_painel():
    return jsonify(pn.gerar(*datas()))


@bp.get("/api/painel/detalhe")
@exige("gestor")
def api_painel_detalhe():
    try:
        return jsonify(pn.detalhe(request.args.get("tipo", ""), request.args.get("valor"), *datas()))
    except ValueError as exc:
        return jsonify(erro=str(exc)), 400


@bp.get("/operacional")
@exige("operacional")
def operacional():
    return render_template("operacional.html", ativa="operacional", abas=ABAS_OPERACIONAL, hoje=date.today().isoformat())


@bp.get("/api/operacional/<secao>")
@exige("operacional")
def api_operacional(secao):
    ini, fim = datas()
    if secao == "relatorios":
        return jsonify(op.relatorios())
    if secao == "profissionais":
        return jsonify(op.profissionais(ini, fim))
    if secao == "profissional":
        chave = request.args.get("chave", "")
        if not chave:
            abort(400, "Informe o profissional.")
        return jsonify(op.pacientes_profissional(chave, ini, fim))
    if secao == "abrangencia":
        return jsonify(op.abrangencia(ini, fim))
    if secao == "fichas":
        return jsonify(op.fichas(ini, fim))
    abort(404)


@bp.get("/api/ficha/<tipo>")
@exige("operacional")
def api_ficha(tipo):
    """Resumo completo de um bairro, profissional ou paciente (aberto pelo clique ou pela busca)."""
    valor = request.args.get("valor", "").strip()
    funcao = {"bairro": fichas.ficha_bairro, "profissional": fichas.ficha_profissional, "paciente": fichas.ficha_paciente}.get(tipo)
    if not funcao:
        abort(404)
    if not valor:
        abort(400, "Informe quem deve ser aberto.")
    try:
        return jsonify(funcao(valor, *datas()))
    except ValueError as exc:
        return jsonify(erro=str(exc)), 404


@bp.get("/api/busca")
@exige("operacional")
def api_busca():
    """Busca rápida de pacientes e profissionais pelo nome (campo no topo dos painéis)."""
    return jsonify(fichas.buscar(request.args.get("q", "")))


@bp.get("/api/notificacoes")
@exige("operacional")
def api_notificacoes():
    """Avisos gerados nas sincronizações, filtrados pelo perfil de quem está vendo."""
    from ..seguranca import nivel_atual
    try:
        desde = int(request.args.get("desde", 0))
    except ValueError:
        desde = 0
    return jsonify(notificacoes.listar(nivel_atual(), desde))
