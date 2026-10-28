from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta

from .db import connect

ATIVO = "(data_alta IS NULL OR data_alta = '')"
FAIXAS = [("0-17", 0, 17), ("18-39", 18, 39), ("40-59", 40, 59), ("60-79", 60, 79), ("80+", 80, 200)]


def _parse(value: str | None, fallback: date) -> date:
    try:
        return datetime.strptime(value or "", "%Y-%m-%d").date()
    except ValueError:
        return fallback


def _pairs(rows, empty: str = "Não informado") -> list[dict]:
    return [{"label": r[0] or empty, "total": r[1]} for r in rows]


def _periodos(ref: date) -> dict[str, tuple[str, str]]:
    d = ref.isoformat()
    m = ref.strftime("%Y-%m")
    return {"dia": (d, d), "mes": (m + "-01", m + "-31"), "ano": (f"{ref.year}-01-01", f"{ref.year}-12-31")}


def _taxa_mortalidade(conn, inicio: str, fim: str, filtro: tuple[str | None, str | None] = (None, None)) -> dict:
    obitos = conn.execute(
        "SELECT COUNT(*) FROM movimentacao m JOIN pacientes p ON p.codigo = m.codigo_paciente "
        "WHERE m.evento = 'Óbito' AND m.data BETWEEN ? AND ?" + _filtro_sql(*filtro, "p")[0],
        (inicio, fim, *_filtro_sql(*filtro, "p")[1])
    ).fetchone()[0]
    expostos = conn.execute(
        "SELECT COUNT(*) FROM pacientes WHERE data_admissao IS NOT NULL AND data_admissao <> '' "
        "AND data_admissao <= ? AND (data_alta IS NULL OR data_alta = '' OR data_alta >= ?)" +
        _filtro_sql(*filtro)[0], (fim, inicio, *_filtro_sql(*filtro)[1]),
    ).fetchone()[0]
    return {"obitos": obitos, "base": expostos, "taxa": round(obitos * 100 / expostos, 2) if expostos else 0}


def _meses(ref: date, n: int = 8) -> list[tuple[str, str, str]]:
    """Últimos n meses até o mês de referência: (AAAA-MM, primeiro dia, último dia)."""
    out, a, m = [], ref.year, ref.month
    for _ in range(n):
        out.append((f"{a}-{m:02d}", f"{a}-{m:02d}-01", f"{a}-{m:02d}-31"))
        a, m = (a, m - 1) if m > 1 else (a - 1, 12)
    return out[::-1]


def _meses_entre(ini: date, fim: date) -> list[tuple[str, str, str]]:
    out, a, m = [], ini.year, ini.month
    while (a, m) <= (fim.year, fim.month):
        out.append((f"{a}-{m:02d}", f"{a}-{m:02d}-01", f"{a}-{m:02d}-31"))
        a, m = (a, m + 1) if m < 12 else (a + 1, 1)
    return out


def _ativos_em(conn, dia: str, filtro: tuple[str | None, str | None] = (None, None)) -> int:
    """Pacientes em atendimento no dia: admitidos até o dia e sem alta até ele."""
    return conn.execute(
        "SELECT COUNT(*) FROM pacientes WHERE data_admissao IS NOT NULL AND data_admissao <> '' AND data_admissao <= ? "
        "AND (data_alta IS NULL OR data_alta = '' OR data_alta > ?)" +
        _filtro_sql(*filtro)[0], (dia, dia, *_filtro_sql(*filtro)[1])).fetchone()[0]


