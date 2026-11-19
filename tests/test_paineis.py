"""Regras dos indicadores (pedidos do cliente) e permissões de cada perfil."""
import pytest

from tst_gestao import espelho

P = "ini=2026-10-01&fim=2026-10-31"


@pytest.fixture
def dados(app, url_falsa):
    espelho.sincronizar()


def test_indicadores_do_painel(admin, dados):
    d = admin.get(f"/api/painel?{P}").get_json()
    k = d["kpis"]
    # "Ana Souza" e "ANA  SOUZA" são a mesma pessoa com dois atendimentos
    assert (k["pacientes_ativos"], k["atendimentos_ativos"]) == (3, 4)
    # pacientes ativos de monitoramento com terapias (substitui "terapias ativas")
    assert (k["monit_terapias"], k["monitoramento"]) == (1, 2)
    # mortalidade: 1 óbito (Carla) ÷ 4 pacientes atendidos no período
    assert (k["obitos"], k["atendidos"], k["mortalidade"]) == (1, 4, 25.0)
    # nº de pacientes por terapia (janela de 90 dias, só ativos)
    por_ter = {t["sigla"]: t for t in d["terapias"]}
    assert {s: por_ter[s]["pacientes"] for s in ("FISIO", "FONO", "TO", "NUTRI", "PSICO")} == \
        {"FISIO": 2, "FONO": 2, "TO": 1, "NUTRI": 1, "PSICO": 1}
    # quantos pacientes por terapia pendente: Ana sem Nutri há 15+ dias; Bruno indicado e sem nenhuma visita
    assert por_ter["NUTRI"]["pendentes"] == 1 and k["sem_atendimento_terapia"] == 1 and k["pendentes"] == 2
    # complexidade pela quantidade de terapias: Ana 3 (Intermediário), Davi 4 (Intensivo)
    assert {n["rotulo"]: n["valor"] for n in d["complexidade"]} == {"Básico": 0, "Intermediário": 1, "Intensivo": 1}
    assert d["complexidade_terapia"]["Intensivo"]["PSICO"] == 1
    # bairro com e sem acento/variação de caixa é agrupado
    assert {b["rotulo"] for b in d["bairros"]} >= {"PARQUELANDIA", "ALDEOTA"}


def test_mortalidade_e_clicavel_e_mostra_quem_foi_a_obito(admin, dados):
    r = admin.get(f"/api/painel/detalhe?tipo=obitos&{P}").get_json()
    assert r["total"] == 1 and r["linhas"][0][0] == "Carla Dias" and r["linhas"][0][6] == "Óbito"
    hist = admin.get(f"/api/painel/detalhe?tipo=paciente&valor=Carla Dias&{P}").get_json()
    assert hist["total"] == 1


@pytest.mark.parametrize("tipo,valor,esperados", [
    ("monit_terapias", "", ["Ana Souza"]),
    ("pendentes", "NUTRI", ["Ana Souza"]),
    ("pendentes", "SEM", ["Bruno Lima"]),
    ("pendentes", "", ["Ana Souza", "Bruno Lima"]),
    ("complexidade", "Intensivo", ["Davi Rocha"]),
    ("em_terapia", "FISIO", ["Ana Souza", "Davi Rocha"]),
    ("complexidade_terapia", "Intermediário|FONO", ["Ana Souza"]),
    ("dma_obitos", "ano", ["Carla Dias"]),
])
def test_cada_numero_abre_a_lista_de_pacientes(admin, dados, tipo, valor, esperados):
    r = admin.get(f"/api/painel/detalhe?tipo={tipo}&valor={valor}&{P}").get_json()
    assert sorted(l[0] for l in r["linhas"]) == esperados


