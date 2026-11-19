"""Ponto de entrada da hospedagem (Render): `gunicorn wsgi:app`.

Diferente do main.py (executável com janela e ícone de bandeja), aqui só existe o servidor web.
Use UM worker: a sincronização de hora em hora roda numa thread dentro do processo e não deve se repetir.
O atualizador do executável não é iniciado: no servidor, a versão nova chega pelo deploy (git push).
"""
import logging
import os
import time

os.environ.setdefault("TST_HOSPEDADO", "1")
# O servidor do Render roda em UTC. Horário de Fortaleza (UTC-3, sem horário de verão) para os horários
# exibidos e para o "hoje" dos cálculos. Formato POSIX: funciona mesmo sem a base de fusos do sistema.
os.environ.setdefault("TZ", "<-03>3")
time.tzset()

from tst_gestao.app import create_app  # noqa: E402
from tst_gestao.espelho import iniciar_agendamento  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
app = create_app()
iniciar_agendamento(app.logger)  # espelha a URL agora e a cada hora
