"""Apoio às integrações: chaves de API, webhooks e leitura de planilhas."""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import json
import re
import secrets
import threading
import unicodedata
import urllib.request
from datetime import date, datetime

from .db import connect

EVENTOS_WEBHOOK = [
    "paciente.criado",
    "paciente.atualizado",
    "terapia.criada",
    "terapia.atualizada",
    "movimentacao.criada",
]
LIMITE_LINHAS = 5000


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