def _periodo(conn, ini: date, fim: date, filtro: tuple[str | None, str | None] = (None, None)) -> dict:
    """Indicadores do período escolhido e do período anterior de mesmo tamanho (para a variação)."""
    dias = (fim - ini).days + 1
    ant_fim = ini - timedelta(days=1)
    ant_ini = ant_fim - timedelta(days=dias - 1)
    if ini.day == 1 and (ini.year, ini.month) == (fim.year, fim.month):  # mês: compara com os mesmos dias do mês anterior
        ant_ini = ant_fim.replace(day=1)
        ant_fim = ant_ini.replace(day=min(fim.day, ant_fim.day))

    def eventos(a: date, b: date) -> dict:
        ev = {r[0]: r[1] for r in conn.execute(
            "SELECT m.evento, COUNT(*) FROM movimentacao m JOIN pacientes p ON p.codigo = m.codigo_paciente "
            "WHERE m.data BETWEEN ? AND ?" + _filtro_sql(*filtro, "p")[0] + " GROUP BY m.evento",
            (a.isoformat(), b.isoformat(), *_filtro_sql(*filtro, "p")[1]))}
        return {"admissoes": ev.get("Admissão", 0), "altas": ev.get("Alta", 0), "obitos": ev.get("Óbito", 0)}

    return {
        "ini": ini.isoformat(), "fim": fim.isoformat(), "dias": dias,
        **eventos(ini, fim), "ativos": _ativos_em(conn, fim.isoformat(), filtro),
        "mortalidade": _taxa_mortalidade(conn, ini.isoformat(), fim.isoformat(), filtro),
        "anterior": {"ini": ant_ini.isoformat(), "fim": ant_fim.isoformat(), **eventos(ant_ini, ant_fim),
                     "ativos": _ativos_em(conn, ant_fim.isoformat(), filtro),
                     "mortalidade": _taxa_mortalidade(conn, ant_ini.isoformat(), ant_fim.isoformat(), filtro)},
    }


FILTRO_COLUNAS = {
    "bairro": "bairro", "cidade": "cidade", "complexidade": "complexidade",
    "diagnostico": "diagnostico", "servico": "servico", "operadora": "operadora",
    "terapia": "terapia", "profissional": "profissional",
}


def _filtro_sql(tipo: str | None, valor: str | None, alias: str = "") -> tuple[str, list[str]]:
    coluna = FILTRO_COLUNAS.get(tipo or "")
    if not coluna or valor is None:
        return "", []
    if tipo in ("terapia", "profissional") and alias != "t":
        paciente = f"{alias}.codigo" if alias else "pacientes.codigo"
        return f" AND EXISTS (SELECT 1 FROM terapias tf WHERE tf.codigo_paciente = {paciente} AND tf.{coluna} = ?)", [valor]
    prefixo = f"{alias}." if alias else ""
    if valor == "Não informado" or valor == "Não informada":
        return f" AND COALESCE(NULLIF({prefixo}{coluna}, ''), ?) = ?", [valor, valor]
    return f" AND {prefixo}{coluna} = ?", [valor]


def _filtro_terapia_sql(tipo: str | None, valor: str | None) -> tuple[str, list[str]]:
    return _filtro_sql(tipo, valor, "t" if tipo in ("terapia", "profissional") else "p")


