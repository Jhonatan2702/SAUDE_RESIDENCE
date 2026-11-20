"""Painel operacional: listas do dia a dia montadas a partir do espelho da URL.

- Relatórios pendentes (lista atual enviada pela URL)
- Profissional × atendimento (visitas do período por profissional e seus pacientes)
- Operacional do paciente (paciente / terapia / profissional no período)
- Região de abrangência / disponibilidade de bairro por profissional
- Fichas realizadas no App (visitas registradas no período)
- Tabela de preços por empresa (aguardando a URL enviar valores)
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from .fonte import JANELA_COBERTURA, NOMES_TERAPIA, Base, br, carregar, em_fortaleza, periodo, tem_terapias

COLS_RELATORIOS = ["Paciente", "Atendimento", "Profissional", "Terapia", "Especialidade", "Competência", "Operadora", "Relatório"]
COLS_FICHAS = ["Data", "Paciente", "Atendimento", "Profissional", "Terapia", "Operadora", "Bairro"]
LIMITE = 10_000


def chave_profissional(v: dict) -> str | None:
    if v.get("profissional_id"):
        return "id:" + str(v["profissional_id"])
    if v.get("profissional"):
        return "nome:" + v["profissional"]
    return None


def _competencia(c: str | None) -> str:
    c = (c or "").strip()
    return f"{c[5:7]}/{c[:4]}" if len(c) == 7 and c[4] == "-" else (c or "—")


def _ordem_competencia(c: str | None) -> str:
    c = (c or "").strip()
    if len(c) == 7 and c[2] == "/":  # MM/AAAA
        return c[3:] + "-" + c[:2]
    return c


# ---------------------------------------------------------------- relatórios pendentes
def linhas_relatorios(rel: list[dict]) -> dict:
    rel = sorted(rel, key=lambda r: (_ordem_competencia(r.get("competencia")), (r.get("profissional") or "").casefold()))
    linhas = [[r["paciente"], r["atendimento"], r.get("profissional") or "—", r["terapia"], r.get("especialidade") or "—",
               _competencia(r.get("competencia")), r.get("operadora") or "—", r.get("id") or "—"] for r in rel]
    return {"colunas": COLS_RELATORIOS, "linhas": linhas, "drill": None}


COMPETENCIAS = ("atual", "anterior", "todas")


def _mes(d: date, recuo: int = 0) -> str:
    """Competência (AAAA-MM) do mês de d, recuando `recuo` meses."""
    ano, mes = divmod(d.year * 12 + d.month - 1 - recuo, 12)
    return f"{ano:04d}-{mes + 1:02d}"


def relatorios(comp: str = "atual", hoje: date | None = None) -> dict:
    """Relatórios pendentes da competência escolhida: mês atual (padrão), mês anterior ou todas.

    Fora de "todas", informa quantas pendências de competências anteriores ficaram de fora,
    para o atraso antigo não sumir sem ninguém perceber."""
    comp = comp if comp in COMPETENCIAS else "atual"
    base = carregar()
    todas = base.relatorios_pendentes()
    alvo = None if comp == "todas" else _mes(hoje or date.today(), 1 if comp == "anterior" else 0)
    chave = lambda r: _ordem_competencia(r.get("competencia"))[:7]
    rel = todas if alvo is None else [r for r in todas if chave(r) == alvo]
    anteriores = [] if alvo is None else [r for r in todas if chave(r) and chave(r) < alvo]
    competencias = Counter(_ordem_competencia(r.get("competencia")) for r in rel)
    todas_comp = [c for c in (chave(r) for r in todas) if c]
    return {
        "atualizado_em": base.sincronizado,
        "competencia": comp, "competencia_rotulo": _competencia(alvo) if alvo else "Todas",
        "total": len(rel), "total_geral": len(todas), "anteriores": len(anteriores),
        "mais_antiga_geral": _competencia(min(todas_comp)) if todas_comp else "—",
        "pacientes": len({r["paciente"].casefold() for r in rel}),
        "profissionais": len({r.get("profissional") for r in rel if r.get("profissional")}),
        "mais_antiga": _competencia(min(competencias)[:7]) if competencias else "—",
        "por_terapia": [{"rotulo": k, "nome": NOMES_TERAPIA.get(k, k), "valor": v}
                        for k, v in Counter(r["terapia"] for r in rel).most_common()],
        "por_profissional": [{"rotulo": k, "valor": v}
                             for k, v in Counter(r.get("profissional") or "Não informado" for r in rel).most_common(10)],
        "por_competencia": [{"rotulo": _competencia(k), "valor": v} for k, v in sorted(competencias.items())],
        **linhas_relatorios(rel),
    }


# ---------------------------------------------------------------- profissionais
def resumo_profissionais(base: Base, ini: date, fim: date) -> list[dict]:
    """Carga de cada profissional no período (ordenado por visitas)."""
    grupos: dict[str, dict] = {}
    for v in base.visitas_entre(ini, fim):
        chave = chave_profissional(v)
        a = base.por_id.get(v["atendimento_origem_id"])
        if not chave or not a:
            continue
        g = grupos.setdefault(chave, {"chave": chave, "nome": v["profissional"] or "Sem nome", "visitas": 0, "dias": set(),
                                      "pacientes": set(), "ter": Counter(), "bairros": set()})
        g["visitas"] += 1
        g["dias"].add(v["_data"])
        g["pacientes"].add(a["_pac"])
        g["ter"][v["_ter"]] += 1
        if a["bairro"]:
            g["bairros"].add(a["bairro"])
    return [{"chave": g["chave"], "nome": g["nome"], "terapia": g["ter"].most_common(1)[0][0], "visitas": g["visitas"],
             "dias": len(g["dias"]), "pacientes": len(g["pacientes"]), "bairros": len(g["bairros"])}
            for g in sorted(grupos.values(), key=lambda g: (-g["visitas"], g["nome"].casefold()))]


def profissionais(ini: date | None, fim: date | None) -> dict:
    ini, fim = periodo(ini, fim)
    base = carregar()
    lista = resumo_profissionais(base, ini, fim)
    return {"periodo": {"ini": ini.isoformat(), "fim": fim.isoformat()}, "atualizado_em": base.sincronizado,
            "profissionais": lista, "visitas": sum(p["visitas"] for p in lista)}


def pacientes_profissional(chave: str, ini: date | None, fim: date | None) -> dict:
    """Pacientes atendidos pelo profissional no período (uma linha por atendimento)."""
    ini, fim = periodo(ini, fim)
    base = carregar()
    grupos: dict[str, dict] = {}
    nome = None
    for v in base.visitas_entre(ini, fim):
        if chave_profissional(v) != chave:
            continue
        nome = nome or v["profissional"]
        a = base.por_id.get(v["atendimento_origem_id"], {})
        g = grupos.setdefault(v["atendimento_origem_id"], {
            "paciente": a.get("nome_paciente") or "Paciente não encontrado", "atendimento": v["atendimento_origem_id"],
            "operadora": a.get("operadora") or "—", "servico": a.get("servico") or "—", "bairro": a.get("bairro") or "—",
            "visitas": 0, "primeira": v["_data"], "ultima": v["_data"], "terapias": set()})
        g["visitas"] += 1
        g["primeira"], g["ultima"] = min(g["primeira"], v["_data"]), max(g["ultima"], v["_data"])
        g["terapias"].add(v["_ter"])
    linhas = [[g["paciente"], g["atendimento"], g["operadora"], g["servico"], g["bairro"], " · ".join(sorted(g["terapias"])),
               g["visitas"], br(g["primeira"]), br(g["ultima"])]
              for g in sorted(grupos.values(), key=lambda g: (g["paciente"].casefold(), g["atendimento"]))]
    return {"titulo": f"Pacientes de {nome or 'profissional'} ({br(ini)} a {br(fim)})",
            "colunas": ["Paciente", "Atendimento", "Operadora", "Serviço", "Bairro", "Terapias", "Visitas", "Primeira", "Última"],
            "linhas": linhas, "total": len(linhas), "truncado": False, "drill": None}


# ---------------------------------------------------------------- operacional do paciente
COLS_PACIENTES = ["Paciente", "Atendimento", "Terapia", "Profissional", "Visitas", "Primeira", "Última", "Operadora", "Bairro"]


def pacientes(ini: date | None, fim: date | None) -> dict:
    """Visão completa paciente / terapia / profissional no período: uma linha por combinação, com as visitas."""
    ini, fim = periodo(ini, fim)
    base = carregar()
    grupos: dict[tuple, dict] = {}
    for v in base.visitas_entre(ini, fim):
        a = base.por_id.get(v["atendimento_origem_id"], {})
        k = (v["atendimento_origem_id"], v["_ter"], chave_profissional(v) or "")
        g = grupos.setdefault(k, {
            "paciente": a.get("nome_paciente") or "Paciente não encontrado", "pac": a.get("_pac"),
            "atendimento": v["atendimento_origem_id"], "terapia": v["_ter"], "profissional": v["profissional"] or "Não informado",
            "operadora": a.get("operadora") or "—", "bairro": a.get("bairro") or "—",
            "visitas": 0, "primeira": v["_data"], "ultima": v["_data"]})
        g["visitas"] += 1
        g["primeira"], g["ultima"] = min(g["primeira"], v["_data"]), max(g["ultima"], v["_data"])
    ordem = sorted(grupos.values(), key=lambda g: (g["paciente"].casefold(), g["atendimento"], g["terapia"], g["profissional"].casefold()))
    linhas = [[g["paciente"], g["atendimento"], g["terapia"], g["profissional"], g["visitas"], br(g["primeira"]), br(g["ultima"]),
               g["operadora"], g["bairro"]] for g in ordem]
    ter = Counter({t: len(p) for t, p in _por_terapia(ordem).items()})  # pacientes distintos por terapia
    return {
        "periodo": {"ini": ini.isoformat(), "fim": fim.isoformat()}, "atualizado_em": base.sincronizado,
        "pacientes": len({g["pac"] or g["paciente"] for g in ordem}), "atendimentos": len({g["atendimento"] for g in ordem}),
        "profissionais": len({g["profissional"] for g in ordem if g["profissional"] != "Não informado"}),
        "visitas": sum(g["visitas"] for g in ordem),
        "por_terapia": [{"rotulo": k, "nome": NOMES_TERAPIA.get(k, k), "valor": n} for k, n in ter.most_common()],
        "colunas": COLS_PACIENTES, "linhas": linhas[:LIMITE], "total": len(linhas), "truncado": len(linhas) > LIMITE,
    }


def _por_terapia(grupos: list[dict]) -> dict[str, set]:
    """{terapia: pacientes distintos atendidos nela}."""
    saida: dict[str, set] = {}
    for g in grupos:
        saida.setdefault(g["terapia"], set()).add(g["pac"] or g["paciente"])
    return saida


# ---------------------------------------------------------------- região de abrangência
def abrangencia(ini: date | None, fim: date | None) -> dict:
    """Bairros e zonas onde cada profissional atendeu pacientes no período (disponibilidade observada)."""
    ini, fim = periodo(ini, fim)
    base = carregar()
    nome_zona = lambda z: base.zonas.get(z, {}).get("nome", "SEM ZONA") if z else "SEM ZONA"  # noqa: E731
    pares: dict[tuple, dict] = {}
    por_zona: dict[str, dict] = {}
    for v in base.visitas_entre(ini, fim):
        chave = chave_profissional(v)
        a = base.por_id.get(v["atendimento_origem_id"])
        if not chave or not a:
            continue
        bairro = a["bairro"] or "NÃO INFORMADO"
        g = pares.setdefault((chave, bairro), {"profissional": v["profissional"] or "Sem nome", "bairro": bairro,
                                               "cidades": Counter(), "zonas": Counter(), "pacientes": set(), "visitas": 0, "ter": Counter()})
        if a["cidade"]:  # a URL nem sempre envia a cidade; usa a mais frequente do bairro
            g["cidades"][a["cidade"]] += 1
        g["zonas"][nome_zona(a["zona"])] += 1
        g["pacientes"].add(a["_pac"])
        g["visitas"] += 1
        g["ter"][v["_ter"]] += 1
        if a["zona"]:
            z = por_zona.setdefault(a["zona"], {"profissionais": set(), "visitas": 0})
            z["profissionais"].add(chave)
            z["visitas"] += 1
    linhas = sorted(pares.values(), key=lambda g: (g["profissional"].casefold(), -len(g["pacientes"]), g["bairro"]))
    por_bairro: dict[str, set] = {}
    for g in linhas:
        por_bairro.setdefault(g["bairro"], set()).add(g["profissional"])
    # quem cobre cada bairro: visitou alguém lá nos últimos JANELA_COBERTURA dias (mesmo sem visita no período)
    cobre: dict[str, dict] = {}
    cobre_zona: dict[str, set] = {}
    inicio_cob = fim - timedelta(days=JANELA_COBERTURA - 1)
    for v in base.visitas:
        if inicio_cob <= v["_data"] <= fim and (a := base.por_id.get(v["atendimento_origem_id"])) and (k := chave_profissional(v)) and a["zona"]:
            cobre_zona.setdefault(a["zona"], set()).add(k)
        if inicio_cob <= v["_data"] <= fim and (a := base.por_id.get(v["atendimento_origem_id"])) and a["bairro"] and (k := chave_profissional(v)):
            atual = cobre.setdefault(a["bairro"], {}).get(k)
            if not atual or v["_data"] > atual[1]:
                cobre[a["bairro"]][k] = (v["profissional"] or "Sem nome", v["_data"])
    # pacientes ativos indicados com terapias, por bairro de Fortaleza e por zona: base para achar áreas sem cobertura
    indicados: dict[str, set] = {}
    indicados_zona: dict[str, set] = {}
    for a in base.ativos(fim):
        if not tem_terapias(a):
            continue
        if a["bairro"] and em_fortaleza(a):
            indicados.setdefault(a["bairro"], set()).add(a["_pac"])
        if a["zona"]:
            indicados_zona.setdefault(a["zona"], set()).add(a["_pac"])
    zonas = []
    for zid in sorted(set(por_zona) | set(indicados_zona), key=lambda z: nome_zona(z)):
        zinfo = base.zonas.get(zid, {})
        zonas.append({"id": zid, "nome": nome_zona(zid), "bairros": zinfo.get("bairros", []),
                      "indicados": len(indicados_zona.get(zid, ())),
                      "profissionais": len(por_zona.get(zid, {}).get("profissionais", ())),
                      "cobrem": len(cobre_zona.get(zid, ())),
                      "visitas": por_zona.get(zid, {}).get("visitas", 0)})
    return {
        "periodo": {"ini": ini.isoformat(), "fim": fim.isoformat()}, "atualizado_em": base.sincronizado,
        "colunas": ["Profissional", "Terapia", "Zona", "Bairro", "Cidade", "Pacientes", "Visitas"],
        "linhas": [[g["profissional"], g["ter"].most_common(1)[0][0], g["zonas"].most_common(1)[0][0], g["bairro"],
                    g["cidades"].most_common(1)[0][0] if g["cidades"] else "NÃO INFORMADA", len(g["pacientes"]), g["visitas"]]
                   for g in linhas],
        "bairros": sorted(({"bairro": b, "profissionais": len(p)} for b, p in por_bairro.items()),
                          key=lambda x: (-x["profissionais"], x["bairro"])),
        "profissionais": len({g["profissional"] for g in linhas}),
        "indicados_bairro": {b: len(p) for b, p in indicados.items()},
        # bairros sem visita no período: quem ainda cobre (visitou alguém lá nos últimos JANELA_COBERTURA dias)
        "sem_cobertura": sorted(({"bairro": b, "pacientes": len(p), "cobrem": [{"nome": n, "ultima": br(d)} for n, d in
                                  sorted(cobre.get(b, {}).values(), key=lambda x: x[1], reverse=True)]}
                                 for b, p in indicados.items() if b not in por_bairro),
                                key=lambda x: (bool(x["cobrem"]), -x["pacientes"], x["bairro"])),
        "cobertura_bairro": {b: len(v) for b, v in cobre.items()},
        "regiao_prof": _regiao_por_profissional(cobre),
        "janela_cobertura": JANELA_COBERTURA,
        "zonas": zonas,
    }


def _regiao_por_profissional(cobre: dict[str, dict]) -> dict[str, list[str]]:
    """{nome do profissional: bairros que ele cobre nos últimos JANELA_COBERTURA dias} (para o mapa de cobertura)."""
    saida: dict[str, set] = {}
    for bairro, profs in cobre.items():
        for nome, _ in profs.values():
            saida.setdefault(nome, set()).add(bairro)
    return {n: sorted(b) for n, b in saida.items()}


# ---------------------------------------------------------------- fichas realizadas no App
def fichas(ini: date | None, fim: date | None) -> dict:
    """Cada visita enviada pela URL é uma ficha/atendimento registrado no App."""
    ini, fim = periodo(ini, fim)
    base = carregar()
    vis = sorted(base.visitas_entre(ini, fim), key=lambda v: (v["_data"], v["profissional"] or ""), reverse=True)
    linhas = []
    for v in vis:
        a = base.por_id.get(v["atendimento_origem_id"], {})
        linhas.append([br(v["_data"]), a.get("nome_paciente", "—"), v["atendimento_origem_id"], v["profissional"] or "—",
                       v["_ter"], a.get("operadora") or "—", a.get("bairro") or "—"])
    return {
        "periodo": {"ini": ini.isoformat(), "fim": fim.isoformat()}, "atualizado_em": base.sincronizado,
        "total": len(linhas), "profissionais": len({v["profissional"] for v in vis if v["profissional"]}),
        "pacientes": len({base.por_id[v["atendimento_origem_id"]]["_pac"] for v in vis if v["atendimento_origem_id"] in base.por_id}),
        "por_terapia": [{"rotulo": k, "nome": NOMES_TERAPIA.get(k, k), "valor": n} for k, n in Counter(v["_ter"] for v in vis).most_common()],
        "colunas": COLS_FICHAS, "linhas": linhas[:LIMITE], "truncado": len(linhas) > LIMITE,
    }
