"""Sincronização da URL para o banco local (espelho), monitor de formato e avisos."""
import json

import pytest

from tst_gestao import espelho
from tst_gestao.db import connect


def test_sincroniza_cria_e_depois_atualiza(app, url_falsa):
    primeiro = espelho.sincronizar()
    assert (primeiro["atendimentos_criados"], primeiro["visitas_criadas"]) == (5, 8)
    assert primeiro["status"] == "sucesso" and primeiro["alertas_esquema"] == 0

    url_falsa["payload"]["dados"][0]["visitas"][0]["nmespecialidade"] = "Fonoaudiologia"
    segundo = espelho.sincronizar()
    assert (segundo["atendimentos_criados"], segundo["atendimentos_atualizados"]) == (0, 5)
    assert (segundo["visitas_criadas"], segundo["visitas_atualizadas"]) == (0, 8)

    with connect() as conn:
        a = conn.execute("SELECT * FROM dadosbi_atendimentos WHERE origem_id = '1'").fetchone()
        v = conn.execute("SELECT * FROM dadosbi_visitas_origem WHERE origem_id = '101'").fetchone()
    assert a["data_admissao"] == "2026-01-10" and a["idade"] == "81" and a["bairro"] == "Parquelândia"
    assert json.loads(a["relatorios_pendentes_json"])[0]["competencia"] == "2026-09"
    assert v["especialidade"] == "Fonoaudiologia" and v["data_visita"] == "2026-10-20"
    assert espelho.status()["atendimentos"] == 5


def test_registro_invalido_e_ignorado_sem_derrubar_a_sincronizacao(app, url_falsa):
    url_falsa["payload"]["dados"].append({"id": 9, "nmpaciente": "", "visitas": []})
    url_falsa["payload"]["dados"][0]["visitas"].append({"id": 999, "idadmission": 1, "datavisita": "31/13/2026"})
    r = espelho.sincronizar()
    assert r["status"] == "parcial" and r["atendimentos_criados"] == 5 and "2 registro(s)" in r["erro"]


def test_monitor_detecta_mudanca_de_formato_sem_expor_pacientes(app, url_falsa):
    espelho.sincronizar()
    url_falsa["payload"]["dados"][0]["novoCampo"] = {"x": 1}
    url_falsa["payload"]["dados"][0]["status"] = 1
    url_falsa["payload"]["dados"][0]["nmservico"] = "Serviço novo"
    r = espelho.sincronizar()
    assert r["alertas_esquema"] >= 3
    m = espelho.monitor()
    texto = json.dumps(m["alertas"], ensure_ascii=False)
    assert "novoCampo" in texto and "Serviço novo" in texto and "Ana Souza" not in texto
    alerta = next(a for a in m["alertas"] if a["campo"].endswith(".novoCampo"))
    assert espelho.reconhecer_alerta(alerta["id"]) and not espelho.reconhecer_alerta(alerta["id"])


def test_falha_da_url_registra_status_e_preserva_o_espelho(app, url_falsa):
    espelho.sincronizar()
    url_falsa["payload"] = {"sucesso": False}
    with pytest.raises(RuntimeError):
        espelho.sincronizar()
    s = espelho.status()
    assert s["status"] == "erro" and s["ultima_sucesso"] and s["atendimentos"] == 5


def test_sincronizar_pela_tela_exige_admin(admin, criar_usuario, url_falsa):
    assert admin.post("/api/integracao/sincronizar").status_code == 200
    gestor = criar_usuario("gestor1", "gestor")
    assert gestor.post("/api/integracao/sincronizar").status_code == 403