def _evolucao(conn, ref: date, ini: date | None = None, filtro: tuple[str | None, str | None] = (None, None)) -> dict:
    """Série mensal da carteira (ativos no fim do mês, admissões, altas, óbitos) e resumo das terapias.

    Com período (ini..ref): a série cobre os meses do período (mínimo de 8 meses) e as terapias contam os meses do período.
    """
    meses = _meses(ref)
    if ini and len(_meses_entre(ini, ref)) > len(meses):
        meses = _meses_entre(ini, ref)
    meses_ter = _meses_entre(ini, ref) if ini else meses[-1:]
    m_ini, m_fim = meses_ter[0][0], meses_ter[-1][0]
    serie = []
    filtro_tipo, filtro_valor = filtro
    for mes, ini, fim in meses:
        ev = {r[0]: r[1] for r in conn.execute(
            "SELECT m.evento, COUNT(*) FROM movimentacao m "
            "JOIN pacientes p ON p.codigo = m.codigo_paciente "
            "WHERE m.data BETWEEN ? AND ?" + _filtro_sql(filtro_tipo, filtro_valor, "p")[0] +
            " GROUP BY m.evento", (ini, fim, *_filtro_sql(filtro_tipo, filtro_valor, "p")[1]))}
        ativos = conn.execute(
            "SELECT COUNT(*) FROM pacientes WHERE data_admissao IS NOT NULL AND data_admissao <> '' AND data_admissao <= ? "
            "AND (data_alta IS NULL OR data_alta = '' OR data_alta > ?)" +
            _filtro_sql(filtro_tipo, filtro_valor)[0],
            (fim, fim, *_filtro_sql(filtro_tipo, filtro_valor)[1])).fetchone()[0]
        serie.append({"mes": mes, "ativos": ativos, "admissoes": ev.get("Admissão", 0), "altas": ev.get("Alta", 0), "obitos": ev.get("Óbito", 0)})
    ter: dict[str, dict] = {}
    for mes, terapia, total in conn.execute(
            "SELECT t.mes, t.terapia, COUNT(*) FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente "
            "WHERE t.mes BETWEEN ? AND ?" + _filtro_terapia_sql(filtro_tipo, filtro_valor)[0] +
            " GROUP BY t.mes, t.terapia",
            (meses[0][0], meses[-1][0], *_filtro_terapia_sql(filtro_tipo, filtro_valor)[1])):
        ter.setdefault(terapia, {})[mes] = total
    mes_ref = meses[-1][0]
    situacao = conn.execute(
        "SELECT s, COUNT(*) AS t FROM (SELECT COALESCE(NULLIF(t.situacao, ''), 'Não informado') AS s FROM terapias t "
        "JOIN pacientes p ON p.codigo = t.codigo_paciente WHERE t.mes BETWEEN ? AND ?" +
        _filtro_terapia_sql(filtro_tipo, filtro_valor)[0] + ") x GROUP BY s ORDER BY t DESC",
        (m_ini, m_fim, *_filtro_terapia_sql(filtro_tipo, filtro_valor)[1])).fetchall()
    prof: dict[str, dict] = {}
    for nome, terapia in conn.execute(
            "SELECT t.profissional, t.terapia FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente "
            "WHERE t.mes BETWEEN ? AND ? AND t.profissional IS NOT NULL AND t.profissional <> ''" +
            _filtro_terapia_sql(filtro_tipo, filtro_valor)[0],
            (m_ini, m_fim, *_filtro_terapia_sql(filtro_tipo, filtro_valor)[1])):
        p = prof.setdefault(nome, {"nome": nome, "total": 0, "terapias": set()})
        p["total"] += 1
        p["terapias"].add(terapia)
    top = sorted(prof.values(), key=lambda p: (-p["total"], p["nome"]))[:8]
    resumo = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT t.codigo_paciente), COALESCE(SUM(t.sessoes), 0), COALESCE(SUM(t.sessoes * t.valor), 0) "
        "FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente WHERE t.mes BETWEEN ? AND ?" +
        _filtro_sql(filtro_tipo, filtro_valor, "p")[0],
        (m_ini, m_fim, *_filtro_sql(filtro_tipo, filtro_valor, "p")[1])).fetchone()
    taxas = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN t.situacao = 'Ativa' THEN 1 ELSE 0 END), SUM(CASE WHEN t.agendado = 'Sim' THEN 1 ELSE 0 END), "
        "SUM(CASE WHEN t.relatorio = 'Sim' THEN 1 ELSE 0 END) FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente "
        "WHERE t.mes BETWEEN ? AND ?" + _filtro_terapia_sql(filtro_tipo, filtro_valor)[0],
        (m_ini, m_fim, *_filtro_terapia_sql(filtro_tipo, filtro_valor)[1])).fetchone()
    ativos = conn.execute(f"SELECT COUNT(*) FROM pacientes WHERE {ATIVO}" + _filtro_sql(filtro_tipo, filtro_valor)[0],
                           _filtro_sql(filtro_tipo, filtro_valor)[1]).fetchone()[0]
    cobertos = conn.execute(
        f"SELECT COUNT(DISTINCT t.codigo_paciente) FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente "
        f"WHERE t.mes BETWEEN ? AND ? AND t.situacao = 'Ativa' AND (p.data_alta IS NULL OR p.data_alta = '')" +
        _filtro_terapia_sql(filtro_tipo, filtro_valor)[0],
        (m_ini, m_fim, *_filtro_terapia_sql(filtro_tipo, filtro_valor)[1])).fetchone()[0]
    completos = conn.execute(
        f"SELECT COUNT(*) FROM pacientes WHERE {ATIVO} AND nascimento IS NOT NULL AND nascimento <> '' "
        "AND complexidade IS NOT NULL AND complexidade <> '' AND diagnostico IS NOT NULL AND diagnostico <> ''" +
        _filtro_sql(filtro_tipo, filtro_valor)[0], _filtro_sql(filtro_tipo, filtro_valor)[1]).fetchone()[0]
    pct = lambda a, b: round((a or 0) * 100 / b, 1) if b else 0  # noqa: E731
    indicadores = {
        "terapias_ativas": {"pct": pct(taxas[1], taxas[0]), "parte": taxas[1] or 0, "total": taxas[0]},
        "agendadas": {"pct": pct(taxas[2], taxas[0]), "parte": taxas[2] or 0, "total": taxas[0]},
        "relatorios": {"pct": pct(taxas[3], taxas[0]), "parte": taxas[3] or 0, "total": taxas[0]},
        "cadastro_completo": {"pct": pct(completos, ativos), "parte": completos, "total": ativos},
        "cobertura": {"pct": pct(cobertos, ativos), "parte": cobertos, "total": ativos},
    }
    return {
        "meses": [m for m, _, _ in meses],
        "carteira": serie,
        "terapias_mes": [{"terapia": t, "valores": [v.get(m, 0) for m, _, _ in meses]}
                         for t, v in sorted(ter.items(), key=lambda x: -sum(x[1].values()))],
        "situacao_terapias": _pairs(situacao),
        "profissionais": [{"nome": p["nome"], "total": p["total"], "terapias": " · ".join(sorted(p["terapias"]))} for p in top],
        "indicadores": indicadores,
        "resumo_terapias": {"mes": mes_ref, "mes_ini": m_ini, "mes_fim": m_fim, "terapias": resumo[0], "pacientes": resumo[1], "sessoes": resumo[2], "valor": round(resumo[3] or 0, 2)},
    }


