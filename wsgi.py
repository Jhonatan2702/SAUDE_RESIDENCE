"""Ponto de entrada da hospedagem (Render): `gunicorn wsgi:app`.

Diferente do main.py (executável com janela e ícone de bandeja), aqui só existe o servidor web.
Use UM worker: a sincronização de hora em hora roda numa thread dentro do processo e não deve se repetir.
O atualizador do executável não é iniciado: no servidor, a versão nova chega pelo deploy (git push).
"""
import logging
import os

os.environ.setdefault("TST_HOSPEDADO", "1")

from tst_gestao.app import create_app  # noqa: E402
from tst_gestao.espelho import iniciar_agendamento  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
iniciar_agendamento(app.logger)  # espelha a URL agora e a cada hora
