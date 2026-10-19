import io
import os
import tempfile

os.environ["TST_DATA_DIR"] = tempfile.mkdtemp()

from tst_gestao.app import ANEXOS_DIR, create_app  # noqa: E402
from tests.test_integracoes import admin  # noqa: E402


def test_prontuario_evolucoes_e_anexos():
    a = admin()
    a.post("/api/pacientes", json={"codigo": "Z/1", "nome": "Zé", "data_admissao": "2026-10-01"})
    assert a.get("/paciente/Z/1").status_code == 200
    assert a.get("/paciente/NAO").status_code == 404

    assert a.post("/api/prontuario/Z/1/evolucoes", json={"tipo": "Evolução", "texto": "Estável <b>ok</b>", "data": "2026-10-19"}).status_code == 200
    assert a.post("/api/prontuario/Z/1/evolucoes", json={"tipo": "Evolução", "texto": ""}).status_code == 400

    def enviar(nome, conteudo, cat="Exame"):
        return a.post("/api/prontuario/Z/1/anexos", data={"file": (io.BytesIO(conteudo), nome), "categoria": cat, "descricao": "Hemograma"},
                      content_type="multipart/form-data")

    assert enviar("../../evil.html", b"<script>1</script>").status_code == 400
    assert enviar("x.exe", b"MZ").status_code == 400
    assert enviar("vazio.pdf", b"").status_code == 400
    assert enviar("exame ç.pdf", b"%PDF-1.4 teste").status_code == 200

    d = a.get("/api/prontuario/Z/1").get_json()
    assert d["evolucoes"][0]["texto"].startswith("Estável") and d["evolucoes"][0]["autor"]
    anexo = d["anexos"][0]
    assert anexo["nome_original"] == "exame ç.pdf" and "arquivo" not in anexo
    r = a.get(f"/anexos/{anexo['id']}")
    assert r.status_code == 200 and r.data.startswith(b"%PDF") and r.headers["X-Content-Type-Options"] == "nosniff"
    r.close()
    baixar = a.get(f"/anexos/{anexo['id']}?baixar=1")
    assert "attachment" in baixar.headers["Content-Disposition"]
    baixar.close()
    assert create_app().test_client().get(f"/anexos/{anexo['id']}").status_code == 302  # exige login
    assert len(list(ANEXOS_DIR.iterdir())) == 1

    pid = next(p["id"] for p in a.get("/api/pacientes").get_json() if p["codigo"] == "Z/1")
    assert a.delete(f"/api/pacientes/{pid}").status_code == 200
    assert not list(ANEXOS_DIR.iterdir())
