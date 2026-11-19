"""Atualização assinada: só aceita o que foi assinado com a chave certa e nunca instala sem pedido."""
import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tst_gestao import atualizador as at
from tst_gestao import config, espelho, versao

EXE_NOVO = b"MZ conteudo do executavel novo"


@pytest.fixture
def chaves(monkeypatch):
    privada = Ed25519PrivateKey.generate()
    publica = base64.b64encode(privada.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    monkeypatch.setattr(versao, "CHAVE_PUBLICA", publica)
    with at._trava:
        at._estado.update(disponivel=None, erro=None, aplicando=False)
    return privada


def manifesto(privada, **mudar):
    dados = {"versao": "9.0.0", "publicado_em": "2026-11-19T10:00:00", "notas": "Novidades",
             "url": "https://github.com/x/y/releases/download/v9.0.0/TST-GESTAO.exe",
             "tamanho": len(EXE_NOVO), "sha256": hashlib.sha256(EXE_NOVO).hexdigest()}
    assinatura = base64.b64encode(privada.sign(at.conteudo_assinado(dados))).decode()
    dados.update(mudar)  # alterações DEPOIS de assinar simulam um arquivo adulterado
    return {"dados": dados, "assinatura": assinatura}


def test_so_aceita_o_que_foi_assinado(chaves):
    assert at.conferir_assinatura(manifesto(chaves))["versao"] == "9.0.0"
    with pytest.raises(at.ErroAtualizacao):
        at.conferir_assinatura(manifesto(chaves, url="https://outro-lugar/virus.exe"))
    with pytest.raises(at.ErroAtualizacao):
        at.conferir_assinatura(manifesto(Ed25519PrivateKey.generate()))  # assinado por outra pessoa
    with pytest.raises(at.ErroAtualizacao):
        at.conferir_assinatura({"dados": manifesto(chaves)["dados"]})  # sem assinatura


def test_verificar_avisa_mas_nao_instala(chaves, monkeypatch):
    monkeypatch.setattr(at, "_baixar", lambda url, limite: json.dumps(manifesto(chaves)).encode())
    e = at.verificar()
    assert e["disponivel"]["versao"] == "9.0.0" and e["erro"] is None
    monkeypatch.setattr(at, "_baixar", lambda url, limite: json.dumps(manifesto(chaves, versao="0.0.1")).encode())
    assert at.verificar()["disponivel"] is None  # versão antiga: nada a fazer
    monkeypatch.setattr(at, "_baixar", lambda url, limite: json.dumps(manifesto(chaves, notas="adulterado")).encode())
    e = at.verificar()
    assert e["disponivel"] is None and "Assinatura" in e["erro"]


def test_aplicar_troca_o_executavel_e_guarda_o_anterior(chaves, monkeypatch, tmp_path):
    exe = tmp_path / "TST-GESTAO.exe"
    exe.write_bytes(b"MZ versao antiga")
    reinicios = []
    monkeypatch.setattr(at, "executavel", lambda: exe)
    monkeypatch.setattr(at, "_reiniciar", lambda caminho: reinicios.append(caminho))
    monkeypatch.setattr(at.threading, "Timer", lambda _s, fn, args: type("T", (), {"start": lambda self: fn(*args)})())
    monkeypatch.setattr(at, "_baixar", lambda url, limite: json.dumps(manifesto(chaves)).encode() if url.endswith(".json") else EXE_NOVO)
    with pytest.raises(at.ErroAtualizacao):
        at.aplicar()  # nada disponível ainda: o admin precisa buscar antes
    at.verificar("https://x/versao.json")
    assert at.aplicar() == {"ok": True, "versao": "9.0.0"}
    assert exe.read_bytes() == EXE_NOVO and (tmp_path / "TST-GESTAO.antigo.exe").read_bytes() == b"MZ versao antiga"
    assert reinicios == [exe]


def test_download_corrompido_nao_altera_nada(chaves, monkeypatch, tmp_path):
    exe = tmp_path / "TST-GESTAO.exe"
    exe.write_bytes(b"MZ versao antiga")
    monkeypatch.setattr(at, "executavel", lambda: exe)
    monkeypatch.setattr(at, "_baixar", lambda url, limite: json.dumps(manifesto(chaves)).encode() if url.endswith(".json") else b"corrompido")
    at.verificar("https://x/versao.json")
    with pytest.raises(at.ErroAtualizacao):
        at.aplicar()
    assert exe.read_bytes() == b"MZ versao antiga" and not (tmp_path / "TST-GESTAO.antigo.exe").exists()


def test_pelo_codigo_fonte_nao_instala(chaves):
    with pytest.raises(at.ErroAtualizacao, match="executável"):
        at.aplicar()


def test_rotas_de_atualizacao_e_url(admin, criar_usuario, monkeypatch):
    assert admin.get("/api/atualizacao").get_json()["versao_atual"] == versao.VERSAO
    gestor = criar_usuario("gestor5", "gestor")
    assert gestor.get("/api/atualizacao").status_code == 403 and gestor.post("/api/atualizacao/aplicar").status_code == 403
    assert admin.post("/api/integracao/url", json={"url": "ftp://x"}).status_code == 400
    assert admin.post("/api/integracao/url", json={"url": "https://dados.cliente/api"}).status_code == 200
    assert config.ler()["url_dadosbi"] == "https://dados.cliente/api"
    monkeypatch.delenv("TST_DADOSBI_URL")
    assert espelho.url() == "https://dados.cliente/api"


def test_sem_url_configurada_avisa(app, monkeypatch):
    monkeypatch.delenv("TST_DADOSBI_URL")
    monkeypatch.setattr(config, "ler", lambda: {})
    with pytest.raises(RuntimeError):
        espelho.sincronizar()
    assert "não foi configurada" in espelho.status()["erro"]


def test_campo_da_url_fica_fixo_quando_configurado(admin, monkeypatch):
    monkeypatch.delenv("TST_DADOSBI_URL")
    monkeypatch.setattr(config, "ler", lambda: {})
    html = admin.get("/integracao").get_data(as_text=True)
    assert "url-alterar" not in html and "ainda não foi configurada" in html  # sem URL: campo livre para preencher
    monkeypatch.setattr(config, "ler", lambda: {"url_dadosbi": "https://dados.cliente/api"})
    html = admin.get("/integracao").get_data(as_text=True)
    assert 'value="https://dados.cliente/api"' in html and "readonly" in html and "Alterar endereço" in html
