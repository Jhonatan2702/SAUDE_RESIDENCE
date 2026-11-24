"""Painel BI (gestor/admin): indicadores calculados sobre o espelho da URL.

Contagens de "pacientes" são de pessoas distintas (nome normalizado); contagens de "atendimentos" são
episódios da URL. Toda lista do painel pode ser aberta em `detalhe()` para ver quem compõe o número.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from . import operacional as op
from .fonte import (FAIXAS_IDADE, JANELA_ATRASO, JANELA_COBERTURA, JANELA_TERAPIA, NIVEIS, NOMES_TERAPIA, TERAPIAS, Base, br, carregar, eh_monitoramento,
                    eh_obito, em_fortaleza, faixa_idade, nivel, periodo, sem_acento, servico_acompanhado, tem_terapias, chave_paciente)

MIN_MESES, MAX_MESES = 8, 24
LIMITE_DETALHE = 5000
SEM_ATENDIMENTO = "SEM"   # pendência: indicado com terapias e nenhuma visita de terapia na janela
COLS_PACIENTE = ["Paciente", "Atendimentos", "Operadora", "Serviço", "Admissão", f"Terapias ({JANELA_TERAPIA} d)",
                 "Última visita", "Bairro", "Cidade", "Idade"]
COLS_ATEND = ["Paciente", "Atendimento", "Operadora", "Serviço", "Admissão", "Alta", "Condição de alta", "Dias", "Bairro", "Idade"]
COLS_VISITA = ["Data", "Paciente", "Atendimento", "Profissional", "Terapia", "Operadora", "Bairro"]


def _top(c: Counter, n: int | None = None) -> list[dict]:
    return [{"rotulo": k, "valor": v} for k, v in c.most_common(n)]


def _meses(ini: date, fim: date) -> list[str]:
    total = min(max((fim.year - ini.year) * 12 + fim.month - ini.month + 1, MIN_MESES), MAX_MESES)
    ano, mes, saida = fim.year, fim.month, []
    for _ in range(total):
        saida.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano, mes - 1) if mes > 1 else (ano - 1, 12)
    return saida[::-1]


def _fim_mes(m: str) -> date:
    a, mm = int(m[:4]), int(m[5:])
    return (date(a + (mm == 12), mm % 12 + 1, 1)) - timedelta(days=1)


def _escopo(nome: str, fim: date) -> tuple[date, date]:
    if nome == "dia":
        return fim, fim
    return (fim.replace(day=1) if nome == "mes" else fim.replace(month=1, day=1)), fim


def _rotulo_escopo(nome: str, fim: date) -> str:
    return {"dia": br(fim), "mes": f"{fim.month:02d}/{fim.year}", "ano": str(fim.year)}[nome]


def _atendidos(base: Base, ini: date, fim: date) -> set[str]:
    """Pacientes em atendimento em algum momento do intervalo."""
    return {a["_pac"] for a in base.atend if a["_adm"] and a["_adm"] <= fim and (not a["_alta"] or a["_alta"] >= ini)}


def _obitos(base: Base, ini: date, fim: date) -> list[dict]:
    return [a for a in base.atend if eh_obito(a) and a["_alta"] and ini <= a["_alta"] <= fim]


def _mortalidade(base: Base, ini: date, fim: date) -> dict:
    obitos = {a["_pac"] for a in _obitos(base, ini, fim)}
    atendidos = _atendidos(base, ini, fim)
    return {"obitos": len(obitos), "atendidos": len(atendidos),
            "taxa": round(len(obitos) * 100 / len(atendidos), 2) if atendidos else 0}


class _Contexto:
    """Cálculos derivados de um período, compartilhados por gerar() e detalhe()."""

    def __init__(self, base: Base, ini: date, fim: date):
        self.base, self.ini, self.fim = base, ini, fim
        self.ativos_at = base.ativos(fim)
        self.ativos: dict[str, list[dict]] = {}
        for a in self.ativos_at:
            self.ativos.setdefault(a["_pac"], []).append(a)
        # atendimento de referência de cada paciente ativo: o mais recente que tenha bairro (a URL nem sempre envia)
        self.rep = {p: max(lst, key=lambda a: (bool(a["bairro"]), a["data_admissao"] or "")) for p, lst in self.ativos.items()}
        # terapias dos últimos 90 dias contadas só nos atendimentos ATIVOS: a alta encerra o ciclo de visitas
        self.ter_janela = base.terapias_por_paciente(fim, so_atendimentos={a["origem_id"] for a in self.ativos_at})
        self.visitas_periodo = base.visitas_entre(ini, fim)
        self.visitados = {base.por_id[v["atendimento_origem_id"]]["_pac"] for v in self.visitas_periodo
                          if v["atendimento_origem_id"] in base.por_id}
        corte = fim - timedelta(days=JANELA_ATRASO - 1)
        self.pend: dict[str, set[str]] = {}
        for p, ters in self.ter_janela.items():
            if any(tem_terapias(a) for a in self.ativos[p]):
                for t, ultima in ters.items():
                    if ultima < corte:
                        self.pend.setdefault(t, set()).add(p)
        self.pend[SEM_ATENDIMENTO] = {p for p, lst in self.ativos.items()
                                      if any(tem_terapias(a) for a in lst) and not self.ter_janela.get(p)}
        self.monit = {p for p, lst in self.ativos.items() if any(eh_monitoramento(a) for a in lst)}
        self.monit_ter = {p for p, lst in self.ativos.items() if any(eh_monitoramento(a) and tem_terapias(a) for a in lst)}
        # atendimento "com terapias": indicado pela URL (possui terapias = SIM) ou com alguma visita de terapia
        self.ids_terapia = {v["atendimento_origem_id"] for v in base.visitas if v["_ter"] in TERAPIAS}
        self.com_ter = {p for p, lst in self.ativos.items() if any(self.com_terapias(a) for a in lst)}
        # sem visita: só pacientes de serviços acompanhados (Monitoramento, ID, Plantão, Serv. Prof. Não Méd.)
        self.sem_visita = {p for p, lst in self.ativos.items() if any(servico_acompanhado(a) for a in lst)} - self.visitados

    def com_terapias(self, a: dict) -> bool:
        return tem_terapias(a) or a["origem_id"] in self.ids_terapia

    def admissoes(self, ini: date, fim: date, so_terapias: bool = False) -> list[dict]:
        return [a for a in self.base.atend if a["_adm"] and ini <= a["_adm"] <= fim and (not so_terapias or self.com_terapias(a))]

    def altas(self, ini: date, fim: date, so_terapias: bool = False) -> list[dict]:
        return [a for a in self.base.atend if a["_alta"] and ini <= a["_alta"] <= fim and not eh_obito(a)
                and (not so_terapias or self.com_terapias(a))]

    # ---- linhas para o detalhamento
    def ultima_visita(self) -> dict[str, date]:
        ult: dict[str, date] = {}
        for v in self.base.visitas:
            a = self.base.por_id.get(v["atendimento_origem_id"])
            if a and v["_data"] <= self.fim and (a["_pac"] not in ult or v["_data"] > ult[a["_pac"]]):
                ult[a["_pac"]] = v["_data"]
        return ult

    def linhas_pacientes(self, pacientes) -> dict:
        ult = self.ultima_visita()
        linhas = []
        for p in pacientes:
            lst = self.ativos.get(p) or [a for a in self.base.atend if a["_pac"] == p]
            r = self.rep.get(p) or max(lst, key=lambda a: a["data_admissao"] or "")
            ters = self.ter_janela.get(p, {})
            linhas.append([r["nome_paciente"], ", ".join(a["origem_id"] for a in lst),
                           " · ".join(sorted({a["operadora"] or "—" for a in lst})),
                           " · ".join(sorted({a["servico"] or "—" for a in lst})),
                           br(min((a["_adm"] for a in lst if a["_adm"]), default=None)),
                           " · ".join(t for t in TERAPIAS + sorted(set(ters) - set(TERAPIAS)) if t in ters) or "—",
                           br(ult.get(p)), r["bairro"] or "—", r["cidade"] or "—", r["idade"] or "—"])
        linhas.sort(key=lambda l: l[0].casefold())
        return {"colunas": COLS_PACIENTE, "linhas": linhas, "drill": {"tipo": "paciente", "col": 0}}

    def linhas_atendimentos(self, lista) -> dict:
        linhas = []
        for a in sorted(lista, key=lambda a: a["data_alta"] or a["data_admissao"] or "", reverse=True):
            dias = ((a["_alta"] or self.fim) - a["_adm"]).days if a["_adm"] else ""
            linhas.append([a["nome_paciente"], a["origem_id"], a["operadora"] or "—", a["servico"] or "—", br(a["_adm"]),
                           br(a["_alta"]), a["condicao_alta"] or "—", dias, a["bairro"] or "—", a["idade"] or "—"])
        return {"colunas": COLS_ATEND, "linhas": linhas, "drill": {"tipo": "paciente", "col": 0}}

    def linhas_visitas(self, lista) -> dict:
        linhas = []
        for v in sorted(lista, key=lambda v: v["_data"], reverse=True):
            a = self.base.por_id.get(v["atendimento_origem_id"], {})
            linhas.append([br(v["_data"]), a.get("nome_paciente", "—"), v["atendimento_origem_id"], v["profissional"] or "—",
                           v["_ter"], a.get("operadora") or "—", a.get("bairro") or "—"])
        return {"colunas": COLS_VISITA, "linhas": linhas, "drill": {"tipo": "paciente", "col": 1}}


METRICAS_MAPA = ["ativos", "em_terapia", "pendentes", "visitas", "profissionais", "cobertura", "altas", "relatorios"]
TODAS = "*"


def _mapa_conjuntos(base: Base, c: "_Contexto", por: str = "bairro") -> tuple[dict, dict]:
    """{bairro ou zona: {métrica: {terapia|'*': conjunto ou lista}}}.

    por="bairro": só Fortaleza; pacientes pelo bairro do atendimento de referência, visitas e relatórios pelo
    bairro do próprio atendimento. por="zona": zona de atendimento enviada pela URL (qualquer cidade).
    """
    mapa: dict[str, dict] = {}
    fora = {"sem_bairro": 0, "outra_cidade": 0, "sem_zona": 0}

    def chave_atend(a):
        if por == "zona":
            return a["zona"]
        return a["bairro"] if a["bairro"] and em_fortaleza(a) else None

    def caixa(chave, metrica, sigla, tipo=set):
        m = mapa.setdefault(chave, {k: {} for k in METRICAS_MAPA})[metrica]
        return m.setdefault(sigla, tipo())

    for p, r in c.rep.items():
        if por == "zona":
            com_zona = [a for a in c.ativos[p] if a["zona"]]
            k = max(com_zona, key=lambda a: a["data_admissao"] or "")["zona"] if com_zona else None
            if not k:
                fora["sem_zona"] += 1
                continue
        else:
            if not em_fortaleza(r):
                fora["outra_cidade"] += 1
                continue
            if not r["bairro"]:
                fora["sem_bairro"] += 1
                continue
            k = r["bairro"]
        caixa(k, "ativos", TODAS).add(p)
        for t in c.ter_janela.get(p, {}):
            caixa(k, "em_terapia", t).add(p)
            caixa(k, "em_terapia", TODAS).add(p)
        for t, pacientes in c.pend.items():
            if p in pacientes:
                caixa(k, "pendentes", t).add(p)
                caixa(k, "pendentes", TODAS).add(p)
    for v in c.visitas_periodo:
        a = base.por_id.get(v["atendimento_origem_id"])
        if not a or not (k := chave_atend(a)):
            continue
        for sig in (v["_ter"], TODAS):
            caixa(k, "visitas", sig, list).append(v)
            if (prof := op.chave_profissional(v)):
                caixa(k, "profissionais", sig).add(prof)
    for rel in base.relatorios_pendentes():
        a = base.por_id.get(rel["atendimento"])
        if a and (k := chave_atend(a)):
            for sig in (rel["terapia"], TODAS):
                caixa(k, "relatorios", sig, list).append(rel)
    # altas do período (sem óbitos), pelo bairro/zona do atendimento que recebeu a alta
    for a in base.atend:
        if a["_alta"] and c.ini <= a["_alta"] <= c.fim and not eh_obito(a) and (k := chave_atend(a)):
            caixa(k, "altas", TODAS, list).append(a)
    # cobertura: profissionais com visita no bairro/zona nos últimos JANELA_COBERTURA dias, mesmo sem visita no período
    inicio_cob = c.fim - timedelta(days=JANELA_COBERTURA - 1)
    for v in base.visitas:
        if not inicio_cob <= v["_data"] <= c.fim:
            continue
        a = base.por_id.get(v["atendimento_origem_id"])
        if a and (k := chave_atend(a)) and (prof := op.chave_profissional(v)):
            for sig in (v["_ter"], TODAS):
                caixa(k, "cobertura", sig).add(prof)
    return mapa, fora


COLS_COBERTURA = ["Profissional", "Terapia", "Situação", f"Pacientes ({JANELA_COBERTURA} d)", "Visitas no período",
                  f"Visitas ({JANELA_COBERTURA} d)", "Última visita"]


def cobertura(base: Base, c: "_Contexto", lugar: str, por: str = "bairro", sig: str = TODAS) -> list[list]:
    """Profissionais que cobrem o bairro/zona: visitaram alguém lá nos últimos JANELA_COBERTURA dias.

    Situação "Atendendo no período" quando houve visita dentro do período; senão "Cobre o bairro" (atendeu antes,
    mas não no período). A última coluna (oculta) é a chave do profissional, para abrir o resumo dele.
    """
    inicio_cob = c.fim - timedelta(days=JANELA_COBERTURA - 1)
    grupos: dict[str, dict] = {}
    for v in base.visitas:
        if not inicio_cob <= v["_data"] <= c.fim or (sig != TODAS and v["_ter"] != sig):
            continue
        a = base.por_id.get(v["atendimento_origem_id"])
        if not a:
            continue
        aqui = a["zona"] == lugar if por == "zona" else (a["bairro"] == lugar and em_fortaleza(a))
        chave = op.chave_profissional(v)
        if not aqui or not chave:
            continue
        g = grupos.setdefault(chave, {"nome": v["profissional"] or "Sem nome", "ter": Counter(), "pac": set(), "vis": 0, "vis_per": 0,
                                      "ultima": v["_data"]})
        g["ter"][v["_ter"]] += 1
        g["pac"].add(a["_pac"])
        g["vis"] += 1
        g["vis_per"] += c.ini <= v["_data"]
        g["ultima"] = max(g["ultima"], v["_data"])
    linhas = [[g["nome"], g["ter"].most_common(1)[0][0], "Atendendo no período" if g["vis_per"] else "Cobre o bairro" if por == "bairro" else "Cobre a zona",
               len(g["pac"]), g["vis_per"], g["vis"], br(g["ultima"]), k] for k, g in grupos.items()]
    return sorted(linhas, key=lambda l: (l[4] == 0, -l[4], -l[5], l[0]))


# ---------------------------------------------------------------- orçamentos dos atendimentos ativos
SITUACOES_ORCAMENTO = [("vencido", "Vencido"), ("vence_7", "Vence em até 7 dias"), ("vence_30", "Vence em 8 a 30 dias"),
                       ("em_dia", "Vigente por mais de 30 dias"), ("sem", "Sem orçamento informado")]
COLS_ORCAMENTO = ["Paciente", "Atendimento", "Operadora", "Serviço", "Zona", "Início do orçamento", "Fim do orçamento", "Dias para vencer"]


def situacao_orcamento(a: dict, dia: date) -> str:
    if not a["_orc_fim"]:
        return "sem"
    dias = (a["_orc_fim"] - dia).days
    return "vencido" if dias < 0 else "vence_7" if dias <= 7 else "vence_30" if dias <= 30 else "em_dia"


def linhas_orcamento(base: Base, lista: list[dict], dia: date) -> dict:
    linhas = []
    for a in sorted(lista, key=lambda a: (a["_orc_fim"] or date.max, a["nome_paciente"])):
        dias = (a["_orc_fim"] - dia).days if a["_orc_fim"] else ""
        zona = base.zonas.get(a["zona"], {}).get("nome", "—") if a["zona"] else "—"
        linhas.append([a["nome_paciente"], a["origem_id"], a["operadora"] or "—", a["servico"] or "—", zona,
                       br(a["_orc_ini"]), br(a["_orc_fim"]), dias])
    return {"colunas": COLS_ORCAMENTO, "linhas": linhas, "drill": {"tipo": "paciente", "col": 0}}


def gerar(ini: date | None = None, fim: date | None = None) -> dict:
    ini, fim = periodo(ini, fim)
    base = carregar()
    c = _Contexto(base, ini, fim)
    mort = _mortalidade(base, ini, fim)

    # ---- terapias (pedido: nº de pacientes por terapia e pacientes por terapia pendente)
    em_terapia = Counter(t for ters in c.ter_janela.values() for t in ters)
    visitas_ter = Counter(v["_ter"] for v in c.visitas_periodo)
    pac_ter_periodo: dict[str, set] = {}
    for v in c.visitas_periodo:
        a = base.por_id.get(v["atendimento_origem_id"])
        if a:
            pac_ter_periodo.setdefault(v["_ter"], set()).add(a["_pac"])
    siglas = TERAPIAS + sorted((set(em_terapia) | set(visitas_ter)) - set(TERAPIAS))
    terapias = [{"sigla": t, "nome": NOMES_TERAPIA.get(t, t), "pacientes": em_terapia.get(t, 0),
                 "pacientes_periodo": len(pac_ter_periodo.get(t, ())), "visitas_periodo": visitas_ter.get(t, 0),
                 "pendentes": len(c.pend.get(t, ()))} for t in siglas]
    pendentes_total = set().union(*c.pend.values())

    # ---- complexidade pelo nº de terapias diferentes
    niveis = Counter(nivel(len(t)) for t in c.ter_janela.values())
    total_ter = len(c.ter_janela)
    complexidade = [{"rotulo": r, "faixa": f"{mi} ou mais terapias" if ma >= 99 else f"{mi} terapias" if mi == ma else f"{mi} a {ma} terapias",
                     "valor": niveis.get(r, 0), "pct": round(niveis.get(r, 0) * 100 / total_ter, 1) if total_ter else 0}
                    for r, mi, ma in NIVEIS]
    cx_terapia = {r: {t: 0 for t in siglas} for r, _, _ in NIVEIS}
    for ters in c.ter_janela.values():
        for t in ters:
            cx_terapia[nivel(len(ters))][t] += 1

    # ---- movimentação e mortalidade
    meses = _meses(ini, fim)
    adm_mes = Counter(a["_adm"].strftime("%Y-%m") for a in base.atend if a["_adm"])
    alta_mes = Counter(a["_alta"].strftime("%Y-%m") for a in base.atend if a["_alta"] and not eh_obito(a))
    obito_mes = Counter(a["_alta"].strftime("%Y-%m") for a in base.atend if a["_alta"] and eh_obito(a))
    visitas_mes = Counter(v["_data"].strftime("%Y-%m") for v in base.visitas)
    mort_mes = [_mortalidade(base, date(int(m[:4]), int(m[5:]), 1), min(_fim_mes(m), fim))["taxa"] for m in meses]
    dma, motivos = {}, {}
    for nome in ("dia", "mes", "ano"):
        e_ini, e_fim = _escopo(nome, fim)
        altas_e = [a for a in base.atend if a["_alta"] and e_ini <= a["_alta"] <= e_fim]
        m = _mortalidade(base, e_ini, e_fim)
        dma[nome] = {"rotulo": _rotulo_escopo(nome, fim), "altas": sum(not eh_obito(a) for a in altas_e),
                     "admissoes": sum(1 for a in base.atend if a["_adm"] and e_ini <= a["_adm"] <= e_fim),
                     "obitos": m["obitos"], "atendidos": m["atendidos"], "mortalidade": m["taxa"]}
        motivos[nome] = _top(Counter(a["condicao_alta"] or "Não informada" for a in altas_e), 10)
    obitos_lista = c.linhas_atendimentos(_obitos(base, ini, fim))

    # ---- perfil dos pacientes ativos
    reps = list(c.rep.values())
    idades = [int(float(a["idade"])) for a in reps if faixa_idade(a["idade"])]
    faixas = Counter(faixa_idade(a["idade"]) for a in reps)
    por_operadora = Counter(o for lst in c.ativos.values() for o in {a["operadora"] or "Não informada" for a in lst})
    por_servico = Counter(s for lst in c.ativos.values() for s in {a["servico"] or "Não informado" for a in lst})
    em_mapa = [a for a in reps if em_fortaleza(a)]
    bairros = Counter(a["bairro"] for a in em_mapa if a["bairro"])

    contar = lambda conj: {k: {m: {s: len(x) for s, x in sigs.items()} for m, sigs in met.items()} for k, met in conj.items()}  # noqa: E731
    conjuntos, fora = _mapa_conjuntos(base, c)
    mapa = contar(conjuntos)
    conj_zonas, fora_zona = _mapa_conjuntos(base, c, por="zona")
    zonas = contar(conj_zonas)
    relatorios = base.relatorios_pendentes()
    rel_recentes = [r for r in relatorios if op.relatorio_recente(r)]
    profs = op.resumo_profissionais(base, ini, fim)
    return {
        "periodo": {"ini": ini.isoformat(), "fim": fim.isoformat()},
        "atualizado_em": base.sincronizado,
        "janelas": {"terapia": JANELA_TERAPIA, "atraso": JANELA_ATRASO},
        "kpis": {
            "pacientes_ativos": len(c.ativos), "atendimentos_ativos": len(c.ativos_at), "com_terapias": len(c.com_ter),
            "admissoes": len(c.admissoes(ini, fim)), "admissoes_terapias": len(c.admissoes(ini, fim, True)),
            "altas": len(c.altas(ini, fim)), "altas_terapias": len(c.altas(ini, fim, True)),
            "visitas": len(c.visitas_periodo), "pacientes_visitados": len(c.visitados & set(c.ativos)),
            "sem_visita": len(c.sem_visita),
            "monit_terapias": len(c.monit_ter), "monitoramento": len(c.monit),
            "mortalidade": mort["taxa"], "obitos": mort["obitos"], "atendidos": mort["atendidos"],
            "em_terapia": total_ter, "pendentes": len(pendentes_total), "sem_atendimento_terapia": len(c.pend[SEM_ATENDIMENTO]),
            "relatorios_pendentes": len(relatorios), "relatorios_recentes": len(rel_recentes), "profissionais": len(profs),
            "idade_media": round(sum(idades) / len(idades), 1) if idades else 0,
        },
        "terapias": terapias,
        "complexidade": complexidade,
        "complexidade_terapia": cx_terapia,
        "complexidade_informada": _top(Counter(a["complexidade"] or "Não informada" for a in reps), 8),
        "meses": meses,
        "admissoes_mes": [adm_mes[m] for m in meses], "altas_mes": [alta_mes[m] for m in meses],
        "obitos_mes": [obito_mes[m] for m in meses], "mortalidade_mes": mort_mes,
        "visitas_mes": [visitas_mes[m] for m in meses],
        "dma": dma, "motivos": motivos, "obitos_lista": obitos_lista,
        "operadoras": _top(por_operadora, 10), "servicos": _top(por_servico, 10),
        "cidades": _top(Counter(a["cidade"] or "Não informada" for a in reps), 10),
        "faixas_etarias": [{"rotulo": r, "valor": faixas.get(r, 0)} for r, _, _ in FAIXAS_IDADE]
                          + [{"rotulo": "Não informada", "valor": faixas.get(None, 0)}],
        "diagnosticos": _top(Counter(a["diagnostico"] or "Não informado" for a in reps), 10),
        "bairros": _top(bairros), "sem_localizacao": len(em_mapa) - sum(bairros.values()),
        "mapa": mapa, "mapa_fora": fora,
        "zonas": zonas, "zonas_sem": fora_zona["sem_zona"],
        "zonas_info": {z: {"nome": base.zonas[z]["nome"], "bairros": base.zonas[z]["bairros"]} for z in base.zonas},
        "profissionais": profs[:15],
        "relatorios_terapia": _top(Counter(r["terapia"] for r in relatorios)),
    }


def detalhe(tipo: str, valor: str | None, ini: date | None = None, fim: date | None = None) -> dict:
    """Registros (com nome do paciente) que compõem cada número do painel."""
    ini, fim = periodo(ini, fim)
    valor = (valor or "").strip()
    base = carregar()
    c = _Contexto(base, ini, fim)
    rot = f"{br(ini)} a {br(fim)}"
    janela = f"últimos {JANELA_TERAPIA} dias até {br(fim)}"
    pacs = lambda cond: [p for p in c.ativos if cond(p)]  # noqa: E731

    if tipo == "ativos":
        titulo, r = f"Pacientes ativos em {br(fim)}", c.linhas_pacientes(c.ativos)
    elif tipo == "com_terapias":
        titulo, r = f"Pacientes ativos com terapias em {br(fim)}", c.linhas_pacientes(c.com_ter)
    elif tipo == "admissoes":
        so_ter = valor == "terapias"
        titulo = f"Admissões{' com terapias' if so_ter else ''} ({rot})"
        r = c.linhas_atendimentos(c.admissoes(ini, fim, so_ter))
    elif tipo == "altas":
        so_ter = valor == "terapias"
        titulo = f"Altas{' com terapias' if so_ter else ''}, exceto óbitos ({rot})"
        r = c.linhas_atendimentos(c.altas(ini, fim, so_ter))
    elif tipo == "obitos":
        titulo, r = f"Pacientes que foram a óbito ({rot})", c.linhas_atendimentos(_obitos(base, ini, fim))
    elif tipo == "visitas":
        titulo, r = f"Visitas ({rot})", c.linhas_visitas(c.visitas_periodo)
    elif tipo == "sem_visita":
        titulo = f"Ativos sem nenhuma visita — Monitoramento, ID, Plantão e Serv. Prof. Não Méd. ({rot})"
        r = c.linhas_pacientes(c.sem_visita)
    elif tipo == "monit_terapias":
        titulo, r = f"Pacientes ativos de monitoramento com terapias em {br(fim)}", c.linhas_pacientes(c.monit_ter)
    elif tipo == "monitoramento":
        titulo, r = f"Pacientes ativos em monitoramento em {br(fim)}", c.linhas_pacientes(c.monit)
    elif tipo == "em_terapia":
        lista = pacs(lambda p: p in c.ter_janela and (not valor or valor in c.ter_janela[p]))
        titulo = f"Pacientes em {NOMES_TERAPIA.get(valor, valor) if valor else 'terapia'} ({janela})"
        r = c.linhas_pacientes(lista)
    elif tipo == "pendentes":
        if valor == SEM_ATENDIMENTO:
            titulo, lista = f"Indicados com terapias e sem nenhuma visita de terapia ({janela})", c.pend[SEM_ATENDIMENTO]
        elif valor:
            titulo = f"{NOMES_TERAPIA.get(valor, valor)}: em terapia, mas sem visita nos últimos {JANELA_ATRASO} dias"
            lista = c.pend.get(valor, set())
        else:
            titulo, lista = "Pacientes com alguma terapia pendente", set().union(*c.pend.values())
        r = c.linhas_pacientes(lista)
    elif tipo == "complexidade":
        titulo = f"Complexidade {valor} ({janela})"
        r = c.linhas_pacientes(pacs(lambda p: p in c.ter_janela and nivel(len(c.ter_janela[p])) == valor))
    elif tipo == "complexidade_terapia":
        nv, _, t = valor.partition("|")
        titulo = f"Complexidade {nv} em {NOMES_TERAPIA.get(t, t)} ({janela})"
        r = c.linhas_pacientes(pacs(lambda p: t in c.ter_janela.get(p, {}) and nivel(len(c.ter_janela[p])) == nv))
    elif tipo in ("operadora", "servico"):
        vazio = "Não informada" if tipo == "operadora" else "Não informado"
        titulo = f"Pacientes ativos — {'operadora' if tipo == 'operadora' else 'serviço'} {valor}"
        r = c.linhas_pacientes(pacs(lambda p: any((a[tipo] or vazio) == valor for a in c.ativos[p])))
    elif tipo in ("cidade", "bairro", "diagnostico", "complexidade_informada", "idade"):
        def campo(a):
            if tipo == "idade":
                return faixa_idade(a["idade"]) or "Não informada"
            if tipo == "bairro":
                return a["bairro"] or ""
            col = "complexidade" if tipo == "complexidade_informada" else tipo
            return a[col] or ("Não informado" if tipo == "diagnostico" else "Não informada")
        alvo = " ".join(sem_acento(valor).upper().split()) if tipo == "bairro" else valor
        titulo = f"Pacientes ativos — {tipo.replace('_', ' ')}: {valor}"
        r = c.linhas_pacientes(pacs(lambda p: campo(c.rep[p]) == alvo))
    elif tipo == "profissional":
        titulo = f"Visitas de {valor} ({rot})"
        r = c.linhas_visitas([v for v in c.visitas_periodo if (v["profissional"] or "") == valor])
    elif tipo == "terapia_visitas":
        titulo = f"Visitas de {NOMES_TERAPIA.get(valor, valor)} ({rot})"
        r = c.linhas_visitas([v for v in c.visitas_periodo if v["_ter"] == valor])
    elif tipo in ("dma_altas", "dma_admissoes", "dma_obitos"):
        e_ini, e_fim = _escopo(valor, fim)
        if tipo == "dma_admissoes":
            lista, nome = [a for a in base.atend if a["_adm"] and e_ini <= a["_adm"] <= e_fim], "Admissões"
        elif tipo == "dma_obitos":
            lista, nome = _obitos(base, e_ini, e_fim), "Óbitos"
        else:
            lista = [a for a in base.atend if a["_alta"] and e_ini <= a["_alta"] <= e_fim and not eh_obito(a)]
            nome = "Altas"
        titulo, r = f"{nome} — {_rotulo_escopo(valor, fim)}", c.linhas_atendimentos(lista)
    elif tipo == "motivo":
        escopo, _, motivo = valor.partition("|")
        e_ini, e_fim = _escopo(escopo or "mes", fim)
        lista = [a for a in base.atend if a["_alta"] and e_ini <= a["_alta"] <= e_fim and (a["condicao_alta"] or "Não informada") == motivo]
        titulo, r = f"Altas — {motivo} ({_rotulo_escopo(escopo or 'mes', fim)})", c.linhas_atendimentos(lista)
    elif tipo in ("mes_admissoes", "mes_altas", "mes_obitos", "mes_visitas"):
        rotulo_mes = f"{valor[5:]}/{valor[:4]}"
        if tipo == "mes_visitas":
            titulo, r = f"Visitas em {rotulo_mes}", c.linhas_visitas([v for v in base.visitas if v["_data"].strftime("%Y-%m") == valor])
        elif tipo == "mes_admissoes":
            titulo = f"Admissões em {rotulo_mes}"
            r = c.linhas_atendimentos([a for a in base.atend if a["_adm"] and a["_adm"].strftime("%Y-%m") == valor])
        else:
            obito = tipo == "mes_obitos"
            titulo = f"{'Óbitos' if obito else 'Altas'} em {rotulo_mes}"
            r = c.linhas_atendimentos([a for a in base.atend if a["_alta"] and a["_alta"].strftime("%Y-%m") == valor
                                       and eh_obito(a) == obito])
    elif tipo == "orcamento":
        rotulos = dict(SITUACOES_ORCAMENTO)
        if valor not in rotulos:
            raise ValueError("Situação de orçamento desconhecida.")
        titulo = f"Orçamentos — {rotulos[valor].lower()} (atendimentos ativos em {br(fim)})"
        r = linhas_orcamento(base, [a for a in c.ativos_at if situacao_orcamento(a, fim) == valor], fim)
    elif tipo in ("mapa", "zona"):  # valor = "métrica|terapia|bairro ou id da zona"
        metrica, sig, bairro = (valor.split("|") + ["", "", ""])[:3]
        if metrica not in METRICAS_MAPA:
            raise ValueError("Indicador do mapa desconhecido.")
        por = "zona" if tipo == "zona" else "bairro"
        if por == "bairro":
            bairro = " ".join(sem_acento(bairro).upper().split())
        sig = sig or TODAS
        conj = _mapa_conjuntos(base, c, por=por)[0]
        itens = conj.get(bairro, {}).get(metrica, {}).get(sig, ())
        ter = "" if sig == TODAS else f" · {NOMES_TERAPIA.get(sig, sig)}"
        nomes = {"ativos": "Pacientes ativos", "em_terapia": f"Pacientes em terapia ({janela})",
                 "pendentes": "Pacientes com terapia pendente", "visitas": f"Visitas ({rot})",
                 "profissionais": f"Profissionais que atenderam ({rot})", "relatorios": "Relatórios pendentes",
                 "cobertura": f"Profissionais que cobrem (últimos {JANELA_COBERTURA} dias)", "altas": f"Altas ({rot})"}
        lugar = f"zona {base.zonas.get(bairro, {}).get('nome', bairro)}" if por == "zona" else bairro
        titulo = f"{nomes[metrica]}{ter} — {lugar}"
        if metrica == "visitas":
            r = c.linhas_visitas(list(itens))
        elif metrica == "altas":
            r = c.linhas_atendimentos(list(itens))
        elif metrica == "cobertura":
            r = {"colunas": COLS_COBERTURA, "linhas": cobertura(base, c, bairro, por, sig), "drill": None}
        elif metrica == "relatorios":
            r = op.linhas_relatorios(list(itens))
        elif metrica == "profissionais":
            vis = list(conj.get(bairro, {}).get("visitas", {}).get(sig, []))
            grupos: dict[str, dict] = {}
            for v in vis:
                g = grupos.setdefault(op.chave_profissional(v) or "?", {"nome": v["profissional"] or "Sem nome",
                                                                          "ter": Counter(), "pac": set(), "vis": 0})
                g["ter"][v["_ter"]] += 1
                g["pac"].add(base.por_id[v["atendimento_origem_id"]]["_pac"])
                g["vis"] += 1
            linhas = sorted(([g["nome"], g["ter"].most_common(1)[0][0], len(g["pac"]), g["vis"]] for g in grupos.values()),
                            key=lambda l: (-l[3], l[0]))
            sufixo = "na zona" if por == "zona" else "no bairro"
            r = {"colunas": ["Profissional", "Terapia", f"Pacientes {sufixo}", f"Visitas {sufixo}"], "linhas": linhas, "drill": None}
        else:
            r = c.linhas_pacientes(itens)
    elif tipo == "relatorios":
        rel = [x for x in base.relatorios_pendentes() if not valor or x["terapia"] == valor]
        titulo, r = f"Relatórios pendentes{f' — {NOMES_TERAPIA.get(valor, valor)}' if valor else ''}", op.linhas_relatorios(rel)
        r["filtros"] = op.filtros_relatorios(rel)
    elif tipo == "paciente":
        chave = chave_paciente(valor)
        lst = [a for a in base.atend if a["_pac"] == chave]
        if not lst:
            raise ValueError("Paciente não encontrado.")
        ids = {a["origem_id"] for a in lst}
        titulo = f"Histórico de visitas — {lst[0]['nome_paciente']} ({len(lst)} atendimento(s): {', '.join(sorted(ids))})"
        r = c.linhas_visitas([v for v in base.visitas if v["atendimento_origem_id"] in ids])
        r["drill"] = None
    else:
        raise ValueError("Detalhamento desconhecido.")

    total = len(r["linhas"])
    saida = {"titulo": titulo, "colunas": r["colunas"], "linhas": r["linhas"][:LIMITE_DETALHE], "drill": r.get("drill"),
             "total": total, "truncado": total > LIMITE_DETALHE}
    if r.get("filtros"):  # caixas de seleção do detalhe; "marcas" acompanha cada linha (1 = passa no filtro)
        saida["filtros"] = [{**f, "marcas": f["marcas"][:LIMITE_DETALHE]} for f in r["filtros"]]
    return saida
