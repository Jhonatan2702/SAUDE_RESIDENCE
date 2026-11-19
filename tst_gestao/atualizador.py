"""Atualização do executável: busca, confere a assinatura digital, baixa e troca a versão — sempre a pedido do admin.

Fluxo:
1. `verificar()` lê o versao.json publicado no GitHub Releases e confere a ASSINATURA (Ed25519) com a chave pública
   embutida em versao.py. Manifesto sem assinatura válida é ignorado.
2. `aplicar()` (só quando o admin clica em "Atualizar agora") baixa o executável, confere tamanho e SHA-256
   (que fazem parte do conteúdo assinado), renomeia o executável em uso para *.antigo.exe, coloca o novo no lugar
   e reinicia o aplicativo. A pasta dados/ não é tocada; a versão anterior fica guardada para voltar se precisar.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

from . import versao
from .banco import DATA_DIR

INTERVALO = 6 * 60 * 60
LIMITE_MANIFESTO = 100_000
LIMITE_EXECUTAVEL = 300_000_000
PASTA = DATA_DIR / "atualizacao"

_trava = threading.Lock()
_estado: dict = {"verificado_em": None, "disponivel": None, "erro": None, "aplicando": False}
_agenda_iniciada = False
ao_reiniciar = None  # definido por main.py: encerra servidor e ícone da bandeja


class ErroAtualizacao(RuntimeError):
    pass


def numero(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in str(v).strip().lstrip("vV").split("."))
    except ValueError:
        return (0,)


def executavel() -> Path | None:
    """Caminho do .exe em uso (None quando roda pelo código-fonte, onde não há o que trocar)."""
    return Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None


def conteudo_assinado(dados: dict) -> bytes:
    return json.dumps(dados, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def conferir_assinatura(manifesto: dict, chave_publica: str | None = None) -> dict:
    """Devolve os dados do manifesto se a assinatura for válida; senão, ErroAtualizacao."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    chave_publica = chave_publica if chave_publica is not None else versao.CHAVE_PUBLICA
    dados, assinatura = manifesto.get("dados"), manifesto.get("assinatura")
    if not isinstance(dados, dict) or not isinstance(assinatura, str) or not chave_publica:
        raise ErroAtualizacao("Arquivo de versão sem assinatura digital.")
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(chave_publica)).verify(
            base64.b64decode(assinatura), conteudo_assinado(dados))
    except (InvalidSignature, ValueError) as exc:
        raise ErroAtualizacao("Assinatura digital inválida: a atualização foi recusada.") from exc
    for campo in ("versao", "url", "sha256", "tamanho"):
        if not dados.get(campo):
            raise ErroAtualizacao(f"Arquivo de versão incompleto ({campo}).")
    if not str(dados["url"]).startswith("https://"):
        raise ErroAtualizacao("Endereço de download inseguro.")
    return dados


def _baixar(url: str, limite: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"TST-GESTAO/{versao.VERSAO}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        corpo = r.read(limite + 1)
    if len(corpo) > limite:
        raise ErroAtualizacao("Arquivo maior que o permitido.")
    return corpo


def estado() -> dict:
    with _trava:
        e = dict(_estado)
    e.update(versao_atual=versao.VERSAO, executavel=bool(executavel()), repositorio=versao.REPOSITORIO,
             assinatura_configurada=bool(versao.CHAVE_PUBLICA))
    return e


def verificar(url: str | None = None) -> dict:
    """Consulta se há versão nova (não baixa nem instala nada)."""
    agora = datetime.now().isoformat(timespec="seconds")
    try:
        manifesto = json.loads(_baixar(url or versao.URL_MANIFESTO, LIMITE_MANIFESTO).decode("utf-8-sig"))
        dados = conferir_assinatura(manifesto)
        novo = dados if numero(dados["versao"]) > numero(versao.VERSAO) else None
        with _trava:
            _estado.update(verificado_em=agora, disponivel=novo, erro=None)
    except Exception as exc:  # sem internet, repositório ainda vazio etc.: só registra
        msg = str(exc) if isinstance(exc, ErroAtualizacao) else (
            "Ainda não há versão publicada." if getattr(exc, "code", None) == 404 else "Não foi possível consultar as atualizações.")
        with _trava:
            _estado.update(verificado_em=agora, erro=msg)
            if isinstance(exc, ErroAtualizacao):  # arquivo inválido/adulterado: retira o aviso; falha de rede mantém o último válido
                _estado["disponivel"] = None
    return estado()


def preparar(dados: dict) -> Path:
    """Baixa o executável e confere tamanho e SHA-256 (ambos garantidos pela assinatura)."""
    corpo = _baixar(dados["url"], LIMITE_EXECUTAVEL)
    if len(corpo) != int(dados["tamanho"]) or hashlib.sha256(corpo).hexdigest() != dados["sha256"].lower():
        raise ErroAtualizacao("O arquivo baixado não confere com a versão assinada. Nada foi alterado.")
    PASTA.mkdir(parents=True, exist_ok=True)
    destino = PASTA / f"TST-GESTAO-{dados['versao']}.exe"
    destino.write_bytes(corpo)
    return destino


def aplicar() -> dict:
    """Baixa, confere e troca o executável; depois reinicia o aplicativo (chamado pelo botão do admin)."""
    atual = executavel()
    if not atual:
        raise ErroAtualizacao("A atualização automática funciona só no executável (TST-GESTAO.exe).")
    with _trava:
        dados, ocupado = _estado.get("disponivel"), _estado["aplicando"]
        if ocupado:
            raise ErroAtualizacao("Já existe uma atualização em andamento.")
        if not dados:
            raise ErroAtualizacao("Nenhuma versão nova disponível. Clique em Buscar atualizações.")
        _estado["aplicando"] = True
    try:
        novo = preparar(dados)
        antigo = atual.with_name(atual.stem + ".antigo.exe")
        antigo.unlink(missing_ok=True)
        os.replace(atual, antigo)         # o Windows permite renomear o .exe em uso
        try:
            shutil.copy2(novo, atual)
        except OSError:
            os.replace(antigo, atual)     # desfaz: volta a versão atual
            raise
    except Exception:
        with _trava:
            _estado["aplicando"] = False
        raise
    threading.Timer(1.5, _reiniciar, args=(atual,)).start()  # dá tempo da tela receber a resposta
    return {"ok": True, "versao": dados["versao"]}


def _reiniciar(exe: Path) -> None:
    subprocess.Popen([str(exe), "--apos-atualizacao"], cwd=str(exe.parent),
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    if ao_reiniciar:
        ao_reiniciar()


def limpar_downloads() -> None:
    """Na inicialização: apaga os downloads temporários. A versão anterior (*.antigo.exe) fica guardada até a
    próxima atualização; para voltar a ela, feche o aplicativo e renomeie o arquivo para TST-GESTAO.exe."""
    shutil.rmtree(PASTA, ignore_errors=True)


def iniciar_verificacao(logger) -> None:
    """Consulta periódica (não instala nada: só avisa o admin na tela)."""
    global _agenda_iniciada
    with _trava:
        if _agenda_iniciada:
            return
        _agenda_iniciada = True

    def executar() -> None:
        espera = threading.Event()
        espera.wait(30)
        while True:
            try:
                verificar()
            except Exception:
                logger.exception("Falha ao verificar atualizações.")
            espera.wait(INTERVALO)

    threading.Thread(target=executar, name="atualizacoes", daemon=True).start()
