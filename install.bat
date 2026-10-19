@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Instalador TST-GESTAO
echo ============================================
echo   TST-GESTAO - Instalacao
echo ============================================
echo.

rem 1) Localiza o Python 3.10+ (launcher "py" ou "python")
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" >nul 2>&1 && set "PY=python"
)

rem 2) Se nao houver, instala via winget
if not defined PY (
  echo Python 3.10+ nao encontrado. Tentando instalar via winget...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  py -3 -c "import sys" >nul 2>&1 && set "PY=py -3"
  if not defined PY (
    echo.
    echo [ERRO] Nao foi possivel instalar o Python automaticamente.
    echo Instale em https://www.python.org/downloads/ ^(marque "Add python.exe to PATH"^) e execute este arquivo novamente.
    pause & exit /b 1
  )
)

rem 3) Ambiente virtual + dependencias
if not exist ".venv\Scripts\pythonw.exe" (
  echo Criando ambiente virtual...
  %PY% -m venv .venv || goto :erro
)
echo Instalando dependencias ^(pode levar alguns minutos^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :erro

rem 4) Atalhos e icone (Area de Trabalho + pasta do projeto)
".venv\Scripts\python.exe" criar_atalhos.py || goto :erro

echo.
echo ============================================
echo   Instalacao concluida!
echo   Abra o atalho TST-GESTAO na Area de Trabalho.
echo   Primeiro acesso: admin / admin
echo   Para SQL Server instale tambem o "ODBC Driver 17/18 for SQL Server".
echo ============================================
choice /c SN /m "Abrir o TST-GESTAO agora"
if errorlevel 2 exit /b 0
start "" ".venv\Scripts\pythonw.exe" main.py
exit /b 0

:erro
echo.
echo [ERRO] A instalacao falhou. Verifique a conexao com a internet e tente novamente.
pause
exit /b 1
