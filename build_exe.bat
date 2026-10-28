@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title Gerar TST-GESTAO.exe
echo ============================================
echo   TST-GESTAO - Geracao do executavel
echo ============================================
echo.

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERRO] Ambiente virtual nao encontrado.
  echo Execute install.bat primeiro.
  pause
  exit /b 1
)

echo Instalando dependencias de empacotamento...
"%PY%" -m pip install -r requirements-build.txt || goto :erro

echo.
echo Gerando executavel...
"%PY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name TST-GESTAO ^
  --icon "tst_gestao\static\tst.ico" ^
  --add-data "tst_gestao\templates;tst_gestao\templates" ^
  --add-data "tst_gestao\static;tst_gestao\static" ^
  --collect-all oracledb ^
  --hidden-import pystray._win32 ^
  --hidden-import pyodbc ^
  main.py || goto :erro

echo.
echo ============================================
echo   Executavel criado em dist\TST-GESTAO.exe
echo   Os dados serao gravados em dist\dados.
echo ============================================
pause
exit /b 0

:erro
echo.
echo [ERRO] A geracao falhou. Confira as mensagens acima.
pause
exit /b 1
