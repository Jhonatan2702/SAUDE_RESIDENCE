import json
import os
import tempfile

os.environ["TST_DATA_DIR"] = tempfile.mkdtemp()
os.environ["TST_DADOSBI_URL"] = "http://teste.local/dadospaciente"  # a URL real fica só em dados/config.json

import pytest  # noqa: E402

from tst_gestao import espelho  # noqa: E402
from tst_gestao.app import create_app  # noqa: E402
from tst_gestao.db import connect  # noqa: E402


def visita(vid, atendimento, data, especialidade, profissional="Prof. Fisio", pid=10):
    return {"id": vid, "idadmission": atendimento, "datavisita": data, "nmespecialidade": especialidade,
            "nmprofessional": profissional, "idprofessional": pid}


def payload_base() -> dict:
    """Cenário controlado (período de referência: outubro/2026)."""
    return {"sucesso": True, "dados": [
        {"id": 1, "nmpaciente": "Ana Souza", "nmservico": "Monitoramento", "possuiterapias": "SIM", "status": "EM ATENDIMENTO",
         "dataadmissao": "10/01/2026", "datainicioorcamento": "01/10/2026", "datafimorcamento": "31/10/2026",
         "zoneamento": {"id": "6011", "nome": "ALDEOTA 1", "bairros": "PARQUELANDIA, ALDEOTA,\nMEIRELES"}, "nmoperadora": "CASSI", "idoperadora": 2, "idade": 81, "diagnostico": "AVC",
         "complexidade": "Alta", "cidade": "Fortaleza", "bairro": "Parquelândia",
         "relatoriospendentes": [{"id": "R1", "idadmission": 1, "idprofessional": 10, "nmprofessional": "Prof. Fisio",
                                  "idespecialidade": 5, "nmespecialidade": "Fisioterapia Respiratória e/ou Motora", "competencia": "2026-09"}],
         "visitas": [visita(101, 1, "20/10/2026", "Fisioterapia Respiratória e/ou Motora"),
                     visita(102, 1, "25/10/2026", "Fonoaudiologia", "Prof. Fono", 11),
                     visita(103, 1, "15/08/2026", "Nutricionista", "Prof. Nutri", 12)]},
        {"id": 2, "nmpaciente": "ANA  SOUZA", "nmservico": "Visita Médica", "possuiterapias": "NÃO", "status": "EM ATENDIMENTO",
         "dataadmissao": "01/10/2026", "nmoperadora": "CASSI", "visitas": []},
        {"id": 3, "nmpaciente": "Bruno Lima", "nmservico": "Enfermagem Domiciliar", "possuiterapias": "SIM", "status": "EM ATENDIMENTO",
         "dataadmissao": "01/09/2026", "datainicioorcamento": "16/09/2026", "datafimorcamento": "15/10/2026",
         "zoneamento": {"id": "6011", "nome": "ALDEOTA 1", "bairros": "PARQUELANDIA, ALDEOTA,\nMEIRELES"}, "nmoperadora": "AMIL", "bairro": "Aldeota", "cidade": "FORTALEZA", "visitas": []},
        {"id": 4, "nmpaciente": "Carla Dias", "nmservico": "Monitoramento", "possuiterapias": "SIM", "status": "ALTA",
         "dataadmissao": "01/05/2026", "dataalta": "12/10/2026", "condicaoalta": "Óbito", "nmoperadora": "AMIL",
         "visitas": [visita(104, 4, "05/10/2026", "Fisioterapia Respiratória e/ou Motora")]},
        {"id": 5, "nmpaciente": "Davi Rocha", "nmservico": "Monitoramento", "possuiterapias": "NÃO", "status": "EM ATENDIMENTO",
         "dataadmissao": "01/02/2026", "zoneamento": {"id": "6041", "nome": "MONTESE 1", "bairros": "Parquelândia"}, "nmoperadora": "CAMED", "bairro": "PARQUELANDIA", "cidade": "Fortaleza",
         "visitas": [visita(105, 5, "20/10/2026", "Fisioterapia Respiratória e/ou Motora"),
                     visita(106, 5, "21/10/2026", "Fonoaudiologia", "Prof. Fono", 11),
                     visita(107, 5, "22/10/2026", "Terapeuta Ocupacional", "Prof. TO", 13),
                     visita(108, 5, "23/10/2026", "Psicólogo", "Prof. Psico", 14)]},
    ]}


class Resposta:
    def __init__(self, payload):
        self.corpo = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limite):
        return self.corpo


@pytest.fixture
def url_falsa(monkeypatch):
    """Substitui a URL por um payload editável."""
    estado = {"payload": payload_base()}
    monkeypatch.setattr(espelho.urllib.request, "urlopen", lambda *_a, **_k: Resposta(estado["payload"]))
    return estado


@pytest.fixture
def app():
    a = create_app()
    with connect() as conn:
        for tabela in ("dadosbi_atendimentos", "dadosbi_visitas_origem", "dadosbi_status", "dadosbi_monitor", "dadosbi_alertas"):
            conn.execute(f"DELETE FROM {tabela}")
    return a


def entrar(app, usuario, senha):
    c = app.test_client()
    c.get("/login")
    with c.session_transaction() as s:
        token = s["csrf"]
    c.post("/login", data={"usuario": usuario, "senha": senha, "csrf_token": token})
    with c.session_transaction() as s:
        c.environ_base["HTTP_X_CSRF_TOKEN"] = s["csrf"]
    return c


@pytest.fixture
def admin(app):
    with connect() as conn:
        conn.execute("UPDATE usuarios SET trocar_senha = 0 WHERE usuario = 'admin'")
    return entrar(app, "admin", "admin")


@pytest.fixture
def criar_usuario(app, admin):
    def criar(usuario, nivel):
        r = admin.post("/api/usuarios", json={"usuario": usuario, "nome": usuario.title(), "nivel": nivel, "senha": "segredo1"})
        assert r.status_code in (200, 409)
        with connect() as conn:
            conn.execute("UPDATE usuarios SET trocar_senha = 0 WHERE usuario = ?", (usuario,))
        return entrar(app, usuario, "segredo1")
    return criar