def test_painel_operacional(admin, dados):
    rel = admin.get("/api/operacional/relatorios").get_json()
    assert rel["total"] == 1 and rel["linhas"][0][0] == "Ana Souza" and rel["linhas"][0][3] == "FISIO"
    assert rel["mais_antiga"] == "09/2026"
    fic = admin.get(f"/api/operacional/fichas?{P}").get_json()
    assert fic["total"] == 7 and fic["pacientes"] == 3
    prof = admin.get(f"/api/operacional/profissionais?{P}").get_json()["profissionais"]
    fisio = next(p for p in prof if p["nome"] == "Prof. Fisio")
    assert (fisio["visitas"], fisio["pacientes"], fisio["chave"]) == (3, 3, "id:10")
    pac = admin.get(f"/api/operacional/profissional?chave=id:10&{P}").get_json()
    assert [l[0] for l in pac["linhas"]] == ["Ana Souza", "Carla Dias", "Davi Rocha"]
    abr = admin.get(f"/api/operacional/abrangencia?{P}").get_json()
    assert abr["colunas"][2] == "Zona"


def test_painel_sem_dados_nao_quebra(admin):
    d = admin.get(f"/api/painel?{P}").get_json()
    assert d["kpis"]["pacientes_ativos"] == 0 and d["kpis"]["mortalidade"] == 0
    assert admin.get("/api/operacional/relatorios").get_json()["total"] == 0


def test_perfis_de_acesso(admin, criar_usuario):
    op = criar_usuario("operador1", "operacional")
    assert op.get("/").headers["Location"].endswith("/operacional")
    assert op.get("/operacional").status_code == 200
    assert op.get(f"/api/operacional/relatorios?{P}").status_code == 200
    for url in ("/painel", f"/api/painel?{P}", "/usuarios", "/integracao", "/api/usuarios"):
        assert op.get(url).status_code == 403, url

    gestor = criar_usuario("gestor2", "gestor")
    assert gestor.get("/").headers["Location"].endswith("/painel")
    assert gestor.get("/painel").status_code == 200 and gestor.get("/operacional").status_code == 200
    assert gestor.get("/usuarios").status_code == 403

    for url in ("/painel", "/operacional", "/usuarios", "/integracao", "/perfil"):
        assert admin.get("/banco").status_code == 404
        assert admin.get(url).status_code == 200, url


def test_login_csrf_e_troca_de_senha_obrigatoria(app):
    from tests.conftest import entrar
    from tst_gestao.db import connect
    with connect() as conn:
        conn.execute("UPDATE usuarios SET trocar_senha = 1 WHERE usuario = 'admin'")
    c = entrar(app, "admin", "admin")
    assert c.get("/painel").headers["Location"].endswith("/perfil")
    assert c.get("/api/painel").status_code == 403
    sem_token = app.test_client()
    assert sem_token.post("/login", data={"usuario": "admin", "senha": "admin"}).status_code == 400
    assert app.test_client().get("/painel").status_code == 302
    assert app.test_client().get("/api/painel").status_code == 401
    with connect() as conn:
        conn.execute("UPDATE usuarios SET trocar_senha = 0 WHERE usuario = 'admin'")


def test_usuarios_nao_podem_ficar_sem_admin(admin):
    lista = admin.get("/api/usuarios").get_json()
    eu = next(u for u in lista if u["usuario"] == "admin")
    r = admin.put(f"/api/usuarios/{eu['id']}", json={"usuario": "admin", "nome": "Adm", "nivel": "gestor", "ativo": 1})
    assert r.status_code == 400
    assert admin.post("/api/usuarios", json={"usuario": "x", "nome": "X", "nivel": "consulta", "senha": "segredo1"}).status_code == 400


def test_mapa_por_bairro(admin, dados):
    d = admin.get(f"/api/painel?{P}").get_json()
    parq = d["mapa"]["PARQUELANDIA"]  # Ana (Parquelândia) e Davi (PARQUELANDIA) caem no mesmo bairro
    assert parq["ativos"]["*"] == 2 and parq["em_terapia"]["FISIO"] == 2 and parq["em_terapia"]["PSICO"] == 1
    assert parq["pendentes"]["NUTRI"] == 1 and parq["relatorios"]["*"] == 1
    assert parq["visitas"]["*"] == 6 and parq["profissionais"]["*"] == 4  # Fisio, Fono, TO e Psico
    assert d["mapa"]["ALDEOTA"]["pendentes"]["SEM"] == 1  # Bruno: indicado e sem nenhuma visita
    lista = admin.get(f"/api/painel/detalhe?tipo=mapa&valor=em_terapia|PSICO|Parquelândia&{P}").get_json()
    assert [l[0] for l in lista["linhas"]] == ["Davi Rocha"]
    prof = admin.get(f"/api/painel/detalhe?tipo=mapa&valor=profissionais|*|PARQUELANDIA&{P}").get_json()
    assert prof["total"] == 4


