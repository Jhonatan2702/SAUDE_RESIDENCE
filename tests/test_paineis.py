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
    rel = admin.get("/api/operacional/relatorios?comp=todas").get_json()
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


def test_relatorios_por_competencia(app, dados):
    from datetime import date

    from tst_gestao import operacional as op
    with app.app_context():
        # o único relatório pendente é da competência 09/2026
        atual = op.relatorios("atual", hoje=date(2026, 9, 15))
        assert (atual["total"], atual["anteriores"], atual["competencia_rotulo"]) == (1, 0, "09/2026")
        # em novembro ele sai da lista do mês, mas o aviso de anteriores não deixa o atraso sumir
        nov = op.relatorios("atual", hoje=date(2026, 11, 20))
        assert (nov["total"], nov["anteriores"], nov["total_geral"], nov["mais_antiga_geral"]) == (0, 1, 1, "09/2026")
        assert op.relatorios("anterior", hoje=date(2026, 10, 3))["total"] == 1
        # virada de ano: o mês anterior a janeiro é dezembro do ano passado
        assert op.relatorios("anterior", hoje=date(2027, 1, 5))["competencia_rotulo"] == "12/2026"
        todas = op.relatorios("todas", hoje=date(2026, 11, 20))
        assert (todas["total"], todas["anteriores"]) == (1, 0)
        assert op.relatorios("xyz", hoje=date(2026, 9, 1))["competencia"] == "atual"


def test_operacional_do_paciente(admin, dados):
    r = admin.get(f"/api/operacional/pacientes?{P}").get_json()
    assert r["colunas"][:4] == ["Paciente", "Atendimento", "Terapia", "Profissional"]
    fic = admin.get(f"/api/operacional/fichas?{P}").get_json()
    # mesmas visitas das fichas, agrupadas por paciente / terapia / profissional
    assert r["visitas"] == fic["total"] == sum(l[4] for l in r["linhas"]) and r["pacientes"] == fic["pacientes"]
    assert len({(l[1], l[2], l[3]) for l in r["linhas"]}) == len(r["linhas"])
    fisio = [l for l in r["linhas"] if l[3] == "Prof. Fisio"]
    assert sorted(l[0] for l in fisio) == ["Ana Souza", "Carla Dias", "Davi Rocha"] and {l[2] for l in fisio} == {"FISIO"}


def test_painel_sem_dados_nao_quebra(admin):
    d = admin.get(f"/api/painel?{P}").get_json()
    assert d["kpis"]["pacientes_ativos"] == 0 and d["kpis"]["mortalidade"] == 0
    assert admin.get("/api/operacional/relatorios").get_json()["total"] == 0


def test_perfis_de_acesso(admin, criar_usuario):
    op = criar_usuario("operador1", "operacional")
    assert op.get("/").headers["Location"].endswith("/operacional")
    assert op.get("/operacional").status_code == 200
    assert op.get(f"/api/operacional/relatorios?{P}").status_code == 200
    assert op.get(f"/api/operacional/pacientes?{P}").status_code == 200
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
    assert abr["sem_cobertura"] == [{"bairro": "ALDEOTA", "pacientes": 1, "cobrem": []}]  # ninguém em 180 dias
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


def _aba(f, id_):
    return next(a for a in f["abas"] if a["id"] == id_)


def test_ficha_do_bairro(admin, dados, criar_usuario):
    f = admin.get(f"/api/ficha/bairro?valor=Parquelândia&{P}").get_json()
    assert f["tipo"] == "bairro" and f["titulo"] == "PARQUELANDIA" and f["oficial"]
    assert [c["texto"] for c in f["chips"]] == ["Zona ALDEOTA 1", "Zona MONTESE 1"]
    k = {x["rotulo"]: x["valor"] for x in f["kpis"]}
    assert (k["Pacientes ativos"], k["Profissionais"], k["Relatórios pendentes"]) == (2, 4, 1)
    prof = {l[0]: l for l in _aba(f, "profissionais")["linhas"]}
    assert prof["Prof. Fisio"][2:8] == ["Atendendo no período", 2, 2, 2, "20/10/2026", "id:10"]
    assert _aba(f, "profissionais")["abrir"] == {"tipo": "profissional", "col": 7}
    # Prof. Nutri não visitou ninguém em outubro, mas atendeu a Ana (Parquelândia) em agosto: cobre o bairro
    assert prof["Prof. Nutri"][2:5] == ["Cobre o bairro", 1, 0]
    pac = {l[0]: l for l in _aba(f, "pacientes")["linhas"]}
    assert pac["Ana Souza"][4] == "Nutrição" and "Prof. Fono (FONO)" in pac["Ana Souza"][5]
    # o perfil Operacional também abre as fichas (mapa de cobertura, listas)
    op = criar_usuario("operador4", "operacional")
    assert op.get(f"/api/ficha/bairro?valor=Aldeota&{P}").get_json()["kpis"][2]["valor"] == 1
    assert op.get(f"/api/ficha/paciente?valor=Ninguém&{P}").status_code == 404
    assert op.get("/api/ficha/bairro").status_code == 400 and op.get("/api/ficha/outro?valor=x").status_code == 404


