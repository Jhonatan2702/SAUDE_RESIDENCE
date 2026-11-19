"""Banco local: estrutura do espelho e limpeza das tabelas da fase da planilha."""
import pytest

from tst_gestao import banco
from tst_gestao.db import DATA_DIR, connect, init_db


def test_estrutura_tem_apenas_usuarios_e_espelho(app):
    with connect() as conn:
        tabelas = banco.tabelas_existentes(conn)
    assert tabelas >= set(banco.TABELAS)
    assert not tabelas & {"pacientes", "terapias", "webhooks"}


@pytest.mark.skipif(banco.POSTGRES, reason="as tabelas da 1ª fase só existiram no arquivo SQLite do executável")
def test_tabelas_da_planilha_sao_removidas_com_backup(app):
    with connect() as conn:
        conn.execute("CREATE TABLE pacientes (id INTEGER PRIMARY KEY, nome TEXT)")
        conn.execute("INSERT INTO pacientes (nome) VALUES ('Fulano')")
        conn.execute("INSERT INTO usuarios (usuario, nome, senha_hash, nivel) VALUES ('antigo', 'Antigo', 'x', 'consulta')")
    antes = set(DATA_DIR.glob("backup_antes_v2_*.db"))
    init_db()
    with connect() as conn:
        assert "pacientes" not in banco.tabelas_existentes(conn)
        assert conn.execute("SELECT nivel FROM usuarios WHERE usuario = 'antigo'").fetchone()[0] == "operacional"
        conn.execute("DELETE FROM usuarios WHERE usuario = 'antigo'")
    assert len(set(DATA_DIR.glob("backup_antes_v2_*.db")) - antes) == 1
