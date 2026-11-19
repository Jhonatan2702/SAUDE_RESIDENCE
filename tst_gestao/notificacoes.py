"""Avisos na tela após cada sincronização: só o que MUDOU desde a anterior e pede ação de alguém.

A cada sincronização bem-sucedida, `processar()` tira uma "fotografia" da situação (óbitos, altas, atendimentos
ativos, pendências de terapia, orçamentos vencidos, bairros sem ninguém, relatórios antigos), compara com a
fotografia anterior e grava um aviso por tipo de novidade. Na primeira vez só guarda a fotografia, para não
disparar avisos de coisas antigas.

Gravidade: crit (fica na tela até fechar), warn e info (somem sozinhos). nivel_min: 1 todos, 2 gestor+, 3 admin.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from .db import connect
from .fonte import JANELA_COBERTURA, NOMES_TERAPIA, carregar, em_fortaleza, tem_terapias
from .painel import SEM_ATENDIMENTO, _Contexto, situacao_orcamento

DIAS_RELATORIO = 60          # relatório pendente "antigo"
LIMITE_GUARDADAS = 500
MOSTRAR_NOMES = 4


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def registrar(tipo: str, gravidade: str, titulo: str, texto: str = "", link: dict | None = None, nivel_min: int = 1) -> None:
    with connect() as conn:
        conn.execute("INSERT INTO notificacoes (criado_em, tipo, gravidade, titulo, texto, link, nivel_min) VALUES (?,?,?,?,?,?,?)",
                     (_agora(), tipo, gravidade, titulo[:200], texto[:1000], json.dumps(link or {}, ensure_ascii=False), nivel_min))
        conn.execute("DELETE FROM notificacoes WHERE id NOT IN (SELECT id FROM notificacoes ORDER BY id DESC LIMIT ?)", (LIMITE_GUARDADAS,))


def listar(nivel: int, desde: int = 0, limite: int = 30) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM notificacoes WHERE nivel_min <= ? AND id > ? ORDER BY id DESC LIMIT ?", (nivel, desde, limite))
        saida = [dict(r) for r in rows]
    for n in saida:
        n["link"] = json.loads(n["link"] or "{}")
    return saida


def _nomes(lista: list[str]) -> str:
    lista = sorted(set(lista), key=str.casefold)
    extra = len(lista) - MOSTRAR_NOMES
    return ", ".join(lista[:MOSTRAR_NOMES]) + (f" e mais {extra}" if extra > 0 else "")


def _competencia_antiga(comp: str | None, dia: date) -> bool:
    """Competência AAAA-MM (ou MM/AAAA) cujo mês terminou há mais de DIAS_RELATORIO dias."""
    c = (comp or "").strip()
    try:
        ano, mes = (int(c[:4]), int(c[5:7])) if c[4:5] == "-" else (int(c[3:7]), int(c[:2]))
        fim_mes = date(ano + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)
    except (ValueError, IndexError):
        return False
    return (dia - fim_mes).days > DIAS_RELATORIO


def fotografia(dia: date | None = None) -> dict:
    """Situação atual dos indicadores que geram aviso (só identificadores, para comparar)."""
    dia = dia or date.today()
    base = carregar()
    c = _Contexto(base, dia, dia)
    inicio_cob = dia - timedelta(days=JANELA_COBERTURA - 1)
    cobertos = {base.por_id[v["atendimento_origem_id"]]["bairro"] for v in base.visitas
                if inicio_cob <= v["_data"] <= dia and v["atendimento_origem_id"] in base.por_id}
    indicados = {a["bairro"] for a in c.ativos_at if tem_terapias(a) and a["bairro"] and em_fortaleza(a)}
    return {
        "obitos": {a["origem_id"]: [a["nome_paciente"], a["operadora"] or "—"] for a in base.atend if a["_alta"] and "bito" in (a["condicao_alta"] or "").lower()},
        "altas": {a["origem_id"]: a["nome_paciente"] for a in base.atend if a["_alta"] and "bito" not in (a["condicao_alta"] or "").lower()},
        "ativos": {a["origem_id"]: [a["nome_paciente"], a["servico"] or "—", tem_terapias(a)] for a in c.ativos_at},
        "pendentes": {t: sorted(c.rep[p]["nome_paciente"] for p in ps) for t, ps in c.pend.items()},
        "orc_vencidos": {a["origem_id"]: [a["nome_paciente"], a["operadora"] or "—"] for a in c.ativos_at if situacao_orcamento(a, dia) == "vencido"},
        "sem_ninguem": sorted(indicados - cobertos),
        "rel_antigos": {r["id"]: [r["paciente"], r.get("profissional") or "—"] for r in base.relatorios_pendentes()
                        if r.get("id") and _competencia_antiga(r.get("competencia"), dia)},
    }


def comparar(antes: dict, agora: dict) -> list[dict]:
    """Avisos com o que apareceu em `agora` e não existia em `antes` (um aviso por tipo de novidade)."""
    avisos = []

    def novos(campo):
        a, b = antes.get(campo, {}), agora.get(campo, {})
        return {k: v for k, v in b.items() if k not in a}

    if obitos := novos("obitos"):
        nomes = [v[0] for v in obitos.values()]
        avisos.append(dict(tipo="obito", gravidade="crit", titulo=f"{len(nomes)} óbito(s) registrado(s)",
                           texto=f"{_nomes(nomes)}. Verifique as visitas agendadas e avise a equipe.",
                           link={"paciente": nomes[0], "aba": "movimentacao"} if len(nomes) == 1 else {"aba": "movimentacao"}))
    if bairros := sorted(set(agora.get("sem_ninguem", [])) - set(antes.get("sem_ninguem", []))):
        avisos.append(dict(tipo="sem_cobertura", gravidade="crit", titulo=f"{len(bairros)} bairro(s) sem nenhum profissional",
                           texto=f"{_nomes(bairros)}: há paciente com terapia indicada e ninguém atendeu lá nos últimos {JANELA_COBERTURA} dias.",
                           link={"bairro": bairros[0], "aba": "abrangencia"} if len(bairros) == 1 else {"aba": "abrangencia"}))
    pend_novos = {t: sorted(set(ps) - set(antes.get("pendentes", {}).get(t, []))) for t, ps in agora.get("pendentes", {}).items()}
    pend_novos = {t: ps for t, ps in pend_novos.items() if ps}
    if pend_novos:
        total = sorted({p for ps in pend_novos.values() for p in ps})
        partes = [f"{'sem nenhuma terapia' if t == SEM_ATENDIMENTO else NOMES_TERAPIA.get(t, t)} ({len(ps)})" for t, ps in pend_novos.items()]
        avisos.append(dict(tipo="pendencia", gravidade="warn", titulo=f"{len(total)} paciente(s) com nova terapia pendente",
                           texto=f"{', '.join(partes)}: {_nomes(total)}.",
                           link={"paciente": total[0], "aba": "terapias"} if len(total) == 1 else {"aba": "terapias"}))
    if venc := novos("orc_vencidos"):
        nomes = [v[0] for v in venc.values()]
        avisos.append(dict(tipo="orcamento", gravidade="warn", titulo=f"{len(nomes)} orçamento(s) venceram",
                           texto=f"Atendimentos ativos que precisam de renovação com a operadora: {_nomes(nomes)}.",
                           link={"aba": "geral"}, nivel_min=2))
    if rel := novos("rel_antigos"):
        profs = [v[1] for v in rel.values()]
        avisos.append(dict(tipo="relatorio", gravidade="warn", titulo=f"{len(rel)} relatório(s) pendente(s) há mais de {DIAS_RELATORIO} dias",
                           texto=f"Profissionais: {_nomes(profs)}.", link={"aba": "relatorios", "pagina": "operacional"}))
    if adm := novos("ativos"):
        com_terapia = [v[0] for v in adm.values() if v[2]]
        avisos.append(dict(tipo="admissao", gravidade="info", titulo=f"{len(adm)} nova(s) admissão(ões)",
                           texto=f"{_nomes([v[0] for v in adm.values()])}." + (f" Com terapia indicada (precisam de profissional): {_nomes(com_terapia)}." if com_terapia else ""),
                           link={"paciente": next(iter(adm.values()))[0]} if len(adm) == 1 else {"aba": "geral"}))
    if altas := novos("altas"):
        nomes = list(altas.values())
        avisos.append(dict(tipo="alta", gravidade="info", titulo=f"{len(nomes)} alta(s) registrada(s)",
                           texto=f"{_nomes(nomes)}. Encerre as visitas desses atendimentos.",
                           link={"paciente": nomes[0]} if len(nomes) == 1 else {"aba": "movimentacao"}))
    return avisos


def processar(dia: date | None = None) -> list[dict]:
    """Chamado após cada sincronização bem-sucedida. Devolve os avisos gerados."""
    agora = fotografia(dia)
    with connect() as conn:
        linha = conn.execute("SELECT id, estado_json FROM notificacoes_estado ORDER BY id").fetchone()
        if linha:
            conn.execute("UPDATE notificacoes_estado SET estado_json=?, atualizado_em=? WHERE id=?",
                         (json.dumps(agora, ensure_ascii=False), _agora(), linha["id"]))
        else:
            conn.execute("INSERT INTO notificacoes_estado (estado_json, atualizado_em) VALUES (?,?)",
                         (json.dumps(agora, ensure_ascii=False), _agora()))
    if not linha:
        return []  # primeira fotografia: nada a comparar
    avisos = comparar(json.loads(linha["estado_json"]), agora)
    for a in avisos:
        registrar(**a)
    return avisos


def falha_sincronizacao(erro: str) -> None:
    """Aviso ao admin, no máximo um a cada 3 horas, para não repetir a cada tentativa."""
    with connect() as conn:
        ultimo = conn.execute("SELECT criado_em FROM notificacoes WHERE tipo='falha_sync' ORDER BY id DESC LIMIT 1").fetchone()
    if ultimo and datetime.fromisoformat(ultimo["criado_em"]) > datetime.now() - timedelta(hours=3):
        return
    registrar("falha_sync", "crit", "A sincronização com a URL falhou", f"{erro} Os números podem estar desatualizados.",
              {"url": "/integracao"}, nivel_min=3)


def formato_alterado(qtd: int) -> None:
    registrar("formato_url", "info", f"A URL passou a enviar {qtd} novidade(s) de formato",
              "Campos ou categorias novas: podem virar indicadores no painel. Confira o monitor de alterações.",
              {"url": "/integracao"}, nivel_min=3)
