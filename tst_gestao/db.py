from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("TST_DATA_DIR", BASE_DIR / "dados"))
DB_PATH = DATA_DIR / "tst_gestao.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nome TEXT NOT NULL,
    senha_hash TEXT NOT NULL,
    nivel TEXT NOT NULL DEFAULT 'consulta',
    ativo INTEGER NOT NULL DEFAULT 1,
    trocar_senha INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS pacientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    nascimento TEXT,
    sexo TEXT,
    bairro TEXT,
    cidade TEXT,
    operadora TEXT,
    diagnostico TEXT,
    complexidade TEXT,
    servico TEXT,
    data_admissao TEXT,
    data_alta TEXT,
    motivo_alta TEXT
);
CREATE TABLE IF NOT EXISTS terapias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mes TEXT NOT NULL,
    codigo_paciente TEXT NOT NULL,
    terapia TEXT NOT NULL,
    modalidade TEXT,
    empresa TEXT,
    profissional TEXT,
    situacao TEXT,
    sessoes INTEGER,
    frequencia TEXT,
    valor REAL,
    agendado TEXT,
    relatorio TEXT,
    observacao TEXT,
    UNIQUE (mes, codigo_paciente, terapia)
);
CREATE TABLE IF NOT EXISTS movimentacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data TEXT NOT NULL,
    codigo_paciente TEXT NOT NULL,
    evento TEXT NOT NULL,
    motivo TEXT
);
CREATE TABLE IF NOT EXISTS opcoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lista TEXT NOT NULL,
    valor TEXT NOT NULL,
    UNIQUE (lista, valor)
);
CREATE TABLE IF NOT EXISTS evolucoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_paciente TEXT NOT NULL,
    data TEXT NOT NULL,
    tipo TEXT NOT NULL,
    profissional TEXT,
    texto TEXT NOT NULL,
    autor TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS anexos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_paciente TEXT NOT NULL,
    categoria TEXT NOT NULL,
    descricao TEXT,
    data_documento TEXT,
    nome_original TEXT NOT NULL,
    arquivo TEXT NOT NULL UNIQUE,
    tamanho INTEGER NOT NULL,
    enviado_por TEXT,
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_evo_pac ON evolucoes (codigo_paciente);
CREATE INDEX IF NOT EXISTS ix_anx_pac ON anexos (codigo_paciente);
CREATE INDEX IF NOT EXISTS ix_mov_data ON movimentacao (data);
CREATE TABLE IF NOT EXISTS api_chaves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    prefixo TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    escopo TEXT NOT NULL DEFAULT 'leitura',
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL,
    ultimo_uso TEXT
);
CREATE TABLE IF NOT EXISTS webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    url TEXT NOT NULL,
    eventos TEXT NOT NULL DEFAULT '*',
    segredo TEXT NOT NULL,
    ativo INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS webhook_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id INTEGER NOT NULL,
    evento TEXT NOT NULL,
    ok INTEGER NOT NULL,
    resultado TEXT,
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ter_mes ON terapias (mes);
"""

LISTAS = {
    "operadoras": "Operadoras",
    "empresas": "Empresas",
    "profissionais": "Profissionais",
    "diagnosticos": "Diagnósticos",
    "motivos_alta": "Motivos de alta",
    "complexidades": "Complexidade",
    "servicos": "Serviços",
    "situacoes": "Situações",
    "frequencias": "Frequências",
    "terapias": "Terapias",
    "modalidades": "Modalidades",
    "tipos_evolucao": "Tipos de registro do prontuário",
    "categorias_anexo": "Categorias de anexo",
}

SEEDS = {
    "tipos_evolucao": ["Evolução", "Anamnese", "Intercorrência", "Orientação", "Visita", "Observação"],
    "categorias_anexo": ["Documento", "Exame", "Receita", "Laudo", "Relatório", "Outros"],
    "complexidades": ["Básico", "Intermediário", "Intensivo"],
    "terapias": ["PSICO", "NUTRI", "TO", "FONO", "FISIO"],
    "situacoes": ["Pendente", "Realizada", "Cancelada", "Suspensa"],
    "frequencias": ["Diária", "Semanal", "Quinzenal", "Mensal"],
    "modalidades": ["Domiciliar", "Ambulatorial", "Teleatendimento"],
    "motivos_alta": ["Alta clínica", "Óbito", "Transferência", "Desistência", "Perda de elegibilidade"],
}

EVENTOS = ["Admissão", "Alta", "Óbito", "Internação", "Retorno"]
NIVEIS = {"consulta": 1, "operador": 2, "gestor": 3, "admin": 4}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
        for lista, valores in SEEDS.items():
            conn.executemany(
                "INSERT OR IGNORE INTO opcoes (lista, valor) VALUES (?, ?)",
                [(lista, v) for v in valores],
            )
        if not conn.execute("SELECT 1 FROM usuarios").fetchone():
            conn.execute(
                "INSERT INTO usuarios (usuario, nome, senha_hash, nivel, trocar_senha) "
                "VALUES ('admin', 'Administrador', ?, 'admin', 1)",
                (generate_password_hash("admin"),),
            )
