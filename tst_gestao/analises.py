from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from .db import connect

MIN_MESES, MAX_MESES = 8, 24
LIMITE_DETALHE = 3000
JANELA_TERAPIA = 90
JANELA_ATRASO = 15
SEM_TERAPIA = "Nenhuma terapia (90 d)"
NIVEIS_COMPLEXIDADE = ["Sem terapia", "Básico", "Intermediário", "Intensivo"]
COLS_ATEND = ["Atendimento", "Paciente", "Operadora", "Serviço", "Admissão", "Alta", "Dias", "Visitas no período", "Especialidades (90 d)"]
COLS_VISITA = ["Data", "Atendimento", "Paciente", "Operadora", "Profissional", "Especialidade"]
COLS_PROFISSIONAL = ["Profissional", "Especialidade principal", "Visitas", "Dias com visita", "Atendimentos", "Operadoras"]


def _nivel(qtd_especialidades: int) -> str:
    if qtd_especialidades == 0:
        return NIVEIS_COMPLEXIDADE[0]
    return NIVEIS_COMPLEXIDADE[1 if qtd_especialidades <= 2 else 2 if qtd_especialidades == 3 else 3]


def _obito(a: dict) -> bool:
    return "bito" in (a["condicao_alta"] or "").lower()


def _monitoramento(a: dict) -> bool:
    return (a["servico"] or "").strip().lower().startswith("monitoramento")


def _com_terapias(a: dict) -> bool:
    return (a["possui_terapias"] or "").strip().upper() in ("SIM", "S")


def _especialidades_janela(visitas: list[dict], fim: date) -> dict[str, set[str]]:
    """Especialidades que atenderam cada atendimento nos JANELA_TERAPIA dias até o fim do período."""
    inicio = fim - timedelta(days=JANELA_TERAPIA - 1)
    saida: dict[str, set[str]] = {}
    for v in visitas:
        d = _data(v["data_visita"])
        if d and inicio <= d <= fim:
            saida.setdefault(v["atendimento_origem_id"], set()).add(v["especialidade"] or "Não informada")
    return saida


def _escopo(nome: str, fim: date) -> tuple[date, date]:
    """Dia, mês ou ano corrente em relação à data final do filtro."""
    if nome == "dia":
        return fim, fim
    return (fim.replace(day=1) if nome == "mes" else fim.replace(month=1, day=1)), fim


def _rotulo_escopo(nome: str, fim: date) -> str:
    return {"dia": _br(fim), "mes": f"{fim.month:02d}/{fim.year} até {_br(fim)}", "ano": f"{fim.year} até {_br(fim)}"}[nome]


def _ultima_visita_terapia(visitas: list[dict], fim: date) -> dict[str, dict[str, date]]:
    """Última visita de cada especialidade, por atendimento, nos JANELA_TERAPIA dias até a data final."""
    inicio = fim - timedelta(days=JANELA_TERAPIA - 1)
    saida: dict[str, dict[str, date]] = {}
    for v in visitas:
        d = _data(v["data_visita"])
        if d and inicio <= d <= fim:
            esp = v["especialidade"] or "Não informada"
            atual = saida.setdefault(v["atendimento_origem_id"], {})
            if esp not in atual or d > atual[esp]:
                atual[esp] = d
    return saida


def _atrasados_terapia(ativos: list[dict], ultimas: dict[str, dict[str, date]], fim: date) -> dict[str, list[dict]]:
    """Pacientes ativos com terapias que fizeram a terapia na janela, mas sem visita dela nos últimos JANELA_ATRASO dias."""
    corte = fim - timedelta(days=JANELA_ATRASO - 1)
    saida: dict[str, list[dict]] = {}
    for a in ativos:
        if not _com_terapias(a):
            continue
        for esp, d in ultimas.get(a["origem_id"], {}).items():
            if d < corte:
                saida.setdefault(esp, []).append(a)
    return saida


def _resumo_profissionais(pares: list[tuple[date, dict]], por_id: dict[str, dict]) -> list[list]:
    grupos: dict[str, dict] = {}
    for d, v in pares:
        if not v["profissional"]:
            continue
        g = grupos.setdefault(v["profissional"], {"visitas": 0, "dias": set(), "atend": set(), "esp": Counter(), "ops": set()})
        g["visitas"] += 1
        g["dias"].add(d)
        g["atend"].add(v["atendimento_origem_id"])
        g["esp"][v["especialidade"] or "Não informada"] += 1
        g["ops"].add(por_id.get(v["atendimento_origem_id"], {}).get("operadora") or "Não informada")
    return [[nome, g["esp"].most_common(1)[0][0], g["visitas"], len(g["dias"]), len(g["atend"]), len(g["ops"])]
            for nome, g in sorted(grupos.items(), key=lambda i: -i[1]["visitas"])]


