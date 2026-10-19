import os
import tempfile
from datetime import date

os.environ["TST_DATA_DIR"] = tempfile.mkdtemp()

from tst_gestao import relatorios as rel  # noqa: E402
from tests.test_integracoes import admin  # noqa: E402


def test_relatorios_todos_renderizam_e_exportam():
    a = admin()
    hoje = date.today().isoformat()
    mes = hoje[:7]
    a.post("/api/pacientes", json={"codigo": "R1", "nome": "Rita", "nascimento": "1950-05-01", "bairro": "Centro", "cidade": "Recife",
                                   "operadora": "Unimed", "complexidade": "Básico", "servico": "Home Care", "data_admissao": hoje})
    a.post("/api/pacientes", json={"codigo": "R2", "nome": "Rui", "nascimento": "1980-01-01", "data_admissao": hoje,
                                   "data_alta": hoje, "motivo_alta": "Melhora clínica"})
    a.post("/api/terapias", json={"mes": mes, "codigo_paciente": "R1", "terapia": "PSICO", "situacao": "Pendente", "valor": 1500.5, "sessoes": 4})

    for slug in rel.REL:
        r = a.get(f"/relatorios/{slug}")
        assert r.status_code == 200, slug
        assert "Imprimir" in r.get_data(as_text=True)
        c = a.get(f"/relatorios/{slug}?formato=csv")
        assert c.status_code == 200 and c.mimetype == "text/csv", slug

    html = a.get("/relatorios/altas").get_data(as_text=True)
    assert "Rui" in html and "Melhora clínica" in html
    assert "Rita" in a.get("/relatorios/lista-pacientes").get_data(as_text=True)
    assert "Rui" not in a.get("/relatorios/lista-pacientes?situacao=ativos").get_data(as_text=True)
    assert "R$ 1.500,50" in a.get(f"/relatorios/lista-terapias?mes={mes}").get_data(as_text=True)
    assert a.get("/relatorios/inexistente").status_code == 404
    assert a.get("/relatorios").status_code == 200
    # parâmetros inválidos caem nos padrões
    assert a.get("/relatorios/altas?ref=xx&periodo=zz&mes=99").status_code == 200