def pendencias_detalhe(terapia: str, ini_text: str | None = None, fim_text: str | None = None,
                       profissional: str | None = None) -> list[dict]:
    """Terapias pendentes de uma terapia, ou todas as terapias de um profissional no período."""
    hoje = date.today()
    fim = _parse(fim_text, hoje)
    ini = _parse(ini_text, fim) if ini_text else None
    if ini and ini > fim:
        ini, fim = fim, ini
    mes_de, mes_ate = (ini.strftime("%Y-%m"), fim.strftime("%Y-%m")) if ini else (hoje.strftime("%Y-%m"),) * 2
    if profissional:
        where, args = "t.profissional = ?", [profissional]
    else:
        where = "t.terapia = ? AND t.situacao = 'Pendente' AND (p.data_alta IS NULL OR p.data_alta = '')"
        args = [terapia]
    with connect() as conn:
        rows = conn.execute(
            "SELECT t.mes, t.codigo_paciente, p.nome, t.terapia, t.modalidade, t.empresa, t.profissional, t.situacao, p.bairro, p.cidade "
            "FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente "
            f"WHERE t.mes BETWEEN ? AND ? AND {where} ORDER BY t.mes DESC, p.nome",
            (mes_de, mes_ate, *args),
        ).fetchall()
        return [dict(zip(("mes", "codigo", "paciente", "terapia", "modalidade", "empresa", "profissional", "situacao", "bairro", "cidade"), r)) for r in rows]


def _meses_periodo(ini_text: str | None, fim_text: str | None) -> tuple[str, str]:
    hoje = date.today()
    fim = _parse(fim_text, hoje)
    ini = _parse(ini_text, fim) if ini_text else None
    if ini and ini > fim:
        ini, fim = fim, ini
    return (ini.strftime("%Y-%m"), fim.strftime("%Y-%m")) if ini else (hoje.strftime("%Y-%m"),) * 2


