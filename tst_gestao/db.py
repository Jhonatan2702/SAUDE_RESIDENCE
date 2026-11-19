"""Inicialização do banco local (usuários + espelho da URL) e perfis de acesso."""
from __future__ import annotations

import os
import shutil
from datetime import datetime

from werkzeug.security import generate_password_hash

from .banco import DATA_DIR, DB_PATH, POSTGRES, Conexao, ErroIntegridade, conectar, criar_estrutura, tabelas_existentes  # noqa: F401

# Perfis em ordem crescente de acesso. Cada perfil enxerga também tudo o que os anteriores enxergam.
PERFIS = {
    "operacional": {"nivel": 1, "rotulo": "Operacional",
                    "descricao": "Somente o Painel operacional: relatórios pendentes, profissional × atendimento, "
                                 "região de abrangência, fichas realizadas e tabela de preços."},
    "gestor": {"nivel": 2, "rotulo": "Gestor",
               "descricao": "Painel BI completo e Painel operacional, sem acesso às configurações."},
    "admin": {"nivel": 3, "rotulo": "Administrador",
              "descricao": "Acesso integral: painéis, usuários e integração com a URL."},
}
NIVEIS = {k: v["nivel"] for k, v in PERFIS.items()}

# Tabelas da 1ª fase (planilha) e de recursos removidos: saem do banco na primeira execução da versão 2.
LEGADAS = ["pacientes", "terapias", "movimentacao", "opcoes", "evolucoes", "anexos", "api_chaves",
           "webhooks", "webhook_log", "dadosbi_visitas"]


def connect() -> Conexao:
    return conectar()


def _remover_legadas() -> None:
    if POSTGRES:  # as tabelas da 1ª fase só existiram no arquivo SQLite do executável
        return
    with connect() as conn:
        presentes = [t for t in LEGADAS if t in tabelas_existentes(conn)]
        if not presentes:
            return
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    # cópia de segurança do arquivo antes de apagar qualquer coisa
    shutil.copy2(DB_PATH, DATA_DIR / f"backup_antes_v2_{datetime.now():%Y%m%d_%H%M%S}.db")
    with connect() as conn:
        for t in presentes:
            conn.execute(f"DROP TABLE {t}")
    with connect() as conn:
        conn.raw.isolation_level = None
        conn.execute("VACUUM")


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _remover_legadas()
    with connect() as conn:
        criar_estrutura(conn)
        # níveis da versão anterior (consulta/operador) passam a ser o perfil Operacional
        conn.execute("UPDATE usuarios SET nivel = 'operacional' WHERE nivel NOT IN ('operacional', 'gestor', 'admin')")
        if not conn.execute("SELECT 1 FROM usuarios").fetchone():
            conn.execute(
                "INSERT INTO usuarios (usuario, nome, senha_hash, nivel, trocar_senha) VALUES ('admin', 'Administrador', ?, 'admin', 1)",
                (generate_password_hash(_senha_inicial_admin()),),
            )


def _senha_inicial_admin() -> str:
    """Senha do primeiro admin: TST_ADMIN_SENHA ou, só no executável local, 'admin'.

    Na hospedagem (PostgreSQL) o site é público: sem a variável, o sistema não sobe com admin/admin.
    """
    senha = os.environ.get("TST_ADMIN_SENHA", "")
    if senha:
        return senha
    if POSTGRES:
        raise RuntimeError("Defina a variável de ambiente TST_ADMIN_SENHA (senha inicial do usuário admin).")
    return "admin"
