"""Publica uma versão nova do TST-GESTÃO no GitHub Releases, assinada digitalmente.

Uso (pelo publicar_atualizacao.bat):
    publicar_atualizacao.bat "O que mudou nesta versão"

Passos:
1. Lê a versão em tst_gestao/versao.py (aumente VERSAO antes de publicar).
2. Gera dist/TST-GESTAO.exe com o PyInstaller.
3. Cria dist/versao.json com versão, data, notas, endereço, tamanho e SHA-256 do executável e ASSINA esse conteúdo
   com a chave privada (chaves/atualizacao_privada.pem).
4. Publica os dois arquivos como uma "release" no repositório de atualizações, usando o token do GitHub em
   chaves/github_token.txt (ou na variável GITHUB_TOKEN). Sem token, mostra o passo a passo para publicar pela web.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from tst_gestao import versao  # noqa: E402
from tst_gestao.atualizador import conferir_assinatura, conteudo_assinado  # noqa: E402

DIST = RAIZ / "dist"
EXE = DIST / "TST-GESTAO.exe"
MANIFESTO = DIST / "versao.json"
PRIVADA = RAIZ / "chaves" / "atualizacao_privada.pem"
TOKEN_ARQ = RAIZ / "chaves" / "github_token.txt"
API = "https://api.github.com"


def gerar_exe() -> None:
    print("Gerando o executável…")
    sep = ";" if os.name == "nt" else ":"
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
                    "--name", "TST-GESTAO", "--icon", str(RAIZ / "tst_gestao" / "static" / "tst.ico"),
                    "--add-data", f"{RAIZ / 'tst_gestao' / 'templates'}{sep}tst_gestao/templates",
                    "--add-data", f"{RAIZ / 'tst_gestao' / 'static'}{sep}tst_gestao/static",
                    "--hidden-import", "pystray._win32", "--distpath", str(DIST), "--workpath", str(RAIZ / "build"),
                    "--specpath", str(RAIZ / "build"), str(RAIZ / "main.py")], check=True, cwd=RAIZ)


def assinar(notas: str) -> dict:
    from cryptography.hazmat.primitives import serialization

    if not PRIVADA.exists():
        sys.exit("Chave privada não encontrada. Rode ferramentas/criar_chaves.py (só na primeira vez) ou restaure o backup da pasta chaves/.")
    corpo = EXE.read_bytes()
    tag = f"v{versao.VERSAO}"
    dados = {
        "versao": versao.VERSAO, "publicado_em": datetime.now().isoformat(timespec="seconds"), "notas": notas.strip(),
        "url": f"https://github.com/{versao.REPOSITORIO}/releases/download/{tag}/TST-GESTAO.exe",
        "tamanho": len(corpo), "sha256": hashlib.sha256(corpo).hexdigest(),
    }
    chave = serialization.load_pem_private_key(PRIVADA.read_bytes(), password=None)
    manifesto = {"dados": dados, "assinatura": base64.b64encode(chave.sign(conteudo_assinado(dados))).decode()}
    conferir_assinatura(manifesto)  # confere com a chave pública que vai dentro do executável
    MANIFESTO.write_text(json.dumps(manifesto, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Versão {versao.VERSAO} assinada: {len(corpo) / 1048576:.1f} MB · SHA-256 {dados['sha256'][:16]}…")
    return dados


def _gh(metodo: str, url: str, token: str, corpo: bytes | None = None, tipo: str = "application/json") -> dict:
    req = urllib.request.Request(url, data=corpo, method=metodo, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "Content-Type": tipo,
        "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "TST-GESTAO-publicador"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read() or b"{}")


def publicar(dados: dict, token: str) -> None:
    tag = f"v{dados['versao']}"
    try:
        _gh("GET", f"{API}/repos/{versao.REPOSITORIO}/releases/tags/{tag}", token)
        sys.exit(f"A versão {tag} já foi publicada. Aumente VERSAO em tst_gestao/versao.py.")
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
    print(f"Publicando {tag} em github.com/{versao.REPOSITORIO}…")
    try:
        rel = _gh("POST", f"{API}/repos/{versao.REPOSITORIO}/releases", token,
                  json.dumps({"tag_name": tag, "name": f"TST-GESTÃO {dados['versao']}", "body": dados["notas"]}).encode())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            sys.exit(f"Repositório {versao.REPOSITORIO} não encontrado (ou o token não tem acesso). Crie-o no GitHub como público.")
        raise
    envio = rel["upload_url"].split("{")[0]
    _gh("POST", f"{envio}?name=TST-GESTAO.exe", token, EXE.read_bytes(), "application/octet-stream")
    _gh("POST", f"{envio}?name=versao.json", token, MANIFESTO.read_bytes(), "application/json")
    print(f"Pronto: {rel['html_url']}")
    print("Os computadores instalados verão o aviso de nova versão em até 6 horas (ou ao clicar em Buscar atualizações).")


def main() -> None:
    notas = " ".join(a for a in sys.argv[1:] if not a.startswith("--"))
    if not notas:
        sys.exit('Informe o que mudou. Exemplo: publicar_atualizacao.bat "Ficha do bairro no mapa"')
    if "--sem-build" not in sys.argv:
        gerar_exe()
    dados = assinar(notas)
    token = os.environ.get("GITHUB_TOKEN") or (TOKEN_ARQ.read_text().strip() if TOKEN_ARQ.exists() else "")
    if "--sem-publicar" in sys.argv or not token:
        print("\nPara publicar pela web (sem token):")
        print(f"  1. Abra https://github.com/{versao.REPOSITORIO}/releases/new")
        print(f"  2. Tag: v{dados['versao']} · título: TST-GESTÃO {dados['versao']} · descrição: as novidades")
        print(f"  3. Anexe {EXE} e {MANIFESTO} e clique em Publish release.")
        return
    publicar(dados, token)


if __name__ == "__main__":
    main()
