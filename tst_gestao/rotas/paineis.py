"""Painel BI (gestor+) e Painel operacional (todos os perfis)."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, abort, jsonify, render_template, request

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


@bp.get("/api/bairro")
@exige("operacional")
def api_bairro():
    """Ficha do bairro clicado no mapa (Painel BI e mapa de cobertura do Painel operacional)."""
    nome = request.args.get("nome", "").strip()
    if not nome:
        abort(400, "Informe o bairro.")
    return jsonify(pn.ficha_bairro(nome, *datas()))


@bp.get("/api/historico")
@exige("operacional")
def api_historico():
    """Histórico de visitas de um paciente (aberto a partir das listas)."""
    try:
        return jsonify(pn.historico_paciente(request.args.get("paciente", "")))
    except ValueError as exc:
        return jsonify(erro=str(exc)), 404
