"""Versão do TST-GESTÃO e de onde vêm as atualizações.

Para publicar uma versão nova: aumente VERSAO e rode publicar_atualizacao.bat (veja o README).
"""
VERSAO = "2.1.1"

# Repositório PÚBLICO só com os executáveis (sem código-fonte e sem dados): github.com/<REPOSITORIO>/releases
REPOSITORIO = "Jhonatan2702/tst-gestao-atualizacoes"
URL_MANIFESTO = f"https://github.com/{REPOSITORIO}/releases/latest/download/versao.json"

# Chave pública da assinatura digital (Ed25519). Só executáveis assinados com a chave privada correspondente,
# que fica apenas no computador de quem publica (pasta chaves/), são aceitos como atualização.
CHAVE_PUBLICA = "/1F+X4lWa5gBTBRlne5v4R2y+jVOKqU6E1GtrX5nDjU="