def faltas_detalhe(tipo: str, ini_text: str | None = None, fim_text: str | None = None,
                   filtro_tipo: str | None = None, filtro_valor: str | None = None) -> dict:
    """Itens que faltam para fechar 100% em cada indicador (terapias não ativas, sem agendamento, sem relatório, cadastro incompleto)."""
    mes_de, mes_ate = _meses_periodo(ini_text, fim_text)
    with connect() as conn:
        if tipo == "cadastro":
            sql_f, args_f = _filtro_sql(filtro_tipo, filtro_valor)
            rows = conn.execute(
                f"SELECT codigo, nome, nascimento, complexidade, diagnostico FROM pacientes WHERE {ATIVO} "
                "AND (COALESCE(nascimento, '') = '' OR COALESCE(complexidade, '') = '' OR COALESCE(diagnostico, '') = '')" +
                sql_f + " ORDER BY nome", args_f).fetchall()
            linhas = []
            for codigo, nome, nasc, cx, diag in rows:
                falta = [n for n, v in (("Nascimento", nasc), ("Complexidade", cx), ("Diagnóstico", diag)) if not v]
                linhas.append([codigo, nome, ", ".join(falta)])
            return {"colunas": ["Código", "Paciente", "Falta preencher"], "linhas": linhas}
        cond = {
            "ativas": "COALESCE(t.situacao, '') <> 'Ativa'",
            "agendadas": "COALESCE(t.agendado, '') <> 'Sim'",
            "relatorios": "COALESCE(t.relatorio, '') <> 'Sim'",
        }.get(tipo)
        if not cond:
            return {"colunas": [], "linhas": []}
        sql_f, args_f = _filtro_terapia_sql(filtro_tipo, filtro_valor)
        rows = conn.execute(
            "SELECT t.mes, t.codigo_paciente, p.nome, t.terapia, t.empresa, t.profissional, t.situacao, t.agendado, t.relatorio "
            "FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente "
            f"WHERE t.mes BETWEEN ? AND ? AND {cond}" + sql_f + " ORDER BY t.mes DESC, p.nome",
            (mes_de, mes_ate, *args_f)).fetchall()
        return {
            "colunas": ["Mês", "Código", "Paciente", "Terapia", "Empresa", "Profissional", "Situação", "Agendado", "Relatório"],
            "linhas": [list(r) for r in rows],
        }