def test_ficha_do_profissional(admin, dados):
    f = admin.get(f"/api/ficha/profissional?valor=id:10&{P}").get_json()
    assert f["titulo"] == "Prof. Fisio" and f["chips"][0]["texto"] == "Fisioterapia"
    k = {x["rotulo"]: x["valor"] for x in f["kpis"]}
    assert (k["Visitas"], k["Pacientes"], k["Dias com visita"], k["Relatórios pendentes"]) == (3, 3, 2, 1)  # Ana e Davi no mesmo dia
    pacs = {l[0]: l for l in _aba(f, "pacientes")["linhas"]}
    assert set(pacs) == {"Ana Souza", "Carla Dias", "Davi Rocha"}
    assert pacs["Carla Dias"][8] == "Óbito" and pacs["Ana Souza"][8] == "Ativo"
    assert {l[0] for l in _aba(f, "regiao")["linhas"]} >= {"PARQUELANDIA"}
    assert _aba(f, "mensal")["itens"][0] == {"rotulo": "out/26", "valor": 3}
    # também abre pelo nome (ex.: vindo da lista de relatórios por profissional)
    assert admin.get(f"/api/ficha/profissional?valor=Prof. Nutri&{P}").get_json()["titulo"] == "Prof. Nutri"
    nutri = admin.get(f"/api/ficha/profissional?valor=id:12&{P}").get_json()
    pend = _aba(nutri, "pendencias")["linhas"]
    assert pend and pend[0][0] == "Ana Souza" and pend[0][1] == "Nutrição" and pend[0][4] == 77  # 15/08 → 31/10


def test_ficha_do_paciente(admin, dados):
    f = admin.get(f"/api/ficha/paciente?valor=ana souza&{P}").get_json()
    assert f["titulo"] == "Ana Souza" and f["chips"][0]["texto"] == "Ativo"
    assert "Terapia pendente" in [c["texto"] for c in f["chips"]]
    dados_ = dict(_aba(f, "dados")["pares"])
    assert dados_["Idade"] == "81 anos" and dados_["Zona de atendimento"] == "ALDEOTA 1" and dados_["Monitoramento com terapias"] == "Sim"
    assert dados_["Complexidade (pelas terapias, 90 dias)"] == "Intermediário"
    ter = {l[0]: l for l in _aba(f, "terapias")["linhas"]}
    assert ter["Fisioterapia"][1] == "Em dia" and ter["Nutrição"][1] == "Pendente há 77 dias"
    atend = _aba(f, "atendimentos")["linhas"]
    assert len(atend) == 2 and {a[0] for a in atend} == {"1", "2"}
    assert any(a[9] == "Vence em até 7 dias" for a in atend)
    assert len(_aba(f, "visitas")["linhas"]) == 3 and len(_aba(f, "relatorios")["linhas"]) == 1
    assert {l[0] for l in _aba(f, "profissionais")["linhas"]} == {"Prof. Fisio", "Prof. Fono", "Prof. Nutri"}


def test_busca_rapida(admin, dados, criar_usuario):
    r = criar_usuario("operador6", "operacional").get("/api/busca?q=souz").get_json()
    assert [p["nome"] for p in r["pacientes"]] == ["Ana Souza"]
    r = admin.get("/api/busca?q=prof. f").get_json()
    assert {p["nome"] for p in r["profissionais"]} == {"Prof. Fisio", "Prof. Fono"} and r["profissionais"][0]["chave"].startswith("id:")
    assert admin.get("/api/busca?q=a").get_json() == {"pacientes": [], "profissionais": []}


def test_altas_e_cobertura_sem_visita_no_periodo(admin, app, url_falsa):
    from tst_gestao import espelho
    url_falsa["payload"]["dados"].append(
        {"id": 6, "nmpaciente": "Eva Lima", "nmservico": "Monitoramento", "possuiterapias": "SIM", "status": "ALTA",
         "dataadmissao": "01/03/2026", "dataalta": "20/10/2026", "condicaoalta": "Alta de procedimento(s)", "nmoperadora": "CASSI",
         "bairro": "Varjota", "cidade": "Fortaleza",
         "visitas": [{"id": 109, "idadmission": 6, "datavisita": "10/06/2026", "nmespecialidade": "Fonoaudiologia",
                      "nmprofessional": "Prof. Fono", "idprofessional": 11}]})
    espelho.sincronizar()
    d = admin.get(f"/api/painel?{P}").get_json()
    assert d["mapa"]["VARJOTA"]["altas"]["*"] == 1
    assert d["mapa"]["VARJOTA"]["cobertura"]["*"] == 1  # ninguém visitou em outubro, mas o Prof. Fono cobre
    assert not d["mapa"]["VARJOTA"]["profissionais"].get("*")
    f = admin.get(f"/api/ficha/bairro?valor=Varjota&{P}").get_json()
    assert [l[0] for l in _aba(f, "altas")["linhas"]] == ["Eva Lima"]
    assert _aba(f, "profissionais")["linhas"][0][:3] == ["Prof. Fono", "FONO", "Cobre o bairro"]
    fono = admin.get(f"/api/ficha/profissional?valor=id:11&{P}").get_json()
    assert "Eva Lima" in [l[0] for l in _aba(fono, "altas")["linhas"]]
    regiao = {l[0]: l for l in _aba(fono, "regiao")["linhas"]}
    assert regiao["VARJOTA"][5] == "Cobre o bairro" and regiao["PARQUELANDIA"][5] == "Atendendo no período"
    det = admin.get(f"/api/painel/detalhe?tipo=mapa&valor=cobertura|*|VARJOTA&{P}").get_json()
    assert det["linhas"][0][0] == "Prof. Fono" and det["linhas"][0][2] == "Cobre o bairro"


