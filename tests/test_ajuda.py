"""Ajuda e tours guiados: a página abre para cada perfil e todo alvo dos tours existe na tela."""
import re
from pathlib import Path

GUIA = (Path(__file__).parent.parent / "tst_gestao" / "static" / "guia.js").read_text(encoding="utf-8")
PAGINAS = {"painel": "/painel", "operacional": "/operacional", "integracao": "/integracao", "usuarios": "/usuarios"}


def tours():
    """{id do tour: [seletores #id usados como alvo]}"""
    saida = {}
    partes = re.split(r"\n  '([\w:-]+)': \{", GUIA)
    for nome, corpo in zip(partes[1::2], partes[2::2]):
        saida[nome] = re.findall(r"alvo: '#([\w-]+)", corpo)
    return saida


def test_todo_alvo_de_tour_existe_na_tela(admin):
    t = tours()
    assert len(t) >= 15 and "boas-vindas" in t and "painel:terapias" in t
    html = {pag: admin.get(url).get_data(as_text=True) for pag, url in PAGINAS.items()}
    for nome, ids in t.items():
        pagina = nome.split(":")[0]
        alvos = [html[pagina]] if pagina in html else list(html.values())
        for i in ids:
            assert any(f'id="{i}"' in h for h in alvos), f"tour {nome}: #{i} não existe na tela"


def test_ajuda_por_perfil(admin, criar_usuario):
    a = admin.get("/ajuda").get_data(as_text=True)
    assert "Glossário" in a and "Mapa por bairro" in a and "?tour=painel:mapa" in a
    op = criar_usuario("operador3", "operacional").get("/ajuda")
    texto = op.get_data(as_text=True)
    assert op.status_code == 200 and "Região de abrangência" in texto and "?tour=painel:" not in texto
    assert 'id="btn-tour"' in admin.get("/painel").get_data(as_text=True)
