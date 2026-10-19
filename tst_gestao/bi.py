from __future__ import annotations

from collections import Counter
from datetime import date, datetime

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


def _taxa_mortalidade(conn, inicio: str, fim: str) -> dict:
    obitos = conn.execute(
        "SELECT COUNT(*) FROM movimentacao WHERE evento = 'Óbito' AND data BETWEEN ? AND ?", (inicio, fim)
    ).fetchone()[0]
    expostos = conn.execute(
        "SELECT COUNT(*) FROM pacientes WHERE data_admissao IS NOT NULL AND data_admissao <> '' "
        "AND data_admissao <= ? AND (data_alta IS NULL OR data_alta = '' OR data_alta >= ?)",
        (fim, inicio),
    ).fetchone()[0]
    return {"obitos": obitos, "base": expostos, "taxa": round(obitos * 100 / expostos, 2) if expostos else 0}


def dashboard(ref_text: str | None, periodo_motivos: str) -> dict:
    hoje = date.today()
    ref = _parse(ref_text, hoje)
    periodos = _periodos(ref)
    with connect() as conn:
        def contar(evento: str) -> dict:
            return {
                k: conn.execute(
                    "SELECT COUNT(*) FROM movimentacao WHERE evento = ? AND data BETWEEN ? AND ?", (evento, a, b)
                ).fetchone()[0]
                for k, (a, b) in periodos.items()
            }

        ini, fim = periodos.get(periodo_motivos, periodos["mes"])
        motivos = conn.execute(
            "SELECT COALESCE(NULLIF(motivo, ''), 'Não informado'), COUNT(*) AS t FROM movimentacao "
            "WHERE evento IN ('Alta', 'Óbito') AND data BETWEEN ? AND ? GROUP BY 1 ORDER BY t DESC LIMIT 8",
            (ini, fim),
        ).fetchall()

        mes_atual = hoje.strftime("%Y-%m")
        pendencias = {
            r[0]: r[1]
            for r in conn.execute(
                "SELECT t.terapia, COUNT(*) FROM terapias t JOIN pacientes p ON p.codigo = t.codigo_paciente "
                "WHERE t.mes = ? AND t.situacao = 'Pendente' AND (p.data_alta IS NULL OR p.data_alta = '') "
                "GROUP BY t.terapia",
                (mes_atual,),
            )
        }
        terapias = [r[0] for r in conn.execute("SELECT valor FROM opcoes WHERE lista = 'terapias' ORDER BY id")]

        def grupo(coluna: str, limite: int | None = None) -> list[dict]:
            sql = (
                f"SELECT {coluna}, COUNT(*) AS t FROM pacientes WHERE {ATIVO} GROUP BY 1 ORDER BY t DESC"
                + (f" LIMIT {limite}" if limite else "")
            )
            return _pairs(conn.execute(sql).fetchall())

        complexidade = grupo("complexidade")
        total_cx = sum(i["total"] for i in complexidade)
        for item in complexidade:
            item["pct"] = round(item["total"] * 100 / total_cx, 1) if total_cx else 0

        nascimentos = [r[0] for r in conn.execute(f"SELECT nascimento FROM pacientes WHERE {ATIVO}")]
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
            f"SELECT COALESCE(NULLIF(servico,''),'Não informado'), COALESCE(NULLIF(operadora,''),'Não informada'), "
            f"COUNT(*) FROM pacientes WHERE {ATIVO} GROUP BY 1, 2 ORDER BY 3 DESC"
        ).fetchall()

        return {
            "referencia": ref.isoformat(),
            "ativos": conn.execute(f"SELECT COUNT(*) FROM pacientes WHERE {ATIVO}").fetchone()[0],
            "altas": contar("Alta"),
            "admissoes": contar("Admissão"),
            "obitos": contar("Óbito"),
            "motivos": {"periodo": periodo_motivos, "dados": _pairs(motivos)},
            "pendencias": [{"label": t, "total": pendencias.get(t, 0)} for t in terapias],
            "mortalidade": {
                "mes": _taxa_mortalidade(conn, *periodos["mes"]),
                "ano": _taxa_mortalidade(conn, *periodos["ano"]),
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
        }
