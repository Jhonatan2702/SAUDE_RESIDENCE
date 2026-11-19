@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Publicar atualizacao do TST-GESTAO
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERRO] Ambiente virtual nao encontrado. Execute install.bat primeiro.
  pause
  exit /b 1
)
"%PY%" -m pip install -q -r requirements-build.txt || goto :erro
"%PY%" ferramentas\publicar_atualizacao.py %* || goto :erro
pause
exit /b 0
:erro
echo.
echo [ERRO] A publicacao falhou. Confira as mensagens acima.
pause
exit /b 1
