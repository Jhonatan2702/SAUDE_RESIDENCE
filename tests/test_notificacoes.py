"""Avisos na tela: só o que mudou desde a sincronização anterior, para o perfil certo."""
import pytest

from tst_gestao import espelho, notificacoes


def _tipos(cliente):
    return {n["tipo"]: n for n in cliente.get("/api/notificacoes").get_json()}


def test_primeira_sincronizacao_nao_dispara_avisos(admin, url_falsa):
    espelho.sincronizar()
    assert admin.get("/api/notificacoes").get_json() == []


def test_novidades_geram_avisos_por_perfil(admin, criar_usuario, url_falsa):
    espelho.sincronizar()
    dados = url_falsa["payload"]["dados"]
    # Bruno foi a óbito; Davi recebeu alta; chegou uma paciente nova com terapia indicada
    dados[2].update(status="ALTA", dataalta="17/11/2026", condicaoalta="Óbito")
    dados[4].update(status="ALTA", dataalta="16/11/2026", condicaoalta="Alta de procedimento(s)")
    dados.append({"id": 7, "nmpaciente": "Fátima Nunes", "nmservico": "Monitoramento", "possuiterapias": "SIM", "status": "EM ATENDIMENTO",
                  "dataadmissao": "17/11/2026", "nmoperadora": "CASSI", "bairro": "Centro", "cidade": "Fortaleza", "visitas": []})
    espelho.sincronizar()
    t = _tipos(admin)
    assert t["obito"]["gravidade"] == "crit" and "Bruno Lima" in t["obito"]["texto"]
    assert t["obito"]["link"] == {"paciente": "Bruno Lima", "aba": "movimentacao"}
    assert t["alta"]["gravidade"] == "info" and "Davi Rocha" in t["alta"]["texto"]
    assert "Fátima Nunes" in t["admissao"]["texto"] and "terapia indicada" in t["admissao"]["texto"]
    # Fátima entrou com terapia indicada e sem visita: vira pendência; o Centro passa a ter paciente sem ninguém que cubra
    assert "Fátima Nunes" in t["pendencia"]["texto"]
    assert t["sem_cobertura"]["gravidade"] == "crit" and "CENTRO" in t["sem_cobertura"]["texto"]
    # sem novidades na sincronização seguinte: nenhum aviso novo
    ultimo = max(n["id"] for n in admin.get("/api/notificacoes").get_json())
    espelho.sincronizar()
    assert admin.get(f"/api/notificacoes?desde={ultimo}").get_json() == []
    # o perfil Operacional não recebe avisos só de gestão/administração
    op = criar_usuario("operador7", "operacional")
    assert {"obito", "alta", "admissao"} <= set(_tipos(op))


def test_orcamento_vencido_so_para_gestao(admin, criar_usuario):
    notificacoes.registrar("orcamento", "warn", "1 orçamento(s) venceram", nivel_min=2)
    assert "orcamento" in _tipos(admin)
    assert "orcamento" not in _tipos(criar_usuario("operador8", "operacional"))


def test_falha_avisa_admin_uma_vez(admin, criar_usuario, url_falsa):
    url_falsa["payload"] = {"sucesso": False}
    for _ in range(2):
        with pytest.raises(RuntimeError):
            espelho.sincronizar()
    falhas = [n for n in admin.get("/api/notificacoes").get_json() if n["tipo"] == "falha_sync"]
    assert len(falhas) == 1 and falhas[0]["link"] == {"url": "/integracao"}
    assert "falha_sync" not in _tipos(criar_usuario("gestor9", "gestor"))


@pytest.mark.parametrize("comp,antigo", [("2026-08", True), ("2026-10", False), ("08/2026", True), ("lixo", False)])
def test_relatorio_antigo(comp, antigo):
    from datetime import date
    assert notificacoes._competencia_antiga(comp, date(2026, 11, 18)) is antigo