def dashboard(ref_text: str | None, periodo_motivos: str, ini_text: str | None = None,
              fim_text: str | None = None, filtro_tipo: str | None = None,
              filtro_valor: str | None = None) -> dict:
    hoje = date.today()
    ref = _parse(fim_text or ref_text, hoje)
    ini = _parse(ini_text, ref) if ini_text else None
    if ini and ini > ref:
        ini, ref = ref, ini
    periodos = _periodos(ref)
    with connect() as conn:
        filtro = (filtro_tipo, filtro_valor)

        def contar(evento: str) -> dict:
            return {
                k: conn.execute(
                    "SELECT COUNT(*) FROM movimentacao m JOIN pacientes p ON p.codigo = m.codigo_paciente "
                    "WHERE m.evento = ? AND m.data BETWEEN ? AND ?" +
                    _filtro_sql(filtro_tipo, filtro_valor, "p")[0],
                    (evento, a, b, *_filtro_sql(filtro_tipo, filtro_valor, "p")[1])
                ).fetchone()[0]
                for k, (a, b) in periodos.items()
            }

        ini_m, fim_m = (ini.isoformat(), ref.isoformat()) if ini else periodos.get(periodo_motivos, periodos["mes"])
        motivos = conn.execute(
            "SELECT m, COUNT(*) AS t FROM (SELECT COALESCE(NULLIF(m.motivo, ''), 'Não informado') AS m "
            "FROM movimentacao m JOIN pacientes p ON p.codigo = m.codigo_paciente "
            "WHERE m.evento IN ('Alta', 'Óbito') AND m.data BETWEEN ? AND ?" +
            _filtro_sql(filtro_tipo, filtro_valor, "p")[0] +
            ") x GROUP BY m ORDER BY t DESC LIMIT 8",
            (ini_m, fim_m, *_filtro_sql(filtro_tipo, filtro_valor, "p")[1]),
        ).fetchall()

        mes_atual = hoje.strftime("%Y-%m")
        mes_de, mes_ate = (ini.strftime("%Y-%m"), ref.strftime("%Y-%m")) if ini else (mes_atual, mes_atual)
        pendencias = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT t.terapia, COUNT(*) FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente "
                "WHERE t.mes BETWEEN ? AND ? AND t.situacao = 'Pendente' AND (p.data_alta IS NULL OR p.data_alta = '') " +
                _filtro_terapia_sql(filtro_tipo, filtro_valor)[0] +
                "GROUP BY t.terapia",
                (mes_de, mes_ate, *_filtro_terapia_sql(filtro_tipo, filtro_valor)[1]),
            )
        }
        terapias = [r[0] for r in conn.execute("SELECT valor FROM opcoes WHERE lista = 'terapias' ORDER BY id")]

        def grupo(coluna: str, limite: int | None = None) -> list[dict]:
            sql = (
                f"SELECT {coluna}, COUNT(*) AS t FROM pacientes WHERE {ATIVO}" +
                _filtro_sql(filtro_tipo, filtro_valor)[0] + f" GROUP BY {coluna} ORDER BY t DESC"
                + (f" LIMIT {limite}" if limite else "")
            )
            return _pairs(conn.execute(sql, _filtro_sql(filtro_tipo, filtro_valor)[1]).fetchall())

        complexidade = grupo("complexidade")
        total_cx = sum(i["total"] for i in complexidade)
        for item in complexidade:
            item["pct"] = round(item["total"] * 100 / total_cx, 1) if total_cx else 0

        nascimentos = [r[0] for r in conn.execute(
            f"SELECT nascimento FROM pacientes WHERE {ATIVO}" + _filtro_sql(filtro_tipo, filtro_valor)[0],
            _filtro_sql(filtro_tipo, filtro_valor)[1])]
        idades = []
        for n in nascimentos:
            try:
                b = datetime.strptime(n or "", "%Y-%m-%d").date()
            except ValueError:
                continue
            idades.append(hoje.year - b.year - ((hoje.month, hoje.day) < (b.month, b.day)))
        faixas = Counter()
        for i in idades:
            for nome, a, b in FAIXAS:
                if a <= i <= b:
                    faixas[nome] += 1

        servico_operadora = conn.execute(
            f"SELECT s, o, COUNT(*) AS t FROM (SELECT COALESCE(NULLIF(servico,''),'Não informado') AS s, "
            f"COALESCE(NULLIF(operadora,''),'Não informada') AS o FROM pacientes WHERE {ATIVO}" +
            _filtro_sql(filtro_tipo, filtro_valor)[0] + ") x GROUP BY s, o ORDER BY t DESC"
            , _filtro_sql(filtro_tipo, filtro_valor)[1]).fetchall()

        return {
            "referencia": ref.isoformat(),
            "ativos": conn.execute(f"SELECT COUNT(*) FROM pacientes WHERE {ATIVO}" + _filtro_sql(filtro_tipo, filtro_valor)[0],
                                   _filtro_sql(filtro_tipo, filtro_valor)[1]).fetchone()[0],
            "altas": contar("Alta"),
            "admissoes": contar("Admissão"),
            "obitos": contar("Óbito"),
            "motivos": {"periodo": periodo_motivos, "dados": _pairs(motivos)},
            "pendencias": [{"label": t, "total": pendencias.get(t, 0)} for t in terapias],
            "mortalidade": {
                "mes": _taxa_mortalidade(conn, *periodos["mes"], filtro),
                "ano": _taxa_mortalidade(conn, *periodos["ano"], filtro),
            },
            "bairros": grupo("bairro", 15),
            "cidades": grupo("cidade", 15),
            "complexidade": complexidade,
            "idade": {
                "media": round(sum(idades) / len(idades), 1) if idades else 0,
                "faixas": [{"label": n, "total": faixas.get(n, 0)} for n, _, _ in FAIXAS],
            },
            "diagnosticos": grupo("diagnostico", 15),
            "servicos": grupo("servico"),
            "operadoras": grupo("operadora"),
            "servico_operadora": [{"servico": s, "operadora": o, "total": t} for s, o, t in servico_operadora],
            "evolucao": _evolucao(conn, ref, ini, filtro),
            "periodo": _periodo(conn, ini or ref.replace(day=1), ref, filtro),
        }
