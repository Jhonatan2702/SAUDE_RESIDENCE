from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

from .bi import FAIXAS, _parse, _periodos, _taxa_mortalidade
from .db import connect

PERIODOS = {"dia": "Dia", "mes": "Mês", "ano": "Ano"}
SITUACOES = {"ativos": "Ativos", "alta": "Com alta", "todos": "Todos"}
ATIVO_P = "(p.data_alta IS NULL OR p.data_alta = '')"


# ---------- formatação ----------
def br(v) -> str:
    try:
        return datetime.strptime(v or "", "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return v or "—"


def mes_br(v) -> str:
    return f"{v[5:7]}/{v[:4]}" if v and re.fullmatch(r"\d{4}-\d{2}", v) else (v or "—")


def val(v) -> str:
    return "—" if v is None or v == "" else v


def pct(parte: int, total: int) -> str:
    return f"{parte * 100 / total:.1f}".replace(".", ",") + "%" if total else "0,0%"


def dinheiro(v) -> str:
    return "R$ " + f"{float(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def idade(nasc: str | None, hoje: date) -> int | None:
    try:
        b = datetime.strptime(nasc or "", "%Y-%m-%d").date()
    except ValueError:
        return None
    return hoje.year - b.year - ((hoje.month, hoje.day) < (b.month, b.day))


def periodo_txt(ref: date, periodo: str) -> str:
    return {"dia": ref.strftime("%d/%m/%Y"), "mes": ref.strftime("%m/%Y"), "ano": str(ref.year)}[periodo]


def contagem(rows, titulo: str, rotulo: str, vazio: str = "Não informado") -> dict:
    dados = [(r[0] or vazio, r[1]) for r in rows]
    total = sum(t for _, t in dados)
    return {
        "titulo": titulo,
        "colunas": [rotulo, "Quantidade", "%"],
        "linhas": [[n, t, pct(t, total)] for n, t in dados],
        "rodape": ["Total", total, "100,0%" if total else "0,0%"],
    }


def _filtro_periodo(p) -> list:
    return [("Período", f"{PERIODOS[p['periodo']]} — {periodo_txt(p['ref'], p['periodo'])}")]


def _movs(eventos: list[str], p):
    marks = ",".join("?" * len(eventos))
    with connect() as c:
        return c.execute(
            "SELECT m.data, m.codigo_paciente, p.nome, p.operadora, p.servico, p.complexidade, p.diagnostico, "
            "m.evento, m.motivo FROM movimentacao m LEFT JOIN pacientes p ON p.codigo = m.codigo_paciente "
            f"WHERE m.evento IN ({marks}) AND m.data BETWEEN ? AND ? ORDER BY m.data, p.nome",
            (*eventos, p["ini"], p["fim"]),
        ).fetchall()


def _ativos(sql: str, params=()):
    with connect() as c:
        return c.execute(sql.replace("{ATIVO}", ATIVO_P), params).fetchall()


# ---------- análises ----------
def r_altas(p):
    rows = _movs(["Alta"], p)
    return {
        "filtros": _filtro_periodo(p),
        "resumo": [("Altas no período", len(rows))],
        "secoes": [{
            "titulo": "Pacientes com alta",
            "colunas": ["Data", "Código", "Paciente", "Operadora", "Serviço", "Motivo"],
            "linhas": [[br(r[0]), r[1], val(r[2]), val(r[3]), val(r[4]), r[8] or "Não informado"] for r in rows],
        }],
    }


def r_motivos(p):
    rows = _movs(["Alta", "Óbito"], p)
    contagens: dict[str, int] = {}
    for r in rows:
        k = r[8] or "Não informado"
        contagens[k] = contagens.get(k, 0) + 1
    ordenados = sorted(contagens.items(), key=lambda i: -i[1])
    return {
        "filtros": _filtro_periodo(p),
        "resumo": [("Saídas no período (alta + óbito)", len(rows)), ("Motivos distintos", len(ordenados))],
        "secoes": [
            contagem(ordenados, "Motivos de alta (ranking)", "Motivo"),
            {
                "titulo": "Detalhamento",
                "colunas": ["Data", "Código", "Paciente", "Evento", "Motivo"],
                "linhas": [[br(r[0]), r[1], val(r[2]), r[7], r[8] or "Não informado"] for r in rows],
            },
        ],
    }


def r_admissoes(p):
    rows = _movs(["Admissão"], p)
    return {
        "filtros": _filtro_periodo(p),
        "resumo": [("Admissões no período", len(rows))],
        "secoes": [{
            "titulo": "Pacientes admitidos",
            "colunas": ["Data", "Código", "Paciente", "Operadora", "Serviço", "Complexidade", "Diagnóstico"],
            "linhas": [[br(r[0]), r[1], val(r[2]), val(r[3]), val(r[4]), val(r[5]), val(r[6])] for r in rows],
        }],
    }


def r_pendencias(p):
    with connect() as c:
        rows = c.execute(
            "SELECT t.terapia, t.codigo_paciente, p.nome, t.profissional, t.empresa, t.agendado, t.observacao "
            "FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente "
            f"WHERE t.mes = ? AND t.situacao = 'Pendente' AND {ATIVO_P} ORDER BY t.terapia, p.nome",
            (p["mes"],),
        ).fetchall()
        terapias = [r[0] for r in c.execute("SELECT valor FROM opcoes WHERE lista = 'terapias' ORDER BY id")]
    cont = {}
    for r in rows:
        cont[r[0]] = cont.get(r[0], 0) + 1
    por_terapia = [(t, cont.get(t, 0)) for t in terapias] + [(t, n) for t, n in cont.items() if t not in terapias]
    return {
        "filtros": [("Mês", mes_br(p["mes"]))],
        "resumo": [("Pendências no mês", len(rows))],
        "secoes": [
            contagem(por_terapia, "Pendências por terapia", "Terapia"),
            {
                "titulo": "Detalhamento das pendências",
                "colunas": ["Terapia", "Código", "Paciente", "Profissional", "Empresa", "Agendado", "Observação"],
                "linhas": [[r[0], r[1], val(r[2]), val(r[3]), val(r[4]), val(r[5]), val(r[6])] for r in rows],
            },
        ],
    }


def r_mortalidade(p):
    pers = _periodos(p["ref"])
    with connect() as c:
        taxas = [(nome, _taxa_mortalidade(c, *pers[k])) for nome, k in (("Mês", "mes"), ("Ano", "ano"))]
    rows = _movs(["Óbito"], p)
    return {
        "filtros": _filtro_periodo(p),
        "resumo": [(f"Taxa {n.lower()} ({periodo_txt(p['ref'], k)})", f"{t['taxa']:.2f}".replace(".", ",") + "%")
                   for (n, t), k in zip(taxas, ("mes", "ano"))] + [("Óbitos no período", len(rows))],
        "secoes": [
            {
                "titulo": "Taxa de mortalidade (óbitos ÷ pacientes expostos)",
                "colunas": ["Período", "Óbitos", "Pacientes expostos", "Taxa"],
                "linhas": [[f"{n} {periodo_txt(p['ref'], k)}", t["obitos"], t["base"], f"{t['taxa']:.2f}".replace(".", ",") + "%"]
                           for (n, t), k in zip(taxas, ("mes", "ano"))],
            },
            {
                "titulo": "Óbitos no período selecionado",
                "colunas": ["Data", "Código", "Paciente", "Diagnóstico", "Motivo"],
                "linhas": [[br(r[0]), r[1], val(r[2]), val(r[6]), val(r[8])] for r in rows],
            },
        ],
    }


def r_localidade(p):
    bairros = _ativos("SELECT p.bairro, COUNT(*) t FROM pacientes p WHERE {ATIVO} GROUP BY p.bairro ORDER BY t DESC")
    cidades = _ativos("SELECT p.cidade, COUNT(*) t FROM pacientes p WHERE {ATIVO} GROUP BY p.cidade ORDER BY t DESC")
    return {
        "filtros": [("Base", "Pacientes ativos")],
        "resumo": [("Pacientes ativos", sum(r[1] for r in cidades)), ("Bairros", len(bairros)), ("Cidades", len(cidades))],
        "secoes": [contagem(bairros, "Pacientes por bairro", "Bairro"), contagem(cidades, "Pacientes por cidade", "Cidade")],
    }


def _analise_coluna(coluna: str, titulo: str, rotulo: str, vazio: str):
    def fn(p):
        rows = _ativos(f"SELECT p.{coluna}, COUNT(*) t FROM pacientes p WHERE {{ATIVO}} GROUP BY p.{coluna} ORDER BY t DESC")
        nomes = _ativos(f"SELECT p.{coluna}, p.codigo, p.nome, p.servico, p.operadora FROM pacientes p WHERE {{ATIVO}} ORDER BY p.{coluna}, p.nome")
        return {
            "filtros": [("Base", "Pacientes ativos")],
            "resumo": [("Pacientes ativos", sum(r[1] for r in rows)), (f"{rotulo}s distintos", len(rows))],
            "secoes": [
                contagem(rows, titulo, rotulo, vazio),
                {
                    "titulo": "Relação nominal",
                    "colunas": [rotulo, "Código", "Paciente", "Serviço", "Operadora"],
                    "linhas": [[r[0] or vazio, r[1], val(r[2]), val(r[3]), val(r[4])] for r in nomes],
                },
            ],
        }

    return fn


def r_idade(p):
    hoje = date.today()
    rows = _ativos("SELECT p.codigo, p.nome, p.nascimento, p.sexo, p.servico FROM pacientes p WHERE {ATIVO}")
    comidade = [(r, idade(r[2], hoje)) for r in rows]
    idades = [i for _, i in comidade if i is not None]
    faixas = [(n, sum(1 for i in idades if a <= i <= b)) for n, a, b in FAIXAS]
    comidade.sort(key=lambda x: (x[1] is None, -(x[1] or 0)))
    return {
        "filtros": [("Base", "Pacientes ativos"), ("Data de cálculo", hoje.strftime("%d/%m/%Y"))],
        "resumo": [("Idade média", (f"{sum(idades) / len(idades):.1f}".replace(".", ",") + " anos") if idades else "—"),
                   ("Mais novo", f"{min(idades)} anos" if idades else "—"), ("Mais velho", f"{max(idades)} anos" if idades else "—")],
        "secoes": [
            contagem(faixas, "Pacientes por faixa etária", "Faixa etária"),
            {
                "titulo": "Relação nominal (da maior para a menor idade)",
                "colunas": ["Código", "Paciente", "Nascimento", "Idade", "Sexo", "Serviço"],
                "linhas": [[r[0], val(r[1]), br(r[2]), "—" if i is None else i, val(r[3]), val(r[4])] for r, i in comidade],
            },
        ],
    }


def r_servico_operadora(p):
    serv = _ativos("SELECT p.servico, COUNT(*) t FROM pacientes p WHERE {ATIVO} GROUP BY p.servico ORDER BY t DESC")
    oper = _ativos("SELECT p.operadora, COUNT(*) t FROM pacientes p WHERE {ATIVO} GROUP BY p.operadora ORDER BY t DESC")
    cruz = _ativos(
        "SELECT s, o, COUNT(*) AS t FROM (SELECT COALESCE(NULLIF(p.servico,''),'Não informado') AS s, "
        "COALESCE(NULLIF(p.operadora,''),'Não informada') AS o FROM pacientes p WHERE {ATIVO}) x GROUP BY s, o ORDER BY s, t DESC"
    )
    return {
        "filtros": [("Base", "Pacientes ativos")],
        "resumo": [("Pacientes ativos", sum(r[1] for r in serv)), ("Serviços", len(serv)), ("Operadoras", len(oper))],
        "secoes": [
            contagem(serv, "Pacientes por serviço", "Serviço"),
            contagem(oper, "Pacientes por operadora", "Operadora", "Não informada"),
            {
                "titulo": "Serviço × operadora",
                "colunas": ["Serviço", "Operadora", "Quantidade"],
                "linhas": [[r[0], r[1], r[2]] for r in cruz],
            },
        ],
    }


# ---------- listagens ----------
def r_lista_pacientes(p):
    filtro = {"ativos": f"WHERE {ATIVO_P}", "alta": f"WHERE NOT {ATIVO_P}", "todos": ""}[p["situacao"]]
    rows = _ativos(
        "SELECT p.codigo, p.nome, p.nascimento, p.sexo, p.bairro, p.cidade, p.operadora, p.diagnostico, p.complexidade, "
        f"p.servico, p.data_admissao, p.data_alta, p.motivo_alta FROM pacientes p {filtro} ORDER BY p.nome COLLATE NOCASE"
    )
    return {
        "filtros": [("Situação", SITUACOES[p["situacao"]])],
        "resumo": [("Pacientes listados", len(rows))],
        "secoes": [{
            "titulo": "Pacientes",
            "colunas": ["Código", "Nome", "Nascimento", "Sexo", "Bairro", "Cidade", "Operadora", "Diagnóstico",
                        "Complexidade", "Serviço", "Admissão", "Alta", "Motivo da alta"],
            "linhas": [[r[0], r[1], br(r[2]), val(r[3]), val(r[4]), val(r[5]), val(r[6]), val(r[7]), val(r[8]), val(r[9]),
                        br(r[10]), br(r[11]), val(r[12])] for r in rows],
        }],
    }


def r_lista_terapias(p):
    rows = _ativos(
        "SELECT t.mes, t.codigo_paciente, p.nome, t.terapia, t.modalidade, t.empresa, t.profissional, t.situacao, "
        "t.sessoes, t.frequencia, t.valor, t.agendado, t.relatorio, t.observacao FROM terapias t "
        "LEFT JOIN pacientes p ON p.codigo = t.codigo_paciente WHERE t.mes = ? ORDER BY p.nome, t.terapia",
        (p["mes"],),
    )
    return {
        "filtros": [("Mês", mes_br(p["mes"]))],
        "resumo": [("Terapias listadas", len(rows)), ("Sessões", sum(r[8] or 0 for r in rows)),
                   ("Valor total", dinheiro(sum(r[10] or 0 for r in rows)))],
        "secoes": [{
            "titulo": "Terapias do mês",
            "colunas": ["Código", "Paciente", "Terapia", "Modalidade", "Empresa", "Profissional", "Situação",
                        "Sessões", "Frequência", "Valor", "Agendado", "Relatório", "Observação"],
            "linhas": [[r[1], val(r[2]), r[3], val(r[4]), val(r[5]), val(r[6]), val(r[7]), r[8] or 0, val(r[9]),
                        dinheiro(r[10]), val(r[11]), val(r[12]), val(r[13])] for r in rows],
        }],
    }


def r_lista_movimentacao(p):
    rows = _movs(["Admissão", "Alta", "Óbito", "Internação", "Retorno"], p)
    return {
        "filtros": _filtro_periodo(p),
        "resumo": [("Eventos no período", len(rows))],
        "secoes": [
            contagem(_contar(r[7] for r in rows), "Eventos por tipo", "Evento"),
            {
                "titulo": "Movimentação",
                "colunas": ["Data", "Código", "Paciente", "Evento", "Motivo"],
                "linhas": [[br(r[0]), r[1], val(r[2]), r[7], val(r[8])] for r in rows],
            },
        ],
    }


def _contar(itens) -> list:
    cont: dict[str, int] = {}
    for i in itens:
        cont[i] = cont.get(i, 0) + 1
    return sorted(cont.items(), key=lambda x: -x[1])


# ---------- registro ----------
REL = {
    "altas": dict(titulo="Altas", grupo="Análises (BI)", icone="🏁", descr="Pacientes que receberam alta no dia, mês ou ano.", filtros=["periodo"], fn=r_altas),
    "motivos-alta": dict(titulo="Motivos de alta", grupo="Análises (BI)", icone="📝", descr="Ranking dos principais motivos de alta e óbito.", filtros=["periodo"], fn=r_motivos),
    "admissoes": dict(titulo="Admissões", grupo="Análises (BI)", icone="➕", descr="Pacientes admitidos no dia, mês ou ano.", filtros=["periodo"], fn=r_admissoes),
    "pendencias": dict(titulo="Pendências por terapia", grupo="Análises (BI)", icone="⏳", descr="Terapias pendentes (Psico, Nutri, TO, Fono, Fisio) do mês.", filtros=["mes"], fn=r_pendencias),
    "mortalidade": dict(titulo="Taxa de mortalidade", grupo="Análises (BI)", icone="📉", descr="Taxa mensal e anual e relação de óbitos.", filtros=["periodo"], fn=r_mortalidade),
    "localidade": dict(titulo="Pacientes por bairro e cidade", grupo="Análises (BI)", icone="📍", descr="Distribuição geográfica dos pacientes ativos.", filtros=[], fn=r_localidade),
    "complexidade": dict(titulo="Pacientes por complexidade", grupo="Análises (BI)", icone="🎯", descr="Básico, intermediário e intensivo, com percentual.", filtros=[], fn=_analise_coluna("complexidade", "Pacientes por complexidade", "Complexidade", "Não informada")),
    "idade": dict(titulo="Pacientes por idade", grupo="Análises (BI)", icone="🎂", descr="Faixas etárias, idade média e relação nominal.", filtros=[], fn=r_idade),
    "diagnostico": dict(titulo="Pacientes por diagnóstico", grupo="Análises (BI)", icone="🩻", descr="Distribuição por diagnóstico e relação nominal.", filtros=[], fn=_analise_coluna("diagnostico", "Pacientes por diagnóstico", "Diagnóstico", "Não informado")),
    "servico-operadora": dict(titulo="Pacientes por serviço e operadora", grupo="Análises (BI)", icone="🏥", descr="Totais por serviço, por operadora e cruzamento.", filtros=[], fn=r_servico_operadora),
    "lista-pacientes": dict(titulo="Listagem de pacientes", grupo="Listagens", icone="👤", descr="Cadastro completo de pacientes (ativos, com alta ou todos).", filtros=["situacao"], fn=r_lista_pacientes),
    "lista-terapias": dict(titulo="Listagem de terapias", grupo="Listagens", icone="🩺", descr="Terapias do mês por paciente, com sessões e valores.", filtros=["mes"], fn=r_lista_terapias),
    "lista-movimentacao": dict(titulo="Listagem de movimentação", grupo="Listagens", icone="🔁", descr="Admissões, altas, óbitos, internações e retornos.", filtros=["periodo"], fn=r_lista_movimentacao),
}


def agrupados() -> dict[str, list[tuple[str, dict]]]:
    grupos: dict[str, list] = {}
    for slug, r in REL.items():
        grupos.setdefault(r["grupo"], []).append((slug, r))
    return grupos


def parametros(args) -> dict:
    hoje = date.today()
    ref = _parse(args.get("ref"), hoje)
    periodo = args.get("periodo") if args.get("periodo") in PERIODOS else "mes"
    ini, fim = _periodos(ref)[periodo]
    mes = args.get("mes") if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", args.get("mes") or "") else hoje.strftime("%Y-%m")
    situacao = args.get("situacao") if args.get("situacao") in SITUACOES else "ativos"
    return {"ref": ref, "periodo": periodo, "ini": ini, "fim": fim, "mes": mes, "situacao": situacao}


def gerar(slug: str, args) -> dict:
    meta = REL[slug]
    p = parametros(args)
    dados = meta["fn"](p)
    return {**dados, "slug": slug, "titulo": meta["titulo"], "meta": meta, "params": p, "gerado_em": datetime.now()}


def para_csv(dados: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["TST-GESTÃO", dados["titulo"], dados["gerado_em"].strftime("%d/%m/%Y %H:%M")])
    for k, v in dados["filtros"]:
        w.writerow([k, v])
    for k, v in dados["resumo"]:
        w.writerow([k, v])
    for s in dados["secoes"]:
        w.writerow([])
        w.writerow([s["titulo"]])
        w.writerow(s["colunas"])
        w.writerows(s["linhas"])
        if s.get("rodape"):
            w.writerow(s["rodape"])
    return buf.getvalue().encode("utf-8-sig")
