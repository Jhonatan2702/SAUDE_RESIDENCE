"""Banco local (SQLite): usuários e o ESPELHO da URL Saúde Residence (tabelas dadosbi_*).

Não há cadastro próprio de pacientes: tudo o que é clínico/operacional vem da URL e pode ser
refeito por uma nova sincronização. O único dado que existe só aqui é a tabela de usuários.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

BASE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent.parent
)
DATA_DIR = Path(os.environ.get("TST_DATA_DIR", BASE_DIR / "dados"))
DB_PATH = DATA_DIR / "tst_gestao.db"
ErroIntegridade = sqlite3.IntegrityError

# ---------------------------------------------------------------- esquema (fonte única)
TABELAS: dict[str, str] = {
    "usuarios": """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
        nome TEXT NOT NULL,
        senha_hash TEXT NOT NULL,
        nivel TEXT NOT NULL DEFAULT 'operacional',
        ativo INTEGER NOT NULL DEFAULT 1,
        trocar_senha INTEGER NOT NULL DEFAULT 0""",
    "dadosbi_atendimentos": """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        origem_id TEXT NOT NULL UNIQUE,
        nome_paciente TEXT NOT NULL,
        operadora_id TEXT, operadora TEXT, servico TEXT, status_origem TEXT,
        data_admissao TEXT, data_alta TEXT, condicao_alta TEXT, possui_terapias TEXT,
        inicio_orcamento TEXT, fim_orcamento TEXT,
        idade TEXT, diagnostico TEXT, complexidade TEXT, cidade TEXT, bairro TEXT,
        relatorios_pendentes_json TEXT,
        zona_id TEXT, zona_nome TEXT, zona_bairros TEXT,
        sincronizado_em TEXT NOT NULL""",
    "dadosbi_visitas_origem": """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        origem_id TEXT NOT NULL UNIQUE,
        atendimento_origem_id TEXT NOT NULL,
        profissional_id TEXT, profissional TEXT, especialidade TEXT,
        data_visita TEXT NOT NULL,
        sincronizado_em TEXT NOT NULL""",
    "dadosbi_status": """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ultima_execucao TEXT, ultima_sucesso TEXT, status TEXT, erro TEXT,
        atendimentos_criados INTEGER, atendimentos_atualizados INTEGER,
        visitas_criadas INTEGER, visitas_atualizadas INTEGER""",
    "dadosbi_monitor": """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estrutura_json TEXT, categorias_json TEXT, campos_monitorados INTEGER, ultima_verificacao TEXT""",
    "dadosbi_alertas": """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL, campo TEXT NOT NULL, detalhe TEXT NOT NULL,
        criado_em TEXT NOT NULL, reconhecido_em TEXT""",
}
INDICES = [
    ("ix_dbi_visita_atend", "dadosbi_visitas_origem", "atendimento_origem_id"),
    ("ix_dbi_visita_data", "dadosbi_visitas_origem", "data_visita"),
]


class Conexao:
    """Conexão SQLite usada com `with`: confirma ao sair sem erro, desfaz em caso de erro e fecha."""

    dual = ""  # mantém compatível o SQL que seleciona sem FROM

    def __init__(self, raw: sqlite3.Connection):
        self.raw = raw

    def execute(self, sql: str, params=()):
        return self.raw.execute(sql, params)

    def executemany(self, sql: str, linhas):
        return self.raw.executemany(sql, linhas)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, tb):
        try:
            self.rollback() if tipo else self.commit()
        finally:
            self.close()


def conectar() -> Conexao:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(DB_PATH, timeout=15)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode = WAL")  # a sincronização não bloqueia quem está lendo os painéis
    raw.execute("PRAGMA foreign_keys = ON")
    return Conexao(raw)


def tabelas_existentes(con: Conexao) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}


def criar_estrutura(con: Conexao) -> None:
    """Cria tabelas e índices que faltam e acrescenta colunas novas em tabelas antigas."""
    existentes = tabelas_existentes(con)
    for nome, colunas in TABELAS.items():
        if nome not in existentes:
            con.execute(f"CREATE TABLE {nome} ({colunas})")
            continue
        atuais = {r[1] for r in con.execute(f"PRAGMA table_info({nome})")}
        for definicao in (c.strip() for c in colunas.split(",")):
            col = definicao.split()[0] if definicao else ""
            if col and col not in atuais and "NOT NULL" not in definicao and "UNIQUE" not in definicao and col.isidentifier():
                con.execute(f"ALTER TABLE {nome} ADD COLUMN {definicao}")
    for nome, tabela, coluna in INDICES:
        con.execute(f"CREATE INDEX IF NOT EXISTS {nome} ON {tabela} ({coluna})")
