"""Fichas de resumo: bairro, profissional e paciente — tudo o que está ligado a cada um, num formato único.

Formato devolvido (o mesmo para os três tipos, desenhado por static/ficha.js):
    {tipo, titulo, trilha, chips: [{texto, tom}], kpis: [{rotulo, valor, sub, tom, aba}],
     abas: [{id, nome, desc, tipo: "tabela"|"barras"|"dados", ...}]}
- tabela: colunas, linhas, abrir {tipo, col} (col pode ser uma coluna oculta além das colunas visíveis), filtros, numericas
- barras: itens [{rotulo, valor}], abrir {tipo}
- dados: pares [[rótulo, valor]]
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from . import operacional as op
from .fonte import (BAIRROS_OFICIAIS, JANELA_ATRASO, JANELA_COBERTURA, JANELA_TERAPIA, NOMES_TERAPIA, TERAPIAS, Base, bairro_padrao, br,
                    ativo_em, carregar, chave_paciente, eh_monitoramento, eh_obito, nivel, periodo, sem_acento, tem_terapias)
from .painel import (COLS_COBERTURA, SEM_ATENDIMENTO, SITUACOES_ORCAMENTO, TODAS, _Contexto, _mapa_conjuntos, cobertura,
                     situacao_orcamento)

MESES_SERIE = 12
NOME_MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _norm(t: str) -> str:
    return " ".join(sem_acento(t or "").casefold().split())


def _serie_mensal(datas: list[date], fim: date) -> list[dict]:
    """Quantidade por mês nos últimos MESES_SERIE meses até `fim` (do mais recente para o mais antigo)."""
    cont = Counter(d.strftime("%Y-%m") for d in datas)
    saida, a, m = [], fim.year, fim.month
    for _ in range(MESES_SERIE):
        chave = f"{a:04d}-{m:02d}"
        saida.append({"rotulo": f"{NOME_MES[m - 1]}/{str(a)[2:]}", "valor": cont.get(chave, 0)})
        a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    return saida


def _zona(base: Base, a: dict) -> str:
    return base.zonas.get(a["zona"], {}).get("nome", "—") if a.get("zona") else "—"


def _situacao_paciente(base: Base, c: _Contexto, p: str) -> str:
    if p in c.ativos:
        return "Ativo"
    lst = [a for a in base.atend if a["_pac"] == p]
    return "Óbito" if any(eh_obito(a) for a in lst) else "Alta"


COLS_ALTAS = ["Paciente", "Serviço", "Operadora", "Admissão", "Alta", "Condição de alta", "Dias de atendimento", "Bairro"]


def _linhas_altas(lista: list[dict]) -> list[list]:
    """Atendimentos que receberam alta (sem óbitos), da mais recente para a mais antiga."""
    return [[a["nome_paciente"], a["servico"] or "—", a["operadora"] or "—", br(a["_adm"]), br(a["_alta"]), a["condicao_alta"] or "—",
             (a["_alta"] - a["_adm"]).days if a["_adm"] else "", a["bairro"] or "—"]
            for a in sorted(lista, key=lambda a: a["_alta"], reverse=True)]


# ---------------------------------------------------------------- bairro
def ficha_bairro(nome: str, ini: date | None = None, fim: date | None = None) -> dict:
    ini, fim = periodo(ini, fim)
    base = carregar()
    c = _Contexto(base, ini, fim)
    bairro = bairro_padrao(nome) or " ".join(sem_acento(nome).upper().split())
    conj = _mapa_conjuntos(base, c)[0].get(bairro, {})
    tot = lambda m: conj.get(m, {}).get(TODAS, ())  # noqa: E731

    pacientes_bairro = tot("ativos")
    janela_ini = fim - timedelta(days=JANELA_TERAPIA - 1)
    quem: dict[str, set] = {}
    for v in base.visitas:
        a = base.por_id.get(v["atendimento_origem_id"])
        if a and a["_pac"] in pacientes_bairro and janela_ini <= v["_data"] <= fim and v["profissional"]:
            quem.setdefault(a["_pac"], set()).add(f'{v["profissional"]} ({v["_ter"]})')
    ult = c.ultima_visita()
    pacientes = []
    for p in sorted(pacientes_bairro, key=lambda p: c.rep[p]["nome_paciente"].casefold()):
        lst, r, ters = c.ativos[p], c.rep[p], c.ter_janela.get(p, {})
        pend = [NOMES_TERAPIA.get(t, t) if t != SEM_ATENDIMENTO else "nenhuma terapia em 90 dias" for t, ps in c.pend.items() if p in ps]
        pacientes.append([r["nome_paciente"], " · ".join(sorted({a["operadora"] or "—" for a in lst})),
                          " · ".join(sorted({a["servico"] or "—" for a in lst})), " · ".join(t for t in TERAPIAS if t in ters) or "—",
                          ", ".join(pend) or "—", "; ".join(sorted(quem.get(p, ()))) or "—", br(ult.get(p))])
    terapias = [[NOMES_TERAPIA[t], len(conj.get("em_terapia", {}).get(t, ())), len(conj.get("pendentes", {}).get(t, ())),
                 len(conj.get("visitas", {}).get(t, [])), len(conj.get("profissionais", {}).get(t, ()))]
                for t in TERAPIAS if conj.get("em_terapia", {}).get(t) or conj.get("visitas", {}).get(t) or conj.get("pendentes", {}).get(t)]
    zonas = sorted(info["nome"] for info in base.zonas.values() if bairro in info["bairros"])
    rel = op.linhas_relatorios(list(tot("relatorios")))
    cob = cobertura(base, c, bairro)
    so_cobrem = sum(1 for l in cob if l[4] == 0)
    altas = _linhas_altas(list(tot("altas")))
    if not tot("profissionais") and tot("ativos"):
        situacao = ({"texto": f"Descoberto no período · coberto por {len(cob)} profissional(is)", "tom": "warn"} if cob
                    else {"texto": f"Sem profissional nos últimos {JANELA_COBERTURA} dias", "tom": "crit"})
    else:
        situacao = None
    r = {m: len(tot(m)) for m in ("ativos", "em_terapia", "pendentes", "visitas", "profissionais", "relatorios")}
    sem_terapia = len(conj.get("pendentes", {}).get(SEM_ATENDIMENTO, ()))
    return {
        "tipo": "bairro", "titulo": bairro, "trilha": "Bairro", "oficial": bairro in BAIRROS_OFICIAIS,
        "periodo": {"ini": ini.isoformat(), "fim": fim.isoformat()},
        "chips": ([situacao] if situacao else []) + [{"texto": f"Zona {z}", "tom": "acc"} for z in zonas]
                 + ([] if bairro in BAIRROS_OFICIAIS else [{"texto": "fora dos bairros oficiais de Fortaleza", "tom": "warn"}]),
        "kpis": [
            {"rotulo": "Pacientes ativos", "valor": r["ativos"], "tom": "acc", "aba": "pacientes"},
            {"rotulo": "Em terapia", "valor": r["em_terapia"], "sub": "últimos 90 dias", "tom": "acc", "aba": "pacientes"},
            {"rotulo": "Com pendência", "valor": r["pendentes"], "sub": f"{sem_terapia} sem nenhuma terapia" if sem_terapia else "",
             "tom": "warn", "aba": "pacientes"},
            {"rotulo": "Profissionais", "valor": r["profissionais"],
             "sub": f"no período · +{so_cobrem} cobrem o bairro" if so_cobrem else "com visita no período", "tom": "acc", "aba": "profissionais"},
            {"rotulo": "Altas", "valor": len(altas), "sub": "no período", "tom": "ok", "aba": "altas"},
            {"rotulo": "Visitas", "valor": r["visitas"], "sub": "no período", "tom": "neutro", "aba": "profissionais"},
            {"rotulo": "Relatórios pendentes", "valor": r["relatorios"], "tom": "warn", "aba": "relatorios"},
        ],
        "abas": [
            {"id": "profissionais", "nome": "Profissionais", "tipo": "tabela",
             "desc": f"Quem atende este bairro: “Atendendo no período” teve visita no período; “Cobre o bairro” atendeu alguém aqui nos "
                     f"últimos {JANELA_COBERTURA} dias, mesmo sem visita agora. Clique para abrir o resumo do profissional.",
             "colunas": COLS_COBERTURA, "linhas": cob, "numericas": [3, 4, 5], "abrir": {"tipo": "profissional", "col": 7},
             "filtros": [{"rotulo": "Todos que cobrem o bairro"}, {"rotulo": "Só atendendo no período", "col": 4, "positivo": True}]},
            {"id": "pacientes", "nome": "Pacientes", "tipo": "tabela",
             "desc": "Pacientes ativos do bairro, terapias dos últimos 90 dias, pendências e quem os atende. Clique para abrir o resumo do paciente.",
             "colunas": ["Paciente", "Operadora", "Serviço", f"Terapias ({JANELA_TERAPIA} d)", "Pendências", f"Atendido por ({JANELA_TERAPIA} d)", "Última visita"],
             "linhas": pacientes, "abrir": {"tipo": "paciente", "col": 0},
             "filtros": [{"rotulo": "Todos os pacientes ativos"}, {"rotulo": "Só em terapia", "col": 3}, {"rotulo": "Só com pendência", "col": 4}]},
            {"id": "terapias", "nome": "Terapias", "tipo": "tabela", "desc": "Situação de cada terapia no bairro.",
             "colunas": ["Terapia", "Pacientes", "Pendentes", "Visitas no período", "Profissionais"], "linhas": terapias, "numericas": [1, 2, 3, 4]},
            {"id": "altas", "nome": "Altas", "tipo": "tabela", "desc": "Pacientes do bairro que receberam alta no período (óbitos ficam de fora). Clique para abrir o resumo do paciente.",
             "colunas": COLS_ALTAS, "linhas": altas, "numericas": [6], "abrir": {"tipo": "paciente", "col": 0}},
            {"id": "relatorios", "nome": "Relatórios pendentes", "tipo": "tabela", "desc": "Relatórios pendentes dos pacientes deste bairro.",
             "colunas": rel["colunas"], "linhas": rel["linhas"], "abrir": {"tipo": "paciente", "col": 0}},
            {"id": "operadoras", "nome": "Operadoras", "tipo": "barras", "desc": "Convênio dos pacientes ativos do bairro.",
             "itens": [{"rotulo": k, "valor": v} for k, v in Counter(o for p in pacientes_bairro for o in {a["operadora"] or "Não informada" for a in c.ativos[p]}).most_common()]},
        ],
    }


# ---------------------------------------------------------------- profissional
def _resolver_profissional(base: Base, valor: str) -> str | None:
    """Aceita a chave (id:/nome:) ou só o nome (ex.: vindo da lista de relatórios)."""
    if valor.startswith(("id:", "nome:")):
        return valor
    alvo = _norm(valor)
    for v in reversed(base.visitas):
        if _norm(v["profissional"]) == alvo:
            return op.chave_profissional(v)
    for r in base.relatorios_pendentes():
        if _norm(r.get("profissional")) == alvo:
            return "id:" + r["profissional_id"] if r.get("profissional_id") else "nome:" + r["profissional"]
    return None


def ficha_profissional(valor: str, ini: date | None = None, fim: date | None = None) -> dict:
    ini, fim = periodo(ini, fim)
    base = carregar()
    chave = _resolver_profissional(base, valor)
    todas = [v for v in base.visitas if chave and op.chave_profissional(v) == chave and v["_data"] <= fim]
    if not chave or not (todas or any(_rel_do(r, chave) for r in base.relatorios_pendentes())):
        raise ValueError("Profissional não encontrado.")
    c = _Contexto(base, ini, fim)
    nome = next((v["profissional"] for v in reversed(todas) if v["profissional"]), None) or chave.split(":", 1)[1]
    no_periodo = [v for v in todas if ini <= v["_data"] <= fim]
    ters = Counter(v["_ter"] for v in todas)

    # pacientes atendidos no período
    pac: dict[str, dict] = {}
    for v in no_periodo:
        a = base.por_id.get(v["atendimento_origem_id"])
        if not a:
            continue
        g = pac.setdefault(a["_pac"], {"a": a, "vis": 0, "ini": v["_data"], "fim": v["_data"], "ter": set()})
        g["vis"] += 1
        g["ini"], g["fim"] = min(g["ini"], v["_data"]), max(g["fim"], v["_data"])
        g["ter"].add(v["_ter"])
    linhas_pac = []
    for p, g in sorted(pac.items(), key=lambda kv: kv[1]["a"]["nome_paciente"].casefold()):
        a = c.rep.get(p, g["a"])
        pendente = [NOMES_TERAPIA.get(t, t) for t in g["ter"] if p in c.pend.get(t, ())]
        linhas_pac.append([a["nome_paciente"], a["bairro"] or "—", _zona(base, a), a["operadora"] or "—", " · ".join(sorted(g["ter"])),
                           g["vis"], br(g["ini"]), br(g["fim"]), _situacao_paciente(base, c, p), ", ".join(pendente) or "—"])

    # pacientes que ele atendeu nos últimos 90 dias e que estão pendentes na terapia dele
    janela_ini = fim - timedelta(days=JANELA_TERAPIA - 1)
    ult_dele: dict[tuple, date] = {}
    for v in todas:
        a = base.por_id.get(v["atendimento_origem_id"])
        if a and v["_data"] >= janela_ini:
            k = (a["_pac"], v["_ter"])
            ult_dele[k] = max(ult_dele.get(k, v["_data"]), v["_data"])
    pendencias = []
    for (p, t), d in sorted(ult_dele.items(), key=lambda kv: kv[1]):
        if p in c.pend.get(t, ()):
            ultima_geral = c.ter_janela.get(p, {}).get(t, d)
            pendencias.append([c.rep[p]["nome_paciente"], NOMES_TERAPIA.get(t, t), br(d), br(ultima_geral), (fim - ultima_geral).days,
                               c.rep[p]["bairro"] or "—"])

    bairros = Counter()
    zonas = Counter()
    for p, g in pac.items():
        bairros[g["a"]["bairro"] or "NÃO INFORMADO"] += 1
        zonas[_zona(base, g["a"])] += 1
    rel = op.linhas_relatorios([r for r in base.relatorios_pendentes() if _rel_do(r, chave)])
    dias = len({v["_data"] for v in no_periodo})
    # região que ele cobre: bairros onde visitou alguém nos últimos JANELA_COBERTURA dias (mesmo sem visita no período)
    inicio_cob = fim - timedelta(days=JANELA_COBERTURA - 1)
    regiao: dict[str, dict] = {}
    pacientes_cob: set[str] = set()
    for v in todas:
        a = base.por_id.get(v["atendimento_origem_id"])
        if not a or v["_data"] < inicio_cob:
            continue
        pacientes_cob.add(a["_pac"])
        g = regiao.setdefault(a["bairro"] or "NÃO INFORMADO", {"pac": set(), "per": 0, "ultima": v["_data"], "zonas": set()})
        g["pac"].add(a["_pac"])
        g["per"] += ini <= v["_data"]
        g["ultima"] = max(g["ultima"], v["_data"])
        if a.get("zona"):
            g["zonas"].add(_zona(base, a))
    linhas_regiao = [[b, ", ".join(sorted(g["zonas"])) or "—", len(g["pac"]), g["per"], br(g["ultima"]),
                      "Atendendo no período" if g["per"] else "Cobre o bairro"]
                     for b, g in sorted(regiao.items(), key=lambda kv: (kv[1]["per"] == 0, -len(kv[1]["pac"]), kv[0]))]
    # pacientes dele (últimos JANELA_COBERTURA dias) que receberam alta no período
    altas = _linhas_altas([a for a in base.atend if a["_pac"] in pacientes_cob and a["_alta"] and ini <= a["_alta"] <= fim and not eh_obito(a)])
    visitas_linhas = [[br(v["_data"]), base.por_id[v["atendimento_origem_id"]]["nome_paciente"], v["_ter"],
                       base.por_id[v["atendimento_origem_id"]]["bairro"] or "—", v["atendimento_origem_id"]]
                      for v in sorted(no_periodo, key=lambda v: v["_data"], reverse=True) if v["atendimento_origem_id"] in base.por_id]
    return {
        "tipo": "profissional", "titulo": nome, "trilha": "Profissional", "periodo": {"ini": ini.isoformat(), "fim": fim.isoformat()},
        "chips": [{"texto": NOMES_TERAPIA.get(t, t), "tom": "acc"} for t, _ in ters.most_common(3)]
                 + [{"texto": chave.replace("id:", "ID ").replace("nome:", "sem ID na URL · "), "tom": ""}],
        "kpis": [
            {"rotulo": "Visitas", "valor": len(no_periodo), "sub": "no período", "tom": "acc", "aba": "visitas"},
            {"rotulo": "Pacientes", "valor": len(pac), "sub": "atendidos no período", "tom": "acc", "aba": "pacientes"},
            {"rotulo": "Dias com visita", "valor": dias, "sub": f"{round(len(no_periodo) / dias, 1) if dias else 0} visitas por dia".replace(".", ","),
             "tom": "neutro", "aba": "visitas"},
            {"rotulo": "Bairros", "valor": len([b for b in bairros if b != "NÃO INFORMADO"]),
             "sub": f"no período · cobre {len([b for b in regiao if b != 'NÃO INFORMADO'])} em {JANELA_COBERTURA} dias", "tom": "acc", "aba": "regiao"},
            {"rotulo": "Altas", "valor": len(altas), "sub": "pacientes dele no período", "tom": "ok", "aba": "altas"},
            {"rotulo": "Pacientes pendentes", "valor": len(pendencias), "sub": f"sem visita há +{JANELA_ATRASO} dias", "tom": "warn", "aba": "pendencias"},
            {"rotulo": "Relatórios pendentes", "valor": len(rel["linhas"]), "tom": "warn", "aba": "relatorios"},
        ],
        "abas": [
            {"id": "pacientes", "nome": "Pacientes", "tipo": "tabela",
             "desc": "Pacientes que ele atendeu no período. Clique para abrir o resumo do paciente.",
             "colunas": ["Paciente", "Bairro", "Zona", "Operadora", "Terapias", "Visitas", "Primeira", "Última", "Situação", "Pendente em"],
             "linhas": linhas_pac, "numericas": [5], "abrir": {"tipo": "paciente", "col": 0},
             "filtros": [{"rotulo": "Todos"}, {"rotulo": "Só com pendência", "col": 9}]},
            {"id": "pendencias", "nome": "Pendências", "tipo": "tabela",
             "desc": f"Pacientes que ele atendeu nos últimos {JANELA_TERAPIA} dias e estão há mais de {JANELA_ATRASO} dias sem visita da terapia dele. Os mais antigos primeiro.",
             "colunas": ["Paciente", "Terapia", "Última visita dele", "Última visita da terapia", "Dias sem visita", "Bairro"],
             "linhas": sorted(pendencias, key=lambda l: -l[4]), "numericas": [4], "abrir": {"tipo": "paciente", "col": 0}},
            {"id": "regiao", "nome": "Região que cobre", "tipo": "tabela",
             "desc": f"Bairros onde ele atendeu alguém nos últimos {JANELA_COBERTURA} dias. “Cobre o bairro” = atende a região, mesmo sem visita "
                     f"no período. Clique para abrir a ficha do bairro.",
             "colunas": ["Bairro", "Zona(s)", f"Pacientes ({JANELA_COBERTURA} d)", "Visitas no período", "Última visita", "Situação"],
             "linhas": linhas_regiao, "numericas": [2, 3], "abrir": {"tipo": "bairro", "col": 0},
             "filtros": [{"rotulo": "Toda a região"}, {"rotulo": "Só atendendo no período", "col": 3, "positivo": True}]},
            {"id": "altas", "nome": "Altas", "tipo": "tabela", "desc": f"Pacientes dele (atendidos nos últimos {JANELA_COBERTURA} dias) que receberam alta no período.",
             "colunas": COLS_ALTAS, "linhas": altas, "numericas": [6], "abrir": {"tipo": "paciente", "col": 0}},
            {"id": "zonas", "nome": "Zonas", "tipo": "barras", "desc": "Pacientes por zona de atendimento no período.",
             "itens": [{"rotulo": k, "valor": v} for k, v in zonas.most_common()]},
            {"id": "visitas", "nome": "Visitas", "tipo": "tabela", "desc": "Todas as visitas (fichas do App) no período.",
             "colunas": ["Data", "Paciente", "Terapia", "Bairro", "Atendimento"], "linhas": visitas_linhas, "abrir": {"tipo": "paciente", "col": 1}},
            {"id": "relatorios", "nome": "Relatórios pendentes", "tipo": "tabela", "desc": "Relatórios que ele ainda precisa entregar (lista atual da URL).",
             "colunas": rel["colunas"], "linhas": rel["linhas"], "abrir": {"tipo": "paciente", "col": 0}},
            {"id": "mensal", "nome": "Mês a mês", "tipo": "barras", "desc": f"Visitas por mês nos últimos {MESES_SERIE} meses.",
             "itens": _serie_mensal([v["_data"] for v in todas], fim), "ordem": True},
        ],
    }


def _rel_do(r: dict, chave: str) -> bool:
    if chave.startswith("id:"):
        return r.get("profissional_id") == chave[3:]
    return _norm(r.get("profissional")) == _norm(chave[5:])


# ---------------------------------------------------------------- paciente
def ficha_paciente(nome: str, ini: date | None = None, fim: date | None = None) -> dict:
    ini, fim = periodo(ini, fim)
    base = carregar()
    p = chave_paciente(nome)
    atend = sorted((a for a in base.atend if a["_pac"] == p), key=lambda a: a["data_admissao"] or "", reverse=True)
    if not atend:
        raise ValueError("Paciente não encontrado.")
    c = _Contexto(base, ini, fim)
    ids = {a["origem_id"] for a in atend}
    vis = sorted((v for v in base.visitas if v["atendimento_origem_id"] in ids and v["_data"] <= fim), key=lambda v: v["_data"], reverse=True)
    r = c.rep.get(p) or atend[0]
    situacao = _situacao_paciente(base, c, p)
    ters90 = c.ter_janela.get(p, {})
    corte = fim - timedelta(days=JANELA_ATRASO - 1)

    terapias = []
    for t in TERAPIAS + sorted({v["_ter"] for v in vis} - set(TERAPIAS)):
        vt = [v for v in vis if v["_ter"] == t]
        if not vt:
            continue
        ultima = vt[0]["_data"]
        dias = (fim - ultima).days
        atend_ultima = base.por_id.get(vt[0]["atendimento_origem_id"], {})
        ativos_ids = {a["origem_id"] for a in c.ativos.get(p, [])}
        if p in c.pend.get(t, ()):
            sit = f"Pendente há {dias} dias"
        elif t in ters90 and ultima >= corte:
            sit = "Em dia"
        elif t in ters90:
            sit = f"Sem visita há {dias} dias (atendimento sem terapia indicada)"
        elif atend_ultima.get("origem_id") not in ativos_ids and atend_ultima.get("_alta"):
            # a alta encerrou o ciclo: não é atraso
            sit = f"Encerrada com a alta de {br(atend_ultima['_alta'])}"
        else:
            sit = f"Sem visita há {dias} dias (fora dos 90 dias)"
        terapias.append([NOMES_TERAPIA.get(t, t), sit, br(ultima), sum(1 for v in vt if v["_data"] >= fim - timedelta(days=JANELA_TERAPIA - 1)),
                         sum(1 for v in vt if ini <= v["_data"] <= fim), "; ".join(sorted({v["profissional"] or "—" for v in vt[:20]}))])
    if p in c.pend.get(SEM_ATENDIMENTO, ()):
        terapias.insert(0, ["Indicado com terapias", f"Sem nenhuma visita de terapia em {JANELA_TERAPIA} dias", "—", 0, 0, "—"])

    profs: dict[str, dict] = {}
    for v in vis:
        g = profs.setdefault(op.chave_profissional(v) or "?", {"nome": v["profissional"] or "Sem nome", "ter": Counter(), "n": 0,
                                                                 "ini": v["_data"], "fim": v["_data"]})
        g["ter"][v["_ter"]] += 1
        g["n"] += 1
        g["ini"], g["fim"] = min(g["ini"], v["_data"]), max(g["fim"], v["_data"])

    rotulos_orc = dict(SITUACOES_ORCAMENTO)
    atendimentos = [[a["origem_id"], a["servico"] or "—", a["operadora"] or "—", "Ativo" if a in c.ativos.get(p, []) else (a["status_origem"] or "—").title(),
                     br(a["_adm"]), br(a["_alta"]) or "—", a["condicao_alta"] or "—", a["possui_terapias"] or "—", br(a["_orc_fim"]) or "—",
                     rotulos_orc[situacao_orcamento(a, fim)] if a in c.ativos.get(p, []) else "—"] for a in sorted(atend, key=lambda a: a not in c.ativos.get(p, []))]
    orc_ativos = [situacao_orcamento(a, fim) for a in c.ativos.get(p, [])]
    pior_orc = next((rotulos_orc[k] for k, _ in SITUACOES_ORCAMENTO if k in orc_ativos), "—")
    rel = op.linhas_relatorios([x for x in base.relatorios_pendentes() if x["atendimento"] in ids])
    pendencias = [NOMES_TERAPIA.get(t, t) for t, ps in c.pend.items() if p in ps and t != SEM_ATENDIMENTO]
    nv = nivel(len(ters90)) if ters90 else "Sem terapia nos últimos 90 dias"
    zonas = sorted({_zona(base, a) for a in atend if a.get("zona")})
    dados = [
        ["Situação", situacao], ["Idade", f"{r['idade']} anos" if r["idade"] else "—"], ["Diagnóstico", r["diagnostico"] or "—"],
        ["Complexidade (pelas terapias, 90 dias)", nv], ["Complexidade informada pela URL", r["complexidade"] or "—"],
        ["Bairro", r["bairro"] or "—"], ["Cidade", r["cidade"] or "—"], ["Zona de atendimento", ", ".join(zonas) or "—"],
        ["Operadora(s)", " · ".join(sorted({a["operadora"] or "—" for a in atend}))],
        ["Serviço(s) ativo(s)", " · ".join(sorted({a["servico"] or "—" for a in c.ativos.get(p, [])})) or "—"],
        ["Primeira admissão", br(min((a["_adm"] for a in atend if a["_adm"]), default=None)) or "—"],
        ["Monitoramento com terapias", "Sim" if any(eh_monitoramento(a) and tem_terapias(a) for a in c.ativos.get(p, [])) else "Não"],
        ["Orçamento", pior_orc],
    ]
    return {
        "tipo": "paciente", "titulo": r["nome_paciente"], "trilha": "Paciente", "periodo": {"ini": ini.isoformat(), "fim": fim.isoformat()},
        "chips": [{"texto": situacao, "tom": {"Ativo": "ok", "Óbito": "crit"}.get(situacao, "")}]
                 + ([{"texto": f"Complexidade {nv}", "tom": "acc"}] if ters90 else [])
                 + [{"texto": f"Zona {z}", "tom": "acc"} for z in zonas[:2]]
                 + ([{"texto": "Terapia pendente", "tom": "warn"}] if pendencias or p in c.pend.get(SEM_ATENDIMENTO, ()) else []),
        "kpis": [
            {"rotulo": "Terapias", "valor": len(ters90), "sub": "nos últimos 90 dias", "tom": "acc", "aba": "terapias"},
            {"rotulo": "Pendências", "valor": len(pendencias) + (1 if p in c.pend.get(SEM_ATENDIMENTO, ()) else 0),
             "sub": ", ".join(pendencias) or "nenhuma", "tom": "warn", "aba": "terapias"},
            {"rotulo": "Visitas", "valor": sum(1 for v in vis if ini <= v["_data"] <= fim), "sub": f"no período · {len(vis)} no total", "tom": "acc", "aba": "visitas"},
            {"rotulo": "Última visita", "valor": br(vis[0]["_data"]) if vis else "—", "sub": vis[0]["_ter"] if vis else "", "tom": "neutro", "aba": "visitas"},
            {"rotulo": "Atendimentos", "valor": len(atend), "sub": f"{len(c.ativos.get(p, []))} ativo(s) · orçamento: {pior_orc.lower()}",
             "tom": "crit" if pior_orc == rotulos_orc["vencido"] else "neutro", "aba": "atendimentos"},
            {"rotulo": "Relatórios pendentes", "valor": len(rel["linhas"]), "tom": "warn", "aba": "relatorios"},
        ],
        "abas": [
            {"id": "dados", "nome": "Dados", "tipo": "dados", "desc": "Como o paciente está cadastrado no sistema da Saúde Residence.", "pares": dados},
            {"id": "terapias", "nome": "Terapias", "tipo": "tabela",
             "desc": f"Cada terapia: em dia, ou pendente quando está há mais de {JANELA_ATRASO} dias sem visita.",
             "colunas": ["Terapia", "Situação", "Última visita", f"Visitas ({JANELA_TERAPIA} d)", "Visitas no período", "Profissionais"],
             "linhas": terapias, "numericas": [3, 4]},
            {"id": "profissionais", "nome": "Profissionais", "tipo": "tabela", "desc": "Quem atende ou já atendeu o paciente. Clique para abrir o resumo do profissional.",
             "colunas": ["Profissional", "Terapia", "Visitas", "Primeira", "Última"],
             "linhas": [[g["nome"], g["ter"].most_common(1)[0][0], g["n"], br(g["ini"]), br(g["fim"]), k]
                        for k, g in sorted(profs.items(), key=lambda kv: kv[1]["fim"], reverse=True)],
             "numericas": [2], "abrir": {"tipo": "profissional", "col": 5}},
            {"id": "atendimentos", "nome": "Atendimentos", "tipo": "tabela",
             "desc": "Cada serviço contratado é um atendimento no sistema do cliente, com seu próprio orçamento.",
             "colunas": ["Atendimento", "Serviço", "Operadora", "Situação", "Admissão", "Alta", "Condição de alta", "Possui terapias", "Orçamento até", "Orçamento"],
             "linhas": atendimentos},
            {"id": "visitas", "nome": "Histórico de visitas", "tipo": "tabela", "desc": "Todas as visitas registradas, da mais recente para a mais antiga. Clique para abrir o profissional.",
             "colunas": ["Data", "Profissional", "Terapia", "Atendimento"],
             "linhas": [[br(v["_data"]), v["profissional"] or "—", v["_ter"], v["atendimento_origem_id"], op.chave_profissional(v) or ""] for v in vis],
             "abrir": {"tipo": "profissional", "col": 4}},
            {"id": "relatorios", "nome": "Relatórios pendentes", "tipo": "tabela", "desc": "Relatórios deste paciente ainda não entregues.",
             "colunas": rel["colunas"], "linhas": rel["linhas"]},
            {"id": "mensal", "nome": "Mês a mês", "tipo": "barras", "desc": f"Visitas por mês nos últimos {MESES_SERIE} meses.",
             "itens": _serie_mensal([v["_data"] for v in vis], fim), "ordem": True},
        ],
    }


# ---------------------------------------------------------------- busca rápida
def buscar(texto: str, limite: int = 8) -> dict:
    """Pacientes e profissionais cujo nome contém o texto (sem diferenciar acentos e maiúsculas)."""
    alvo = _norm(texto)
    if len(alvo) < 2:
        return {"pacientes": [], "profissionais": []}
    base = carregar()
    hoje = date.today()
    pacientes: dict[str, dict] = {}
    for a in base.atend:
        if alvo in a["_pac"]:
            g = pacientes.setdefault(a["_pac"], {"nome": a["nome_paciente"], "bairro": a["bairro"], "ativo": False})
            g["ativo"] = g["ativo"] or ativo_em(a, hoje)
    profs: dict[str, dict] = {}
    for v in base.visitas:
        if v["profissional"] and alvo in _norm(v["profissional"]):
            g = profs.setdefault(op.chave_profissional(v), {"nome": v["profissional"], "ter": Counter(), "ultima": v["_data"]})
            g["ter"][v["_ter"]] += 1
            g["ultima"] = max(g["ultima"], v["_data"])
    pac = sorted(pacientes.values(), key=lambda g: (not g["ativo"], g["nome"].casefold()))[:limite]
    pro = sorted(profs.items(), key=lambda kv: kv[1]["ultima"], reverse=True)[:limite]
    return {
        "pacientes": [{"nome": g["nome"], "detalhe": f"{'Ativo' if g['ativo'] else 'Sem atendimento ativo'} · {g['bairro'] or 'bairro não informado'}"} for g in pac],
        "profissionais": [{"chave": k, "nome": g["nome"], "detalhe": f"{g['ter'].most_common(1)[0][0]} · última visita {br(g['ultima'])}"} for k, g in pro],
    }
