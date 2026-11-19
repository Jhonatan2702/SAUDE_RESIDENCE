"""Painel operacional: listas do dia a dia montadas a partir do espelho da URL.

- Relatórios pendentes (lista atual enviada pela URL)
- Profissional × atendimento (visitas do período por profissional e seus pacientes)
- Região de abrangência / disponibilidade de bairro por profissional
- Fichas realizadas no App (visitas registradas no período)
- Tabela de preços por empresa (aguardando a URL enviar valores)
"""
from __future__ import annotations

from collections import Counter
from datetime import date

from .fonte import NOMES_TERAPIA, Base, br, carregar, em_fortaleza, periodo, tem_terapias

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


def relatorios() -> dict:
    base = carregar()
    rel = base.relatorios_pendentes()
    competencias = Counter(_ordem_competencia(r.get("competencia")) for r in rel)
    return {
        "atualizado_em": base.sincronizado,
        "total": len(rel),
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
        "sem_cobertura": sorted(({"bairro": b, "pacientes": len(p)} for b, p in indicados.items() if b not in por_bairro),
                                key=lambda x: (-x["pacientes"], x["bairro"])),
        "zonas": zonas,
    }


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
