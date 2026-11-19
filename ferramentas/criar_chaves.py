"""Cria (uma única vez) o par de chaves da assinatura digital das atualizações.

- chaves/atualizacao_privada.pem: fica SÓ no computador de quem publica. Faça backup em local seguro;
  sem ela, nenhuma atualização nova será aceita pelos computadores já instalados.
- A chave pública é gravada em tst_gestao/versao.py (vai junto no executável).
"""
import base64
import re
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

RAIZ = Path(__file__).resolve().parent.parent
PRIVADA = RAIZ / "chaves" / "atualizacao_privada.pem"
VERSAO = RAIZ / "tst_gestao" / "versao.py"

if PRIVADA.exists() and "--substituir" not in sys.argv:
    sys.exit(f"Já existe uma chave em {PRIVADA}. Use --substituir só se tiver certeza (as instalações atuais deixarão de aceitar atualizações).")
chave = Ed25519PrivateKey.generate()
PRIVADA.parent.mkdir(exist_ok=True)
PRIVADA.write_bytes(chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
publica = base64.b64encode(chave.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
texto = re.sub(r'^CHAVE_PUBLICA = ".*"$', f'CHAVE_PUBLICA = "{publica}"', VERSAO.read_text(encoding="utf-8"), flags=re.M)
VERSAO.write_text(texto, encoding="utf-8")
print("Chave privada:", PRIVADA)
print("Chave pública gravada em tst_gestao/versao.py:", publica)
