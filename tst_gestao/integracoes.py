"""Apoio às integrações: chaves de API, webhooks e leitura de planilhas."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import threading
import unicodedata
import urllib.request
from datetime import date, datetime
from urllib.error import HTTPError, URLError

from .db import connect

EVENTOS_WEBHOOK = [
    "paciente.criado",
    "paciente.atualizado",
    "terapia.criada",
    "terapia.atualizada",
    "movimentacao.criada",
    "dadosbi.esquema_alterado",
]
LIMITE_LINHAS = 5000
DADOSBI_URL_PADRAO = "http://35.247.217.138:8081/SaudeResidenceHomeCareServices/ultron/dadosbi/lista/dadospaciente"
DADOSBI_LIMITE_RESPOSTA = 25_000_000
DADOSBI_LIMITE_REGISTROS = 20_000
DADOSBI_LIMITE_VISITAS = 100_000
DADOSBI_LIMITE_RELATORIOS = 100_000
DADOSBI_INTERVALO = 60 * 60
DADOSBI_CATEGORIAS_MONITORADAS = {"status", "nmservico", "possuiterapias", "idoperadora", "nmoperadora"}
_dadosbi_trava = threading.Lock()
_dadosbi_execucao_trava = threading.Lock()
_dadosbi_thread_iniciada = False


def url_dadosbi() -> str:
    return os.environ.get("TST_DADOSBI_URL", DADOSBI_URL_PADRAO).strip()


def _data_dadosbi(valor) -> str | None:
    texto = str(valor or "").strip()
    if not texto:
        return None
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Data inválida na resposta da API.")


def _texto_dadosbi(registro: dict, campo: str, limite: int) -> str | None:
    valor = registro.get(campo)
    if valor is None:
        return None
    if isinstance(valor, (dict, list, bool)):
        raise ValueError(f"Campo {campo} inválido na resposta da API.")
    texto = str(valor).strip()
    if len(texto) > limite:
        raise ValueError(f"Campo {campo} excede o tamanho permitido.")
    return texto or None


def _relatorios_pendentes_dadosbi(valor, atendimento_id: str) -> list[dict]:
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise ValueError("Lista de relatórios pendentes inválida.")
    relatorios = []
    for item in valor:
        if not isinstance(item, dict):
            raise ValueError("Relatório pendente inválido.")
        vinculo = _texto_dadosbi(item, "idadmission", 40)
        if vinculo and vinculo != atendimento_id:
            raise ValueError("Relatório pendente vinculado a outro atendimento.")
        relatorios.append({
            "id": _texto_dadosbi(item, "id", 40),
            "profissional_id": _texto_dadosbi(item, "idprofessional", 40),
            "especialidade_id": _texto_dadosbi(item, "idespecialidade", 40),
            "profissional": _texto_dadosbi(item, "nmprofessional", 200),
            "especialidade": _texto_dadosbi(item, "nmespecialidade", 200),
            "competencia": _texto_dadosbi(item, "competencia", 30),
        })
    return relatorios


def _salvar_status_dadosbi(status: dict) -> None:
    with connect() as conn:
        atual = conn.execute("SELECT id FROM dadosbi_status ORDER BY id").fetchone()
        valores = (
            status.get("ultima_execucao"), status.get("ultima_sucesso"), status.get("status"),
            status.get("erro"), status.get("atendimentos_criados"), status.get("atendimentos_atualizados"),
            status.get("visitas_criadas"), status.get("visitas_atualizadas"),
        )
        if atual:
            conn.execute(
                "UPDATE dadosbi_status SET ultima_execucao=?, ultima_sucesso=?, status=?, erro=?, "
                "atendimentos_criados=?, atendimentos_atualizados=?, visitas_criadas=?, visitas_atualizadas=? WHERE id=?",
                (*valores, atual["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO dadosbi_status (ultima_execucao, ultima_sucesso, status, erro, atendimentos_criados, "
                "atendimentos_atualizados, visitas_criadas, visitas_atualizadas) VALUES (?,?,?,?,?,?,?,?)", valores)


def status_dadosbi() -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM dadosbi_status ORDER BY id").fetchone()
    return dict(row) if row else None


def _tipo_json(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "boolean"
    if isinstance(valor, (int, float)):
        return "number"
    if isinstance(valor, str):
        return "string"
    if isinstance(valor, dict):
        return "object"
    if isinstance(valor, list):
        return "array"
    return "unknown"


def _esquema_e_categorias(payload) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    tipos: dict[str, set[str]] = {}
    categorias: dict[str, set[str]] = {}

    def percorrer(valor, caminho: str) -> None:
        tipos.setdefault(caminho, set()).add(_tipo_json(valor))
        if isinstance(valor, dict):
            for chave, item in valor.items():
                nome = str(chave)
                filho = f"{caminho}.{nome}" if caminho else nome
                if nome in DADOSBI_CATEGORIAS_MONITORADAS and isinstance(item, (str, int, float)) and not isinstance(item, bool):
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


def monitorar_esquema_dadosbi(payload) -> list[dict]:
    """Compara estrutura e categorias públicas da resposta sem armazenar dados individuais."""
    esquema, categorias = _esquema_e_categorias(payload)
    agora = datetime.now().isoformat(timespec="seconds")
    alertas: list[dict] = []
    with connect() as conn:
        anterior = conn.execute("SELECT * FROM dadosbi_monitor ORDER BY id").fetchone()
        if anterior:
            esquema_anterior = json.loads(anterior["estrutura_json"] or "{}")
            categorias_anteriores = json.loads(anterior["categorias_json"] or "{}")
            for campo, tipos in esquema.items():
                if campo not in esquema_anterior:
                    alertas.append({"tipo": "campo_novo", "campo": campo, "detalhe": f"Novo campo na resposta ({', '.join(tipos)})."})
                    continue
                tipos_novos = sorted(set(tipos) - set(esquema_anterior[campo]))
                if tipos_novos:
                    alertas.append({
                        "tipo": "tipo_novo",
                        "campo": campo,
                        "detalhe": f"Novo tipo de valor: {', '.join(tipos_novos)}; tipos já vistos: {', '.join(esquema_anterior[campo])}.",
                    })
            for campo, valores in categorias.items():
                novos = sorted(set(valores) - set(categorias_anteriores.get(campo, [])), key=str.casefold)
                for valor in novos:
                    alertas.append({
                        "tipo": "categoria_nova",
                        "campo": campo,
                        "detalhe": f"Nova categoria: {valor[:120]}",
                    })
        if anterior:
            conn.execute(
                "UPDATE dadosbi_monitor SET estrutura_json=?, categorias_json=?, campos_monitorados=?, "
                "ultima_verificacao=? WHERE id=?",
                (json.dumps(esquema, ensure_ascii=False), json.dumps(categorias, ensure_ascii=False),
                 len(esquema), agora, anterior["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO dadosbi_monitor (estrutura_json, categorias_json, campos_monitorados, ultima_verificacao) "
                "VALUES (?,?,?,?)",
                (json.dumps(esquema, ensure_ascii=False), json.dumps(categorias, ensure_ascii=False), len(esquema), agora),
            )
        for alerta in alertas:
            conn.execute(
                "INSERT INTO dadosbi_alertas (tipo, campo, detalhe, criado_em) VALUES (?,?,?,?)",
                (alerta["tipo"], alerta["campo"][:300], alerta["detalhe"][:1000], agora),
            )
        conn.execute(
            "DELETE FROM dadosbi_alertas WHERE reconhecido_em IS NOT NULL "
            "AND id NOT IN (SELECT id FROM dadosbi_alertas WHERE reconhecido_em IS NOT NULL ORDER BY id DESC LIMIT 200)"
        )
    return alertas


def listar_monitor_dadosbi() -> dict:
    with connect() as conn:
        monitor = conn.execute("SELECT * FROM dadosbi_monitor ORDER BY id").fetchone()
        alertas = [dict(r) for r in conn.execute(
            "SELECT id, tipo, campo, detalhe, criado_em, reconhecido_em FROM dadosbi_alertas "
            "WHERE reconhecido_em IS NULL OR id IN "
            "(SELECT id FROM dadosbi_alertas WHERE reconhecido_em IS NOT NULL ORDER BY id DESC LIMIT 50) "
            "ORDER BY id DESC"
        )]
        pendentes = conn.execute(
            "SELECT COUNT(*) FROM dadosbi_alertas WHERE reconhecido_em IS NULL"
        ).fetchone()[0]
    return {
        "ultima_verificacao": monitor["ultima_verificacao"] if monitor else None,
        "campos_monitorados": monitor["campos_monitorados"] if monitor else 0,
        "alertas_pendentes": pendentes,
        "alertas": alertas,
    }


def reconhecer_alerta_dadosbi(alerta_id: int) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE dadosbi_alertas SET reconhecido_em=? WHERE id=? AND reconhecido_em IS NULL",
            (datetime.now().isoformat(timespec="seconds"), alerta_id),
        )
    return cur.rowcount > 0


def _sincronizar_dadosbi() -> dict:
    """Sincroniza atendimentos e visitas sem tratá-los como pacientes do cadastro principal."""
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        req = urllib.request.Request(url_dadosbi(), headers={"Accept": "application/json", "User-Agent": "TST-GESTAO/1"})
        with urllib.request.urlopen(req, timeout=30) as resposta:
            bruto = resposta.read(DADOSBI_LIMITE_RESPOSTA + 1)
        if len(bruto) > DADOSBI_LIMITE_RESPOSTA:
            raise ValueError("Resposta da API excede o limite permitido.")
        payload = json.loads(bruto.decode("utf-8-sig"))
        alertas_esquema = monitorar_esquema_dadosbi(payload)
        if alertas_esquema:
            notificar("dadosbi.esquema_alterado", {
                "origem": "Saúde Residence BI",
                "detectado_em": agora,
                "alertas": alertas_esquema,
            })
        registros = payload.get("dados") if isinstance(payload, dict) and payload.get("sucesso") is True else None
        if not isinstance(registros, list):
            raise ValueError("Formato de resposta não reconhecido.")
        if len(registros) > DADOSBI_LIMITE_REGISTROS:
            raise ValueError("Quantidade de registros excede o limite permitido.")

        atendimentos_criados = atendimentos_atualizados = visitas_criadas = visitas_atualizadas = erros = 0
        total_visitas = sum(
            len(r.get("visitas") or []) for r in registros
            if isinstance(r, dict) and isinstance(r.get("visitas") or [], list)
        )
        if total_visitas > DADOSBI_LIMITE_VISITAS:
            raise ValueError("Quantidade de visitas excede o limite permitido.")
        total_relatorios = sum(
            len(r.get("relatoriospendentes") or []) for r in registros
            if isinstance(r, dict) and isinstance(r.get("relatoriospendentes") or [], list)
        )
        if total_relatorios > DADOSBI_LIMITE_RELATORIOS:
            raise ValueError("Quantidade de relatórios pendentes excede o limite permitido.")

        with connect() as conn:
            atendimentos_validos = set()
            for registro in registros:
                try:
                    if not isinstance(registro, dict) or registro.get("id") in (None, "") or not str(registro.get("nmpaciente") or "").strip():
                        raise ValueError("Atendimento sem identificador ou nome do paciente.")
                    origem_id = str(registro["id"]).strip()
                    nome = str(registro["nmpaciente"]).strip()
                    admissao = _data_dadosbi(registro.get("dataadmissao"))
                    alta = _data_dadosbi(registro.get("dataalta"))
                    relatorios = _relatorios_pendentes_dadosbi(registro.get("relatoriospendentes"), origem_id)
                    if len(origem_id) > 40 or len(nome) > 200:
                        raise ValueError("Identificador ou nome excede o tamanho permitido.")
                    campos = (
                        nome,
                        str(registro.get("idoperadora") or "").strip() or None,
                        str(registro.get("nmoperadora") or "").strip() or None,
                        str(registro.get("nmservico") or "").strip() or None,
                        str(registro.get("status") or "").strip() or None,
                        admissao,
                        alta,
                        str(registro.get("condicaoalta") or "").strip() or None,
                        str(registro.get("possuiterapias") or "").strip() or None,
                        _data_dadosbi(registro.get("datainicioorcamento")),
                        _data_dadosbi(registro.get("datafimorcamento")),
                        _texto_dadosbi(registro, "idade", 10),
                        _texto_dadosbi(registro, "diagnostico", 200),
                        _texto_dadosbi(registro, "complexidade", 120),
                        _texto_dadosbi(registro, "cidade", 120),
                        _texto_dadosbi(registro, "bairro", 120),
                        json.dumps(relatorios, ensure_ascii=False),
                        agora,
                    )
                    existente = conn.execute(
                        "SELECT id FROM dadosbi_atendimentos WHERE origem_id = ?", (origem_id,)
                    ).fetchone()
                    if existente:
                        conn.execute(
                            "UPDATE dadosbi_atendimentos SET nome_paciente=?, operadora_id=?, operadora=?, servico=?, "
                            "status_origem=?, data_admissao=?, data_alta=?, condicao_alta=?, possui_terapias=?, "
                            "inicio_orcamento=?, fim_orcamento=?, idade=?, diagnostico=?, complexidade=?, cidade=?, bairro=?, "
                            "relatorios_pendentes_json=?, sincronizado_em=? WHERE origem_id=?",
                            (*campos, origem_id),
                        )
                        atendimentos_atualizados += 1
                    else:
                        conn.execute(
                            "INSERT INTO dadosbi_atendimentos (nome_paciente, operadora_id, operadora, servico, status_origem, "
                            "data_admissao, data_alta, condicao_alta, possui_terapias, inicio_orcamento, fim_orcamento, "
                            "idade, diagnostico, complexidade, cidade, bairro, relatorios_pendentes_json, sincronizado_em, "
                            "origem_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (*campos, origem_id),
                        )
                        atendimentos_criados += 1
                    atendimentos_validos.add(origem_id)
                except (TypeError, ValueError):
                    erros += 1

            for registro in registros:
                if not isinstance(registro, dict) or registro.get("id") in (None, ""):
                    continue
                atendimento_id = str(registro["id"]).strip()
                if atendimento_id not in atendimentos_validos:
                    continue
                visitas = registro.get("visitas") or []
                if not isinstance(visitas, list):
                    erros += 1
                    continue
                for visita in visitas:
                    try:
                        if not isinstance(visita, dict) or visita.get("id") in (None, ""):
                            raise ValueError("Visita sem identificador.")
                        origem_id = str(visita["id"]).strip()
                        visita_atendimento = str(visita.get("idadmission") or "").strip()
                        data = _data_dadosbi(visita.get("datavisita"))
                        if not data or len(origem_id) > 40 or visita_atendimento != atendimento_id:
                            raise ValueError("Vínculo ou data da visita inválidos.")
                        profissional = str(visita.get("nmprofessional") or "").strip() or None
                        especialidade = str(visita.get("nmespecialidade") or "").strip() or None
                        profissional_id = str(visita.get("idprofessional") or "").strip() or None
                        existente = conn.execute(
                            "SELECT id FROM dadosbi_visitas_origem WHERE origem_id = ?", (origem_id,)
                        ).fetchone()
                        campos = (atendimento_id, profissional_id, profissional, especialidade, data, agora)
                        if existente:
                            conn.execute(
                                "UPDATE dadosbi_visitas_origem SET atendimento_origem_id=?, profissional_id=?, "
                                "profissional=?, especialidade=?, data_visita=?, sincronizado_em=? WHERE origem_id=?",
                                (*campos, origem_id),
                            )
                            visitas_atualizadas += 1
                        else:
                            conn.execute(
                                "INSERT INTO dadosbi_visitas_origem (atendimento_origem_id, profissional_id, "
                                "profissional, especialidade, data_visita, sincronizado_em, origem_id) VALUES (?,?,?,?,?,?,?)",
                                (*campos, origem_id),
                            )
                            visitas_criadas += 1
                    except (TypeError, ValueError):
                        erros += 1

        resultado = {
            "ultima_execucao": agora,
            "ultima_sucesso": agora,
            "status": "sucesso" if not erros else "parcial",
            "atendimentos_criados": atendimentos_criados,
            "atendimentos_atualizados": atendimentos_atualizados,
            "visitas_criadas": visitas_criadas,
            "visitas_atualizadas": visitas_atualizadas,
            "alertas_esquema": len(alertas_esquema),
            "erro": f"{erros} registro(s) inválido(s)." if erros else None,
        }
        _salvar_status_dadosbi(resultado)
        return resultado
    except Exception as exc:
        if isinstance(exc, HTTPError):
            erro = f"API retornou HTTP {exc.code}."
        elif isinstance(exc, URLError):
            erro = "Não foi possível conectar à API."
        elif isinstance(exc, (ValueError, json.JSONDecodeError)):
            erro = "Resposta da API inválida ou fora do formato esperado."
        else:
            erro = "Falha ao importar os dados da API."
        anterior = status_dadosbi() or {}
        _salvar_status_dadosbi({
            "ultima_execucao": agora,
            "ultima_sucesso": anterior.get("ultima_sucesso"),
            "status": "erro",
            "atendimentos_criados": 0,
            "atendimentos_atualizados": 0,
            "visitas_criadas": 0,
            "visitas_atualizadas": 0,
            "erro": erro,
        })
        raise RuntimeError(erro) from exc


def sincronizar_dadosbi() -> dict:
    if not _dadosbi_execucao_trava.acquire(blocking=False):
        raise RuntimeError("Já existe uma sincronização Saúde Residence em andamento.")
    try:
        return _sincronizar_dadosbi()
    finally:
        _dadosbi_execucao_trava.release()


def iniciar_sincronizacao_dadosbi(logger) -> None:
    """Inicia uma única rotina automática no processo principal do aplicativo."""
    global _dadosbi_thread_iniciada
    with _dadosbi_trava:
        if _dadosbi_thread_iniciada:
            return
        _dadosbi_thread_iniciada = True

    def executar() -> None:
        while True:
            try:
                sincronizar_dadosbi()
            except Exception:
                logger.exception("Falha na sincronização automática Saúde Residence.")
            threading.Event().wait(DADOSBI_INTERVALO)

    threading.Thread(target=executar, name="sincronizacao-dadosbi", daemon=True).start()


# ---------- chaves ----------
def hash_chave(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def nova_chave() -> tuple[str, str, str]:
    token = "tst_" + secrets.token_urlsafe(32)
    return token, token[:10], hash_chave(token)


# ---------- webhooks ----------
def _enviar(hook, evento: str, dados) -> tuple[bool, str]:
    corpo = json.dumps(
        {"evento": evento, "ocorrido_em": datetime.now().isoformat(timespec="seconds"), "dados": dados},
        ensure_ascii=False,
        default=str,
    ).encode()
    assinatura = hmac.new(hook["segredo"].encode(), corpo, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        hook["url"],
        data=corpo,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "TST-GESTAO-Webhook/1",
            "X-TST-Event": evento,
            "X-TST-Signature": "sha256=" + assinatura,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            ok, resultado = 200 <= r.status < 300, f"HTTP {r.status}"
    except Exception as exc:  # falha de rede/HTTP não pode afetar o sistema
        ok, resultado = False, getattr(exc, "code", None) and f"HTTP {exc.code}" or str(exc)[:200]
    with connect() as conn:
        conn.execute(
            "INSERT INTO webhook_log (webhook_id, evento, ok, resultado, criado_em) VALUES (?,?,?,?,?)",
            (hook["id"], evento, int(ok), resultado, datetime.now().isoformat(timespec="seconds")),
        )
        conn.execute("DELETE FROM webhook_log WHERE id NOT IN (SELECT id FROM webhook_log ORDER BY id DESC LIMIT 300)")
    return ok, resultado


def _enviar_todos(evento: str, dados) -> None:
    with connect() as conn:
        hooks = conn.execute("SELECT * FROM webhooks WHERE ativo = 1").fetchall()
    for h in hooks:
        eventos = (h["eventos"] or "*").split(",")
        if "*" in eventos or evento in eventos:
            _enviar(h, evento, dados)


def notificar(evento: str, dados) -> None:
    threading.Thread(target=_enviar_todos, args=(evento, dados), daemon=True).start()


def testar(hook) -> tuple[bool, str]:
    return _enviar(hook, "teste.ping", {"mensagem": "Teste de webhook do TST-GESTÃO"})


# ---------- planilhas ----------
def norm(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_")


def _decodificar(dados: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return dados.decode(enc)
        except UnicodeDecodeError:
            continue
    return dados.decode("latin-1")


def ler_planilha(nome: str, dados: bytes) -> list[dict]:
    """Retorna linhas como dict {cabeçalho_normalizado: valor}."""
    nome = (nome or "").lower()
    if nome.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(dados), read_only=True, data_only=True)
        linhas = list(wb.worksheets[0].iter_rows(values_only=True))
    elif nome.endswith((".csv", ".txt")):
        texto = _decodificar(dados)
        amostra = texto[:4096]
        delim = ";" if amostra.count(";") > amostra.count(",") else ","
        linhas = list(csv.reader(io.StringIO(texto), delimiter=delim))
    else:
        raise ValueError("Formato não suportado. Envie um arquivo .xlsx ou .csv.")
    linhas = [l for l in linhas if l and any(c not in (None, "") for c in l)]
    if len(linhas) < 2:
        raise ValueError("A planilha precisa ter cabeçalho e ao menos uma linha de dados.")
    if len(linhas) - 1 > LIMITE_LINHAS:
        raise ValueError(f"Limite de {LIMITE_LINHAS} linhas por importação excedido.")
    cab = [norm(c) for c in linhas[0]]
    return [{c: v for c, v in zip(cab, l) if c} for l in linhas[1:]]


def valor_data(v):
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s)
    if m:
        return f"{m[3]}-{int(m[2]):02d}-{int(m[1]):02d}"
    return s[:10] if re.match(r"\d{4}-\d{2}-\d{2}", s) else s


def valor_mes(v):
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m")
    s = str(v).strip()
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{4})", s)
    if m:
        return f"{m[2]}-{int(m[1]):02d}"
    m = re.fullmatch(r"(\d{1,2})[/.-]\d{1,2}[/.-](\d{4})", s)
    if m:
        return f"{m[2]}-{int(m[1]):02d}"
    return s[:7] if re.match(r"\d{4}-\d{2}", s) else s


def valor_texto(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()
