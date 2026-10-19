import os
import tempfile

os.environ["TST_DATA_DIR"] = tempfile.mkdtemp()

from tst_gestao.app import create_app  # noqa: E402


def cliente(usuario="admin", senha="admin"):
    c = create_app().test_client()
    c.get("/login")
    with c.session_transaction() as s:
        token = s["csrf"]
    c.post("/login", data={"usuario": usuario, "senha": senha, "csrf_token": token})
    with c.session_transaction() as s:
        token = s["csrf"]
    c.environ_base["HTTP_X_CSRF_TOKEN"] = token
    return c


def test_fluxo_completo():
    c = cliente()
    assert c.get("/").status_code == 302  # troca de senha obrigatória
    assert c.post("/api/senha", json={"atual": "admin", "nova": "segredo1"}).status_code == 200

    p = {"codigo": "P1", "nome": "Ana", "nascimento": "1950-05-10", "bairro": "Centro", "cidade": "X",
         "complexidade": "Básico", "data_admissao": "2026-10-01"}
    assert c.post("/api/pacientes", json=p).status_code == 200
    assert c.post("/api/pacientes", json=p).status_code == 409
    assert c.post("/api/movimentacao", json={"data": "2026-10-19", "codigo_paciente": "P1", "evento": "Óbito"}).status_code == 200
    assert c.post("/api/terapias", json={"mes": "2026-10", "codigo_paciente": "P1", "terapia": "FONO", "situacao": "Pendente"}).status_code == 200

    pac = c.get("/api/pacientes").get_json()[0]
    assert pac["data_alta"] == "2026-10-19" and pac["motivo_alta"] == "Óbito"

    d = c.get("/api/bi?ref=2026-10-19").get_json()
    assert d["admissoes"]["mes"] == 1 and d["obitos"]["dia"] == 1
    assert d["mortalidade"]["mes"]["taxa"] == 100.0
    assert c.get("/").status_code == 200


def test_csrf_e_permissoes():
    c = cliente("admin", "segredo1")
    c.post("/api/usuarios", json={"usuario": "leitor", "nome": "L", "nivel": "consulta", "senha": "abcdef"})
    sem_token = create_app().test_client()
    assert sem_token.post("/api/pacientes", json={}).status_code == 400

    leitor = cliente("leitor", "abcdef")
    leitor.post("/api/senha", json={"atual": "abcdef", "nova": "novasenha"})
    assert leitor.get("/api/pacientes").status_code == 200
    assert leitor.post("/api/pacientes", json={"codigo": "Z", "nome": "Z"}).status_code == 403
    assert leitor.get("/usuarios").status_code == 403