def test_alta_encerra_o_ciclo_de_visitas(admin, app, url_falsa):
    """Visitas de um atendimento que já recebeu alta não geram pendência, mesmo se o paciente foi readmitido."""
    from tst_gestao import espelho
    url_falsa["payload"]["dados"] += [
        # Gil fez Fisio no atendimento 8 (alta em 05/10) e foi readmitido no 9, ainda sem visita de terapia
        {"id": 8, "nmpaciente": "Gil Prado", "nmservico": "Internação Domiciliar", "possuiterapias": "SIM", "status": "ALTA",
         "dataadmissao": "01/06/2026", "dataalta": "05/10/2026", "condicaoalta": "Alta de procedimento(s)", "nmoperadora": "CASSI",
         "bairro": "Centro", "cidade": "Fortaleza",
         "visitas": [{"id": 110, "idadmission": 8, "datavisita": "03/10/2026", "nmespecialidade": "Fisioterapia Respiratória e/ou Motora",
                      "nmprofessional": "Prof. Fisio", "idprofessional": 10}]},
        {"id": 9, "nmpaciente": "Gil Prado", "nmservico": "Internação Domiciliar", "possuiterapias": "SIM", "status": "EM ATENDIMENTO",
         "dataadmissao": "20/10/2026", "nmoperadora": "CASSI", "bairro": "Centro", "cidade": "Fortaleza", "visitas": []},
        # Hugo recebeu alta e não voltou: não pode aparecer em nenhuma pendência
        {"id": 10, "nmpaciente": "Hugo Melo", "nmservico": "Monitoramento", "possuiterapias": "SIM", "status": "ALTA",
         "dataadmissao": "01/05/2026", "dataalta": "10/10/2026", "condicaoalta": "Saida", "nmoperadora": "CASSI",
         "visitas": [{"id": 111, "idadmission": 10, "datavisita": "01/09/2026", "nmespecialidade": "Fonoaudiologia",
                      "nmprofessional": "Prof. Fono", "idprofessional": 11}]},
    ]
    espelho.sincronizar()
    pend = {tipo: {l[0] for l in admin.get(f"/api/painel/detalhe?tipo=pendentes&valor={tipo}&{P}").get_json()["linhas"]}
            for tipo in ("FISIO", "FONO", "SEM")}
    assert "Gil Prado" not in pend["FISIO"]  # a Fisio era do atendimento encerrado
    assert "Gil Prado" in pend["SEM"]        # o novo atendimento tem terapia indicada e nenhuma visita ainda
    assert "Hugo Melo" not in pend["FONO"] | pend["SEM"]
    gil = admin.get(f"/api/ficha/paciente?valor=Gil Prado&{P}").get_json()
    ter = {l[0]: l[1] for l in next(a for a in gil["abas"] if a["id"] == "terapias")["linhas"]}
    assert ter["Fisioterapia"] == "Encerrada com a alta de 05/10/2026"


def test_ultimo_acesso_registra_quem_ja_estava_logado(admin, criar_usuario):
    from tst_gestao.db import connect
    op = criar_usuario("operador7", "operacional")
    ler = lambda: {u["usuario"]: u["ultimo_acesso"] for u in admin.get("/api/usuarios").get_json()}["operador7"]
    # sessão aberta antes de a coluna existir: entra direto, sem passar pelo login
    with connect() as conn:
        conn.execute("UPDATE usuarios SET ultimo_acesso = NULL WHERE usuario = 'operador7'")
    assert op.get("/operacional").status_code == 200
    assert ler()
    # dentro de 5 minutos não grava de novo (poupa o banco)
    with connect() as conn:
        conn.execute("UPDATE usuarios SET ultimo_acesso = '2099-01-01T00:00:00' WHERE usuario = 'operador7'")
    op.get("/api/operacional/relatorios")
    assert ler() == "2099-01-01T00:00:00"
    # acesso antigo é atualizado na próxima página
    with connect() as conn:
        conn.execute("UPDATE usuarios SET ultimo_acesso = '2020-01-01T00:00:00' WHERE usuario = 'operador7'")
    op.get("/api/operacional/relatorios")
    assert ler() > "2020-01-01T00:00:00"
