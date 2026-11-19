"""Espelho local da URL Saúde Residence (dadosbi).

A URL da equipe de dados do cliente é a ÚNICA fonte de informação do sistema. Este módulo baixa a
resposta, valida, grava atendimentos e visitas nas tabelas `dadosbi_*` e registra o resultado. A rotina
automática roda na inicialização e a cada hora; o Admin pode disparar manualmente.

Registros que somem da resposta não são apagados (proteção contra respostas parciais da URL).
"""
from __future__ import annotations

import json
import os
import threading
import urllib.request
from datetime import datetime
from urllib.error import HTTPError, URLError

from . import config
from .db import connect

LIMITE_RESPOSTA = 25_000_000
LIMITE_REGISTROS = 20_000
LIMITE_VISITAS = 100_000
LIMITE_RELATORIOS = 100_000
INTERVALO = 60 * 60
CATEGORIAS_MONITORADAS = {"status", "nmservico", "possuiterapias", "idoperadora", "nmoperadora"}

_trava_execucao = threading.Lock()


class SemUrl(RuntimeError):
    """A URL ainda não foi configurada neste computador."""
_trava_agenda = threading.Lock()
_agenda_iniciada = False


def url() -> str:
    """URL da Saúde Residence: variável de ambiente TST_DADOSBI_URL ou a configurada na tela de Integração."""
    return (os.environ.get("TST_DADOSBI_URL") or config.ler().get("url_dadosbi") or "").strip()


# ---------------------------------------------------------------- normalização dos campos
def _data(valor) -> str | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Data inválida na resposta da URL.")


def _texto(registro: dict, campo: str, limite: int) -> str | None:
    valor = registro.get(campo)
    if valor is None:
        return None
    if isinstance(valor, (dict, list, bool)):
        raise ValueError(f"Campo {campo} inválido na resposta da URL.")
    texto = str(valor).strip()
    if len(texto) > limite:
        raise ValueError(f"Campo {campo} excede o tamanho permitido.")
    return texto or None


def _relatorios_pendentes(valor, atendimento_id: str) -> list[dict]:
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise ValueError("Lista de relatórios pendentes inválida.")
    relatorios = []
    for item in valor:
        if not isinstance(item, dict):
            raise ValueError("Relatório pendente inválido.")
        vinculo = _texto(item, "idadmission", 40)
        if vinculo and vinculo != atendimento_id:
            raise ValueError("Relatório pendente vinculado a outro atendimento.")
        relatorios.append({
            "id": _texto(item, "id", 40),
            "profissional_id": _texto(item, "idprofessional", 40),
            "especialidade_id": _texto(item, "idespecialidade", 40),
            "profissional": _texto(item, "nmprofessional", 200),
            "especialidade": _texto(item, "nmespecialidade", 200),
            "competencia": _texto(item, "competencia", 30),
        })
    return relatorios


def _campos_atendimento(registro: dict, agora: str) -> tuple[str, tuple]:
    if registro.get("id") in (None, "") or not str(registro.get("nmpaciente") or "").strip():
        raise ValueError("Atendimento sem identificador ou nome do paciente.")
    origem_id = str(registro["id"]).strip()
    nome = str(registro["nmpaciente"]).strip()
    if len(origem_id) > 40 or len(nome) > 200:
        raise ValueError("Identificador ou nome excede o tamanho permitido.")
    txt = lambda campo: str(registro.get(campo) or "").strip() or None  # noqa: E731
    return origem_id, (
        nome, txt("idoperadora"), txt("nmoperadora"), txt("nmservico"), txt("status"),
        _data(registro.get("dataadmissao")), _data(registro.get("dataalta")), txt("condicaoalta"),
        txt("possuiterapias"), _data(registro.get("datainicioorcamento")), _data(registro.get("datafimorcamento")),
        _texto(registro, "idade", 10), _texto(registro, "diagnostico", 200), _texto(registro, "complexidade", 120),
        _texto(registro, "cidade", 120), _texto(registro, "bairro", 120),
        json.dumps(_relatorios_pendentes(registro.get("relatoriospendentes"), origem_id), ensure_ascii=False),
        *_zoneamento(registro.get("zoneamento")),
        agora,
    )


def _zoneamento(valor) -> tuple[str | None, str | None, str | None]:
    """Zona de atendimento do cliente (desde 18/11/2026): id, nome e a lista de bairros que ela cobre."""
    if not isinstance(valor, dict):
        return None, None, None
    return _texto(valor, "id", 40), _texto(valor, "nome", 120), _texto(valor, "bairros", 4000)