def test_bairro_sem_cobertura(admin, dados):
    abr = admin.get(f"/api/operacional/abrangencia?{P}").get_json()
    assert abr["sem_cobertura"] == [{"bairro": "ALDEOTA", "pacientes": 1}]
    assert abr["indicados_bairro"]["PARQUELANDIA"] == 1


def test_orcamentos_dos_atendimentos_ativos(admin, dados):
    d = admin.get(f"/api/painel?{P}").get_json()
    orc = {o["chave"]: o["valor"] for o in d["orcamentos"]}
    # em 31/10: Bruno venceu em 15/10; Ana vence no próprio dia; Davi e o 2º atendimento da Ana não têm orçamento
    assert orc == {"vencido": 1, "vence_7": 1, "vence_30": 0, "em_dia": 0, "sem": 2}
    assert d["kpis"]["orcamentos_vencidos"] == 1
    lista = admin.get(f"/api/painel/detalhe?tipo=orcamento&valor=vencido&{P}").get_json()
    assert lista["linhas"][0][0] == "Bruno Lima" and lista["linhas"][0][4] == "ALDEOTA 1" and lista["linhas"][0][7] == -16


def test_zonas_de_atendimento(admin, dados):
    d = admin.get(f"/api/painel?{P}").get_json()
    assert d["zonas_info"]["6011"] == {"nome": "ALDEOTA 1", "bairros": ["ALDEOTA", "MEIRELES", "PARQUELANDIA"]}
    assert d["zonas"]["6011"]["ativos"]["*"] == 2 and d["zonas"]["6041"]["em_terapia"]["PSICO"] == 1
    lista = admin.get(f"/api/painel/detalhe?tipo=zona&valor=ativos|*|6011&{P}").get_json()
    assert sorted(l[0] for l in lista["linhas"]) == ["Ana Souza", "Bruno Lima"] and "ALDEOTA 1" in lista["titulo"]
    abr = admin.get(f"/api/operacional/abrangencia?{P}").get_json()
    z = {x["id"]: x for x in abr["zonas"]}
    assert (z["6011"]["indicados"], z["6011"]["profissionais"]) == (2, 2)
    assert (z["6041"]["indicados"], z["6041"]["profissionais"]) == (0, 4)
    assert ["Prof. Fisio", "FISIO", "ALDEOTA 1", "PARQUELANDIA", "FORTALEZA", 2, 2] in abr["linhas"]


def test_ficha_do_bairro(admin, dados, criar_usuario):
    f = admin.get(f"/api/bairro?nome=Parquelândia&{P}").get_json()
    assert f["bairro"] == "PARQUELANDIA" and f["oficial"] and [z["nome"] for z in f["zonas"]] == ["ALDEOTA 1", "MONTESE 1"]
    assert f["resumo"]["ativos"] == 2 and f["resumo"]["profissionais"] == 4 and f["resumo"]["relatorios"] == 1
    prof = {l[0]: l for l in f["profissionais"]["linhas"]}
    assert prof["Prof. Fisio"][2:5] == [2, 2, "20/10/2026"] and prof["Prof. Fisio"][5] == "id:10"
    pac = {l[0]: l for l in f["pacientes"]["linhas"]}
    assert pac["Ana Souza"][4] == "Nutrição" and "Prof. Fono (FONO)" in pac["Ana Souza"][5]
    assert pac["Davi Rocha"][3] == "FISIO · FONO · TO · PSICO"
    assert {t["sigla"] for t in f["terapias"]} == {"FISIO", "FONO", "TO", "NUTRI", "PSICO"}
    # o perfil Operacional também abre a ficha (mapa de cobertura) e o histórico de um paciente
    op = criar_usuario("operador4", "operacional")
    assert op.get(f"/api/bairro?nome=Aldeota&{P}").get_json()["resumo"]["pendentes"] == 1
    assert op.get("/api/historico?paciente=Davi Rocha").get_json()["total"] == 4
    assert op.get("/api/historico?paciente=Ninguém").status_code == 404
    assert op.get("/api/bairro").status_code == 400