def _data(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _top(contador: Counter, n: int) -> list[dict]:
    return [{"rotulo": k, "valor": v} for k, v in contador.most_common(n)]


def _meses(ini: date, fim: date) -> list[str]:
    """Meses do período; se curto, estende para trás até ter ao menos MIN_MESES (limite MAX_MESES)."""
    total = (fim.year - ini.year) * 12 + fim.month - ini.month + 1
    total = min(max(total, MIN_MESES), MAX_MESES)
    ano, mes, saida = fim.year, fim.month, []
    for _ in range(total):
        saida.append(f"{ano:04d}-{mes:02d}")
        mes -= 1
        if mes == 0:
            ano, mes = ano - 1, 12
    return saida[::-1]


def _carregar():
    with connect() as conn:
        atend = [dict(r) for r in conn.execute(
            "SELECT origem_id, nome_paciente, operadora, servico, status_origem, data_admissao, data_alta, condicao_alta, "
            "possui_terapias FROM dadosbi_atendimentos")]
        visitas = [dict(r) for r in conn.execute(
            "SELECT atendimento_origem_id, profissional, especialidade, data_visita FROM dadosbi_visitas_origem")]
        sync = conn.execute("SELECT MAX(sincronizado_em) AS m FROM dadosbi_atendimentos").fetchone()
    return atend, visitas, sync["m"] if sync else None


def _ativo_em(a: dict, fim: date) -> bool:
    adm, alta = _data(a["data_admissao"]), _data(a["data_alta"])
    if adm and adm > fim:
        return False
    if alta:
        return alta > fim
    return (a["status_origem"] or "").upper() != "ALTA"


def _periodo(ini: date | None, fim: date | None) -> tuple[date, date]:
    fim = fim or date.today()
    ini = ini or fim.replace(day=1)
    return (fim, ini) if ini > fim else (ini, fim)


def gerar(ini: date | None = None, fim: date | None = None) -> dict:
    """Agrega os dados sincronizados da API Saúde Residence BI (atendimentos e visitas) no período."""
    ini, fim = _periodo(ini, fim)
    atend, visitas, sincronizado = _carregar()

    ativos = [a for a in atend if _ativo_em(a, fim)]
    meses = _meses(ini, fim)
    por_mes, esp, prof, visitas_periodo = Counter(), Counter(), Counter(), 0
    com_visita = set()
    for v in visitas:
        d = _data(v["data_visita"])
        if not d or d > fim:
            continue
        por_mes[d.strftime("%Y-%m")] += 1
        if d >= ini:
            visitas_periodo += 1
            com_visita.add(v["atendimento_origem_id"])
            esp[v["especialidade"] or "Não informada"] += 1
            if v["profissional"]:
                prof[v["profissional"]] += 1

    adm_mes, alta_mes, permanencias, condicao = Counter(), Counter(), [], Counter()
    admissoes = altas = 0
    for a in atend:
        da, dl = _data(a["data_admissao"]), _data(a["data_alta"])
        if da:
            adm_mes[da.strftime("%Y-%m")] += 1
            admissoes += ini <= da <= fim
        if dl:
            alta_mes[dl.strftime("%Y-%m")] += 1
            if ini <= dl <= fim:
                altas += 1
                condicao[(a["condicao_alta"] or "Não informada").strip()] += 1
                if da and dl >= da:
                    permanencias.append((dl - da).days)

    sem_visita = [a for a in ativos if a["origem_id"] not in com_visita]
    ativos_dias = [(fim - d).days for a in ativos if (d := _data(a["data_admissao"]))]

    esp_janela = _especialidades_janela(visitas, fim)
    monit_terapias = [a for a in ativos if _monitoramento(a) and _com_terapias(a)]
    pendentes = [a for a in ativos if _com_terapias(a) and not esp_janela.get(a["origem_id"])]
    por_terapia = Counter(e for a in ativos for e in esp_janela.get(a["origem_id"], ()))
    por_nivel = Counter(_nivel(len(esp_janela.get(a["origem_id"], ()))) for a in ativos)
    obitos = sum(1 for a in atend if _obito(a) and (dl := _data(a["data_alta"])) and ini <= dl <= fim)
    atendidos = sum(1 for a in atend if (da := _data(a["data_admissao"])) and da <= fim
                    and (not (dl := _data(a["data_alta"])) or dl >= ini))
    pares_periodo = [(d, v) for v in visitas if (d := _data(v["data_visita"])) and ini <= d <= fim]
    por_id = {a["origem_id"]: a for a in atend}

    dma, motivos = {}, {}
    for nome in ("dia", "mes", "ano"):
        e_ini, e_fim = _escopo(nome, fim)
        altas_e = [a for a in atend if (dl := _data(a["data_alta"])) and e_ini <= dl <= e_fim]
        n_obitos = sum(1 for a in altas_e if _obito(a))
        n_atendidos = sum(1 for a in atend if (da := _data(a["data_admissao"])) and da <= e_fim
                          and (not (dl := _data(a["data_alta"])) or dl >= e_ini))
        dma[nome] = {
            "rotulo": _rotulo_escopo(nome, fim),
            "altas": len(altas_e),
            "admissoes": sum(1 for a in atend if (da := _data(a["data_admissao"])) and e_ini <= da <= e_fim),
            "obitos": n_obitos,
            "atendidos": n_atendidos,
            "mortalidade": round(n_obitos * 100 / n_atendidos, 2) if n_atendidos else 0,
        }
        motivos[nome] = _top(Counter((a["condicao_alta"] or "Não informada").strip() for a in altas_e), 8)
    atrasados = _atrasados_terapia(ativos, _ultima_visita_terapia(visitas, fim), fim)
    pend_terapia = sorted(({"rotulo": e, "valor": len(l)} for e, l in atrasados.items()), key=lambda i: -i["valor"])
    pend_terapia.append({"rotulo": SEM_TERAPIA, "valor": len(pendentes)})
    total_ativos = len(ativos)
    por_bairro = Counter((a.get("bairro") or "").strip().upper() for a in ativos if (a.get("bairro") or "").strip())
    por_cidade = Counter((a.get("cidade") or "").strip() for a in ativos if (a.get("cidade") or "").strip())

    return {
        "bairros": _top(por_bairro, 1000),
        "cidades": _top(por_cidade, 20),
        "sem_localizacao": total_ativos - sum(por_bairro.values()),
        "dma": dma,
        "motivos": motivos,
        "pendencias_terapia": pend_terapia,
        "janela_atraso": JANELA_ATRASO,
        "periodo": {"ini": ini.isoformat(), "fim": fim.isoformat()},
        "atualizado_em": sincronizado,
        "kpis": {
            "atendimentos": len(atend),
            "ativos": len(ativos),
            "admissoes": admissoes,
            "altas": altas,
            "visitas": visitas_periodo,
            "permanencia_media": round(sum(permanencias) / len(permanencias)) if permanencias else 0,
            "tempo_medio_ativos": round(sum(ativos_dias) / len(ativos_dias)) if ativos_dias else 0,
            "ativos_sem_visita": len(sem_visita),
            "visitas_por_ativo": round(visitas_periodo / len(ativos), 1) if ativos else 0,
            "profissionais": len(prof),
            "obitos": obitos,
            "atendidos": atendidos,
            "mortalidade": round(obitos * 100 / atendidos, 2) if atendidos else 0,
            "monitoramento_terapias": len(monit_terapias),
            "monitoramento_ativos": sum(1 for a in ativos if _monitoramento(a)),
            "terapias_pendentes": len(pendentes),
            "com_terapias": sum(1 for a in ativos if _com_terapias(a)),
        },
        "janela_terapia": JANELA_TERAPIA,
        "terapias": _top(por_terapia, 8),
        "complexidade": [{"rotulo": n, "valor": por_nivel[n], "pct": round(por_nivel[n] * 100 / total_ativos, 1) if total_ativos else 0}
                         for n in NIVEIS_COMPLEXIDADE],
        "pendentes_operadora": _top(Counter(a["operadora"] or "Não informada" for a in pendentes), 8),
        "profissionais_atend": [dict(zip(COLS_PROFISSIONAL, r)) for r in _resumo_profissionais(pares_periodo, por_id)[:15]],
        "meses": meses,
        "visitas_mes": [por_mes[m] for m in meses],
        "admissoes_mes": [adm_mes[m] for m in meses],
        "altas_mes": [alta_mes[m] for m in meses],
        "especialidades": _top(esp, 8),
        "profissionais": _top(prof, 10),
        "operadoras_ativos": _top(Counter(a["operadora"] or "Não informada" for a in ativos), 10),
        "servicos_ativos": _top(Counter(a["servico"] or "Não informado" for a in ativos), 8),
        "condicao_alta": _top(condicao, 8),
        "alerta_sem_visita": [
            {"id": a["origem_id"], "operadora": a["operadora"] or "—", "servico": a["servico"] or "—",
             "admissao": a["data_admissao"] or ""}
            for a in sorted(sem_visita, key=lambda x: x["data_admissao"] or "")[:15]
        ],
    }


def detalhe(tipo: str, valor: str | None, ini: date | None = None, fim: date | None = None) -> dict:
    """Registros que compõem cada indicador/gráfico, para o drill-down da página."""
    ini, fim = _periodo(ini, fim)
    valor = valor or ""
    atend, visitas, _ = _carregar()
    por_id = {a["origem_id"]: a for a in atend}
    pares = [(d, v) for v in visitas if (d := _data(v["data_visita"]))]
    no_periodo = [(d, v) for d, v in pares if ini <= d <= fim]
    visitas_atend = Counter(v["atendimento_origem_id"] for _, v in no_periodo)
    ativos = [a for a in atend if _ativo_em(a, fim)]
    esp_janela = _especialidades_janela(visitas, fim)
    rotulo_periodo = f"{_br(ini)} a {_br(fim)}"
    janela = f"últimos {JANELA_TERAPIA} dias até {_br(fim)}"

    def altas_periodo():
        return [a for a in atend if (dl := _data(a["data_alta"])) and ini <= dl <= fim]

    def lin_atend(lista, antigos_primeiro=False):
        lista = sorted(lista, key=lambda a: a["data_admissao"] or "", reverse=not antigos_primeiro)
        saida = []
        for a in lista:
            adm, alta = _data(a["data_admissao"]), _data(a["data_alta"])
            dias = ((alta or fim) - adm).days if adm else ""
            saida.append([a["origem_id"], a["nome_paciente"], a["operadora"] or "—", a["servico"] or "—",
                          _br(adm), _br(alta), dias, visitas_atend.get(a["origem_id"], 0),
                          " · ".join(sorted(esp_janela.get(a["origem_id"], ()))) or "—"])
        return {"colunas": COLS_ATEND, "linhas": saida, "drill": {"tipo": "atendimento", "col": 0}}

    def lin_visitas(lista):
        saida = []
        for d, v in sorted(lista, key=lambda p: p[0], reverse=True):
            a = por_id.get(v["atendimento_origem_id"], {})
            saida.append([_br(d), v["atendimento_origem_id"], a.get("nome_paciente", "—"), a.get("operadora") or "—",
                          v["profissional"] or "—", v["especialidade"] or "—"])
        return {"colunas": COLS_VISITA, "linhas": saida, "drill": {"tipo": "atendimento", "col": 1}}

    def mes_de(campo):
        return [a for a in atend if (d := _data(a[campo])) and d.strftime("%Y-%m") == valor]

    if tipo == "ativos":
        titulo, r = f"Atendimentos ativos em {_br(fim)}", lin_atend(ativos)
    elif tipo == "sem_visita":
        sem = [a for a in ativos if visitas_atend.get(a["origem_id"], 0) == 0]
        titulo, r = f"Ativos sem visita ({rotulo_periodo})", lin_atend(sem, antigos_primeiro=True)
    elif tipo == "admissoes":
        lista = [a for a in atend if (d := _data(a["data_admissao"])) and ini <= d <= fim]
        titulo, r = f"Admissões ({rotulo_periodo})", lin_atend(lista)
    elif tipo == "altas":
        titulo, r = f"Altas ({rotulo_periodo})", lin_atend(altas_periodo())
    elif tipo == "visitas":
        titulo, r = f"Visitas ({rotulo_periodo})", lin_visitas(no_periodo)
    elif tipo == "operadora":
        lista = [a for a in ativos if (a["operadora"] or "Não informada") == valor]
        titulo, r = f"Ativos da operadora {valor}", lin_atend(lista)
    elif tipo == "servico":
        lista = [a for a in ativos if (a["servico"] or "Não informado") == valor]
        titulo, r = f"Ativos no serviço {valor}", lin_atend(lista)
    elif tipo == "condicao":
        lista = [a for a in altas_periodo() if (a["condicao_alta"] or "Não informada").strip() == valor]
        titulo, r = f"Altas — {valor} ({rotulo_periodo})", lin_atend(lista)
    elif tipo == "especialidade":
        lista = [(d, v) for d, v in no_periodo if (v["especialidade"] or "Não informada") == valor]
        titulo, r = f"Visitas de {valor} ({rotulo_periodo})", lin_visitas(lista)
    elif tipo == "profissional":
        lista = [(d, v) for d, v in no_periodo if v["profissional"] == valor]
        titulo, r = f"Visitas de {valor} ({rotulo_periodo})", lin_visitas(lista)
    elif tipo == "mes_visitas":
        lista = [(d, v) for d, v in pares if d.strftime("%Y-%m") == valor]
        titulo, r = f"Visitas em {valor[5:]}/{valor[:4]}", lin_visitas(lista)
    elif tipo == "mes_admissoes":
        titulo, r = f"Admissões em {valor[5:]}/{valor[:4]}", lin_atend(mes_de("data_admissao"))
    elif tipo == "mes_altas":
        titulo, r = f"Altas em {valor[5:]}/{valor[:4]}", lin_atend(mes_de("data_alta"))
    elif tipo == "profissionais":
        titulo = f"Profissionais × atendimentos ({rotulo_periodo})"
        r = {"colunas": COLS_PROFISSIONAL, "linhas": _resumo_profissionais(no_periodo, por_id),
             "drill": {"tipo": "profissional", "col": 0}}
    elif tipo == "obitos":
        lista = [a for a in altas_periodo() if _obito(a)]
        titulo, r = f"Óbitos ({rotulo_periodo})", lin_atend(lista)
    elif tipo == "monit_terapias":
        lista = [a for a in ativos if _monitoramento(a) and _com_terapias(a)]
        titulo, r = f"Ativos de monitoramento com terapias em {_br(fim)}", lin_atend(lista)
    elif tipo == "pendentes":
        lista = [a for a in ativos if _com_terapias(a) and not esp_janela.get(a["origem_id"])
                 and (not valor or (a["operadora"] or "Não informada") == valor)]
        titulo = f"Terapias pendentes{f' — {valor}' if valor else ''}: ativos com terapias sem visita nos {janela}"
        r = lin_atend(lista)
    elif tipo == "terapia":
        lista = [a for a in ativos if valor in esp_janela.get(a["origem_id"], ())]
        titulo, r = f"Pacientes ativos em {valor} ({janela})", lin_atend(lista)
    elif tipo == "complexidade":
        lista = [a for a in ativos if _nivel(len(esp_janela.get(a["origem_id"], ()))) == valor]
        titulo, r = f"Complexidade {valor} — ativos por nº de especialidades ({janela})", lin_atend(lista)
    elif tipo in ("dma_altas", "dma_admissoes", "dma_obitos"):
        e_ini, e_fim = _escopo(valor, fim)
        if tipo == "dma_admissoes":
            lista = [a for a in atend if (d := _data(a["data_admissao"])) and e_ini <= d <= e_fim]
            nome = "Admissões"
        else:
            lista = [a for a in atend if (d := _data(a["data_alta"])) and e_ini <= d <= e_fim
                     and (tipo == "dma_altas" or _obito(a))]
            nome = "Altas" if tipo == "dma_altas" else "Óbitos"
        titulo, r = f"{nome} ({_rotulo_escopo(valor, fim)})", lin_atend(lista)
    elif tipo == "motivo":
        escopo, _, motivo = valor.partition("|")
        e_ini, e_fim = _escopo(escopo, fim)
        lista = [a for a in atend if (d := _data(a["data_alta"])) and e_ini <= d <= e_fim
                 and (a["condicao_alta"] or "Não informada").strip() == motivo]
        titulo, r = f"Altas — {motivo} ({_rotulo_escopo(escopo, fim)})", lin_atend(lista)
    elif tipo == "atraso":
        if valor == SEM_TERAPIA:
            lista = [a for a in ativos if _com_terapias(a) and not esp_janela.get(a["origem_id"])]
            titulo = f"Com terapias e sem nenhuma visita nos {janela}"
        else:
            lista = _atrasados_terapia(ativos, _ultima_visita_terapia(visitas, fim), fim).get(valor, [])
            titulo = f"{valor}: com terapias, atendidos nos {janela} e sem visita nos últimos {JANELA_ATRASO} dias"
        r = lin_atend(lista)
    elif tipo in ("bairro", "cidade"):
        campo = tipo
        lista = [a for a in ativos if (a.get(campo) or "").strip().upper() == valor.upper()]
        titulo, r = f"Ativos — {tipo} {valor}", lin_atend(lista)
    elif tipo == "atendimento":
        a = por_id.get(valor)
        if not a:
            raise ValueError("Atendimento não encontrado.")
        titulo = f"Histórico de visitas — atendimento {valor} ({a['nome_paciente']})"
        r = lin_visitas([(d, v) for d, v in pares if v["atendimento_origem_id"] == valor])
        r["drill"] = None
    else:
        raise ValueError("Detalhamento desconhecido.")

    total = len(r["linhas"])
    return {"titulo": titulo, "colunas": r["colunas"], "linhas": r["linhas"][:LIMITE_DETALHE], "drill": r["drill"],
            "total": total, "truncado": total > LIMITE_DETALHE}
