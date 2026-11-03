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
    codigos_bi = {"P2", "P3", "P4", "P5"}
    try:
        for codigo, nome, bairro, complexidade in (
            ("P2", "Bruna", "Centro", "Básico"),
            ("P3", "Caio", "Boa Vista", "Intermediário"),
            ("P4", "Dora", "Centro", "Intensivo"),
            ("P5", "Eva", "Várzea", "Básico"),
        ):
            assert c.post("/api/pacientes", json={
                "codigo": codigo, "nome": nome, "bairro": bairro, "cidade": "Recife",
                "complexidade": complexidade, "data_admissao": "2026-10-01",
            }).status_code == 200
        for codigo, terapia, profissional, situacao in (
            ("P2", "FISIO", "Prof Ana", "Pendente"),
            ("P2", "FISIO", "Prof Bia", "Pendente"),
            ("P3", "FISIO", "Prof Ana", "Pendente"),
            ("P2", "PSICO", "Prof Ana", "Ativa"),
            ("P4", "FONO", "Prof Bia", "Ativa"),
        ):
            assert c.post("/api/terapias", json={
                "mes": "2026-10", "codigo_paciente": codigo, "terapia": terapia,
                "profissional": profissional, "situacao": situacao,
            }).status_code == 200

        bi = c.get("/api/bi?ini=2026-10-01&fim=2026-10-31").get_json()
        indicadores = bi["evolucao"]["indicadores"]
        assert indicadores["pacientes_monitorados"]["parte"] == 3
        assert indicadores["pacientes_monitorados"]["total"] == 4
        assert next(p["total"] for p in bi["pendencias"] if p["label"] == "FISIO") == 2
        cx = {item["label"]: item["total"] for item in bi["complexidade"]}
        assert cx["Básico"] == 2 and cx["Intermediário"] == 1 and cx["Intensivo"] == 1
        fisio = next(t for t in bi["evolucao"]["terapias_mes"] if t["terapia"] == "FISIO")
        assert fisio["valores"][bi["evolucao"]["meses"].index("2026-10")] == 2
        disponibilidade = bi["evolucao"]["disponibilidade_profissionais"]
        assert {(r["profissional"], r["bairro"], r["pacientes"]) for r in disponibilidade
                if r["profissional"] == "Prof Ana" and r["terapia"] == "FISIO"} == {
                    ("Prof Ana", "Centro", 1), ("Prof Ana", "Boa Vista", 1),
                }
        obitos = c.get("/api/bi/obitos?ini=2026-10-01&fim=2026-10-31").get_json()
        assert [item["codigo"] for item in obitos] == ["P1"]
        faltas = c.get("/api/bi/faltas?tipo=monitoramento&ini=2026-10-01&fim=2026-10-31").get_json()
        assert faltas["linhas"] == [["P5", "Eva", "Não informado"]]
    finally:
        pacientes = c.get("/api/pacientes").get_json()
        for paciente in pacientes:
            if paciente["codigo"] in codigos_bi:
                c.delete(f"/api/pacientes/{paciente['id']}")
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