def _campos_visita(visita, atendimento_id: str, agora: str) -> tuple[str, tuple]:
    if not isinstance(visita, dict) or visita.get("id") in (None, ""):
        raise ValueError("Visita sem identificador.")
    origem_id = str(visita["id"]).strip()
    data = _data(visita.get("datavisita"))
    if not data or len(origem_id) > 40 or str(visita.get("idadmission") or "").strip() != atendimento_id:
        raise ValueError("Vínculo ou data da visita inválidos.")
    txt = lambda campo: str(visita.get(campo) or "").strip() or None  # noqa: E731
    return origem_id, (atendimento_id, txt("idprofessional"), txt("nmprofessional"), txt("nmespecialidade"), data, agora)


# ---------------------------------------------------------------- monitor de estrutura da resposta
def _tipo_json(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "boolean"
    if isinstance(valor, (int, float)):
        return "number"
    return {str: "string", dict: "object", list: "array"}.get(type(valor), "unknown")


def _esquema_e_categorias(payload) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    tipos: dict[str, set[str]] = {}
    categorias: dict[str, set[str]] = {}

    def percorrer(valor, caminho: str) -> None:
        tipos.setdefault(caminho, set()).add(_tipo_json(valor))
        if isinstance(valor, dict):
            for chave, item in valor.items():
                nome = str(chave)
                filho = f"{caminho}.{nome}" if caminho else nome
                if nome in CATEGORIAS_MONITORADAS and isinstance(item, (str, int, float)) and not isinstance(item, bool):
                    categoria = str(item).strip()
                    if categoria and len(categoria) <= 120:
                        categorias.setdefault(filho, set()).add(categoria)
                percorrer(item, filho)
        elif isinstance(valor, list):
            for item in valor:
                percorrer(item, f"{caminho}[]")

    percorrer(payload, "")
    return (
        {c: sorted(ts) for c, ts in sorted(tipos.items())},
        {c: sorted(vs, key=str.casefold) for c, vs in sorted(categorias.items())},
    )


def monitorar_esquema(payload) -> list[dict]:
    """Compara campos/tipos e categorias com as respostas anteriores (sem guardar dados de pacientes)."""
    esquema, categorias = _esquema_e_categorias(payload)
    agora = datetime.now().isoformat(timespec="seconds")
    alertas: list[dict] = []
    with connect() as conn:
        anterior = conn.execute("SELECT * FROM dadosbi_monitor ORDER BY id").fetchone()
        if anterior:
            esquema_ant = json.loads(anterior["estrutura_json"] or "{}")
            categorias_ant = json.loads(anterior["categorias_json"] or "{}")
            for campo, tipos in esquema.items():
                if campo not in esquema_ant:
                    alertas.append({"tipo": "campo_novo", "campo": campo, "detalhe": f"Novo campo na resposta ({', '.join(tipos)})."})
                    continue
                novos = sorted(set(tipos) - set(esquema_ant[campo]))
                if novos:
                    alertas.append({"tipo": "tipo_novo", "campo": campo,
                                    "detalhe": f"Novo tipo de valor: {', '.join(novos)}; tipos já vistos: {', '.join(esquema_ant[campo])}."})
            for campo, valores in categorias.items():
                for valor in sorted(set(valores) - set(categorias_ant.get(campo, [])), key=str.casefold):
                    alertas.append({"tipo": "categoria_nova", "campo": campo, "detalhe": f"Nova categoria: {valor[:120]}"})
            conn.execute(
                "UPDATE dadosbi_monitor SET estrutura_json=?, categorias_json=?, campos_monitorados=?, ultima_verificacao=? WHERE id=?",
                (json.dumps(esquema, ensure_ascii=False), json.dumps(categorias, ensure_ascii=False), len(esquema), agora, anterior["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO dadosbi_monitor (estrutura_json, categorias_json, campos_monitorados, ultima_verificacao) VALUES (?,?,?,?)",
                (json.dumps(esquema, ensure_ascii=False), json.dumps(categorias, ensure_ascii=False), len(esquema), agora),
            )
        for alerta in alertas:
            conn.execute("INSERT INTO dadosbi_alertas (tipo, campo, detalhe, criado_em) VALUES (?,?,?,?)",
                         (alerta["tipo"], alerta["campo"][:300], alerta["detalhe"][:1000], agora))
        conn.execute(
            "DELETE FROM dadosbi_alertas WHERE reconhecido_em IS NOT NULL AND id NOT IN "
            "(SELECT id FROM dadosbi_alertas WHERE reconhecido_em IS NOT NULL ORDER BY id DESC LIMIT 200)"
        )
    return alertas


def monitor() -> dict:
    with connect() as conn:
        m = conn.execute("SELECT * FROM dadosbi_monitor ORDER BY id").fetchone()
        alertas = [dict(r) for r in conn.execute(
            "SELECT id, tipo, campo, detalhe, criado_em, reconhecido_em FROM dadosbi_alertas WHERE reconhecido_em IS NULL "
            "OR id IN (SELECT id FROM dadosbi_alertas WHERE reconhecido_em IS NOT NULL ORDER BY id DESC LIMIT 50) ORDER BY id DESC")]
        pendentes = conn.execute("SELECT COUNT(*) FROM dadosbi_alertas WHERE reconhecido_em IS NULL").fetchone()[0]
    return {"ultima_verificacao": m["ultima_verificacao"] if m else None,
            "campos_monitorados": m["campos_monitorados"] if m else 0,
            "alertas_pendentes": pendentes, "alertas": alertas}


def reconhecer_alerta(alerta_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute("UPDATE dadosbi_alertas SET reconhecido_em=? WHERE id=? AND reconhecido_em IS NULL",
                           (datetime.now().isoformat(timespec="seconds"), alerta_id))
    return cur.rowcount > 0


# ---------------------------------------------------------------- status
def status() -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM dadosbi_status ORDER BY id").fetchone()
        if not row:
            return None
        d = dict(row)
        d["atendimentos"] = conn.execute("SELECT COUNT(*) FROM dadosbi_atendimentos").fetchone()[0]
        d["visitas"] = conn.execute("SELECT COUNT(*) FROM dadosbi_visitas_origem").fetchone()[0]
    d["intervalo_min"] = INTERVALO // 60
    return d


def _salvar_status(s: dict) -> None:
    valores = (s.get("ultima_execucao"), s.get("ultima_sucesso"), s.get("status"), s.get("erro"),
               s.get("atendimentos_criados"), s.get("atendimentos_atualizados"), s.get("visitas_criadas"), s.get("visitas_atualizadas"))
    with connect() as conn:
        atual = conn.execute("SELECT id FROM dadosbi_status ORDER BY id").fetchone()
        if atual:
            conn.execute("UPDATE dadosbi_status SET ultima_execucao=?, ultima_sucesso=?, status=?, erro=?, atendimentos_criados=?, "
                         "atendimentos_atualizados=?, visitas_criadas=?, visitas_atualizadas=? WHERE id=?", (*valores, atual["id"]))
        else:
            conn.execute("INSERT INTO dadosbi_status (ultima_execucao, ultima_sucesso, status, erro, atendimentos_criados, "
                         "atendimentos_atualizados, visitas_criadas, visitas_atualizadas) VALUES (?,?,?,?,?,?,?,?)", valores)


# ---------------------------------------------------------------- sincronização
COLS_ATEND = ("nome_paciente, operadora_id, operadora, servico, status_origem, data_admissao, data_alta, condicao_alta, "
              "possui_terapias, inicio_orcamento, fim_orcamento, idade, diagnostico, complexidade, cidade, bairro, "
              "relatorios_pendentes_json, zona_id, zona_nome, zona_bairros, sincronizado_em")
COLS_VISITA = "atendimento_origem_id, profissional_id, profissional, especialidade, data_visita, sincronizado_em"


def _upsert(conn, tabela: str, colunas: str, linhas: dict[str, tuple]) -> tuple[int, int]:
    """Insere/atualiza em lote pelo `origem_id`. Retorna (criados, atualizados)."""
    existentes = {r[0] for r in conn.execute(f"SELECT origem_id FROM {tabela}")}
    nomes = [c.strip() for c in colunas.split(",")]
    novos = [(*v, k) for k, v in linhas.items() if k not in existentes]
    alterados = [(*v, k) for k, v in linhas.items() if k in existentes]
    if novos:
        conn.executemany(f"INSERT INTO {tabela} ({colunas}, origem_id) VALUES ({','.join('?' * (len(nomes) + 1))})", novos)
    if alterados:
        conn.executemany(f"UPDATE {tabela} SET {', '.join(n + '=?' for n in nomes)} WHERE origem_id=?", alterados)
    return len(novos), len(alterados)


def _baixar() -> object:
    if not url():
        raise SemUrl("A URL da Saúde Residence ainda não foi configurada (Integração com a URL).")
    req = urllib.request.Request(url(), headers={"Accept": "application/json", "User-Agent": "TST-GESTAO/2"})
    with urllib.request.urlopen(req, timeout=60) as resposta:
        bruto = resposta.read(LIMITE_RESPOSTA + 1)
    if len(bruto) > LIMITE_RESPOSTA:
        raise ValueError("Resposta da URL excede o limite permitido.")
    return json.loads(bruto.decode("utf-8-sig"))


def _sincronizar() -> dict:
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        payload = _baixar()
        alertas = monitorar_esquema(payload)
        registros = payload.get("dados") if isinstance(payload, dict) and payload.get("sucesso") is True else None
        if not isinstance(registros, list):
            raise ValueError("Formato de resposta não reconhecido.")
        if len(registros) > LIMITE_REGISTROS:
            raise ValueError("Quantidade de registros excede o limite permitido.")
        registros = [r for r in registros if isinstance(r, dict)]
        if sum(len(r.get("visitas") or []) for r in registros if isinstance(r.get("visitas") or [], list)) > LIMITE_VISITAS:
            raise ValueError("Quantidade de visitas excede o limite permitido.")
        if sum(len(r.get("relatoriospendentes") or []) for r in registros
               if isinstance(r.get("relatoriospendentes") or [], list)) > LIMITE_RELATORIOS:
            raise ValueError("Quantidade de relatórios pendentes excede o limite permitido.")

        erros = 0
        atendimentos: dict[str, tuple] = {}
        visitas: dict[str, tuple] = {}
        for registro in registros:
            try:
                origem_id, campos = _campos_atendimento(registro, agora)
            except (TypeError, ValueError):
                erros += 1
                continue
            atendimentos[origem_id] = campos
            lista = registro.get("visitas") or []
            if not isinstance(lista, list):
                erros += 1
                continue
            for visita in lista:
                try:
                    vid, vcampos = _campos_visita(visita, origem_id, agora)
                    visitas[vid] = vcampos
                except (TypeError, ValueError):
                    erros += 1

        with connect() as conn:
            a_criados, a_atualizados = _upsert(conn, "dadosbi_atendimentos", COLS_ATEND, atendimentos)
            v_criadas, v_atualizadas = _upsert(conn, "dadosbi_visitas_origem", COLS_VISITA, visitas)

        resultado = {
            "ultima_execucao": agora, "ultima_sucesso": agora, "status": "sucesso" if not erros else "parcial",
            "atendimentos_criados": a_criados, "atendimentos_atualizados": a_atualizados,
            "visitas_criadas": v_criadas, "visitas_atualizadas": v_atualizadas,
            "alertas_esquema": len(alertas), "erro": f"{erros} registro(s) inválido(s) ignorado(s)." if erros else None,
        }
        _salvar_status(resultado)
        return resultado
    except Exception as exc:
        if isinstance(exc, SemUrl):
            erro = str(exc)
        elif isinstance(exc, HTTPError):
            erro = f"A URL retornou HTTP {exc.code}."
        elif isinstance(exc, URLError):
            erro = "Não foi possível conectar à URL."
        elif isinstance(exc, ValueError):
            erro = "Resposta da URL inválida ou fora do formato esperado."
        else:
            erro = "Falha ao sincronizar os dados da URL."
        anterior = status() or {}
        _salvar_status({"ultima_execucao": agora, "ultima_sucesso": anterior.get("ultima_sucesso"), "status": "erro",
                        "atendimentos_criados": 0, "atendimentos_atualizados": 0, "visitas_criadas": 0,
                        "visitas_atualizadas": 0, "erro": erro})
        raise RuntimeError(erro) from exc


def sincronizar() -> dict:
    if not _trava_execucao.acquire(blocking=False):
        raise RuntimeError("Já existe uma sincronização em andamento.")
    try:
        return _sincronizar()
    finally:
        _trava_execucao.release()


def iniciar_agendamento(logger) -> None:
    """Sincroniza ao iniciar e depois a cada INTERVALO segundos (uma única rotina por processo)."""
    global _agenda_iniciada
    with _trava_agenda:
        if _agenda_iniciada:
            return
        _agenda_iniciada = True

    def executar() -> None:
        espera = threading.Event()
        while True:
            try:
                sincronizar()
            except Exception:
                logger.exception("Falha na sincronização automática com a URL Saúde Residence.")
            espera.wait(INTERVALO)

    threading.Thread(target=executar, name="espelho-url", daemon=True).start()
