"""Banco do TST-GESTÃO: usuários e o ESPELHO da URL Saúde Residence (tabelas dadosbi_*).

Não há cadastro próprio de pacientes: tudo o que é clínico/operacional vem da URL e pode ser
refeito por uma nova sincronização. O único dado que existe só aqui é a tabela de usuários.

Dois motores, mesmo código SQL (com `?` como marcador):
- SQLite (padrão): arquivo dados/tst_gestao.db, usado pelo executável no computador do cliente.
- PostgreSQL: quando a variável DATABASE_URL existe (hospedagem no Render com banco no Neon), porque
  o disco do Render gratuito é apagado a cada reinício.
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
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))

if POSTGRES:
    import psycopg

    ErroIntegridade: tuple = (sqlite3.IntegrityError, psycopg.errors.IntegrityError)
else:
    ErroIntegridade = (sqlite3.IntegrityError,)

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
    # avisos na tela gerados a cada sincronização (o que mudou e pede atenção)
    "notificacoes": """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        criado_em TEXT NOT NULL, tipo TEXT NOT NULL, gravidade TEXT NOT NULL,
        titulo TEXT NOT NULL, texto TEXT, link TEXT, nivel_min INTEGER NOT NULL DEFAULT 1""",
    # fotografia da sincronização anterior, para comparar com a nova
    "notificacoes_estado": """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estado_json TEXT NOT NULL, atualizado_em TEXT NOT NULL""",
    "dadosbi_alertas": """
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipo TEXT NOT NULL, campo TEXT NOT NULL, detalhe TEXT NOT NULL,
        criado_em TEXT NOT NULL, reconhecido_em TEXT""",
}
INDICES = [
    ("ix_dbi_visita_atend", "dadosbi_visitas_origem", "atendimento_origem_id"),
    ("ix_dbi_visita_data", "dadosbi_visitas_origem", "data_visita"),
]


class Linha(dict):
    """Linha do PostgreSQL que se comporta como a sqlite3.Row: r["coluna"], r[0], dict(r) e tuple(r) (valores).

    Os valores ficam também numa lista, na ordem do SELECT: colunas com o mesmo nome (ex.: dois COUNT(*))
    não se perdem no acesso por posição.
    """

    def __init__(self, nomes, valores):
        super().__init__(zip(nomes, valores))
        self._valores = list(valores)

    def __iter__(self):
        return iter(self._valores)

    def __len__(self):
        return len(self._valores)

    def __getitem__(self, chave):
        if isinstance(chave, (int, slice)):
            return self._valores[chave]
        return super().__getitem__(chave)


def _fabrica_linhas(cursor):
    nomes = [c.name for c in cursor.description or ()]
    return lambda valores: Linha(nomes, valores)


def _sql_pg(sql: str) -> str:
    """Troca o marcador `?` (SQLite) por `%s` (psycopg); `%` literal passa a ser `%%`."""
    return sql.replace("%", "%%").replace("?", "%s")


class Conexao:
    """Conexão usada com `with`: confirma ao sair sem erro, desfaz em caso de erro e fecha."""

    dual = ""  # mantém compatível o SQL que seleciona sem FROM

    def __init__(self, raw, pg: bool = False):
        self.raw = raw
        self._pg = pg

    def execute(self, sql: str, params=()):
        if not self._pg:
            return self.raw.execute(sql, params)
        return self.raw.execute(_sql_pg(sql), params) if params else self.raw.execute(sql)

    def executemany(self, sql: str, linhas):
        if not self._pg:
            return self.raw.executemany(sql, linhas)
        with self.raw.cursor() as cur:
            cur.executemany(_sql_pg(sql), list(linhas))

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


def _conectar_pg():
    """Uma conexão nova por operação, fechada ao final (sem pool).

    O Neon gratuito desliga quando ocioso e derruba conexões paradas; abrir na hora evita conexões
    "mortas" guardadas e deixa o banco dormir. Na mesma região do Render, conectar leva poucos ms.
    Keepalives + timeouts: uma rede travada vira erro em segundos, nunca uma espera sem fim.
    """
    import psycopg

    return psycopg.connect(
        DATABASE_URL, row_factory=_fabrica_linhas, prepare_threshold=None,  # compatível com o "-pooler" do Neon
        connect_timeout=15, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=3,
    )


def conectar() -> Conexao:
    if POSTGRES:
        return Conexao(_conectar_pg(), pg=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(DB_PATH, timeout=15)
    raw.row_factory = sqlite3.Row
    raw.execute("PRAGMA journal_mode = WAL")  # a sincronização não bloqueia quem está lendo os painéis
    raw.execute("PRAGMA foreign_keys = ON")
    return Conexao(raw)


def tabelas_existentes(con: Conexao) -> set[str]:
    if POSTGRES:
        return {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")}
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")}


def _colunas(con: Conexao, tabela: str) -> set[str]:
    if POSTGRES:
        return {r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = ?",
            (tabela,))}
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}


def _ddl(colunas: str) -> str:
    """Ajusta a definição das colunas ao motor em uso (o esquema acima é escrito para SQLite)."""
    if not POSTGRES:
        return colunas
    return (colunas.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY")
            .replace(" COLLATE NOCASE", ""))


def criar_estrutura(con: Conexao) -> None:
    """Cria tabelas e índices que faltam e acrescenta colunas novas em tabelas antigas."""
    existentes = tabelas_existentes(con)
    for nome, colunas in TABELAS.items():
        colunas = _ddl(colunas)
        if nome not in existentes:
            con.execute(f"CREATE TABLE {nome} ({colunas})")
            continue
        atuais = _colunas(con, nome)
        for definicao in (c.strip() for c in colunas.split(",")):
            col = definicao.split()[0] if definicao else ""
            if col and col not in atuais and "NOT NULL" not in definicao and "UNIQUE" not in definicao and col.isidentifier():
                con.execute(f"ALTER TABLE {nome} ADD COLUMN {definicao}")
    for nome, tabela, coluna in INDICES:
        con.execute(f"CREATE INDEX IF NOT EXISTS {nome} ON {tabela} ({coluna})")
    if POSTGRES:  # no SQLite o COLLATE NOCASE já impede "Admin" e "admin" ao mesmo tempo
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_usuarios_usuario_lower ON usuarios (LOWER(usuario))")
