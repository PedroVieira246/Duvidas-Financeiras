@echo off
chcp 65001 >nul
setlocal EnableExtensions
REM ===========================================================================
REM RPA Duvidas Financeiras - build do executavel (secao 7.1 da especificacao v0.3.0)
REM
REM   build_exe.bat [senha_das_abas_protegidas]
REM
REM Maquina de build: Windows, Python 3.11/3.12 64 bits, com
REM   python -m pip install -r requirements-build.txt
REM Passos: 1) testes  2) PyInstaller (onedir)  3) modelo da planilha e pastas
REM         4) versao.txt  5) RPA_DuvidasFinanceiras_v<versao>.zip
REM PENDENTE (T15): validar o .exe em uma maquina limpa, sem Python.
REM ===========================================================================
set "RAIZ=%~dp0"
cd /d "%RAIZ%"
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
set "PYTHONPATH=%RAIZ%src"
set "PYTHONIOENCODING=utf-8"
set "SENHA_ARG="
if not "%~1"=="" set "SENHA_ARG=--senha %~1"

"%PY%" -c "import struct,sys; sys.exit(0 if struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
  echo ERRO: o build precisa de Python 64 bits ^(Office 64 bits na maquina do analista^).
  exit /b 1
)
for /f "usebackq delims=" %%v in (`"%PY%" -c "import rpa_duvidas; print(rpa_duvidas.__version__)"`) do set "VERSAO=%%v"
if not defined VERSAO (
  echo ERRO: nao foi possivel ler a versao do pacote rpa_duvidas.
  exit /b 1
)
set "PACOTE=dist\RPA_DuvidasFinanceiras"
set "ZIP=dist\RPA_DuvidasFinanceiras_v%VERSAO%.zip"

echo [1/5] Testes automatizados
"%PY%" -m pytest -q -p no:cacheprovider
if errorlevel 1 (
  echo ERRO: testes falharam - build cancelado.
  exit /b 1
)

echo [2/5] PyInstaller ^(onedir^)
"%PY%" -m PyInstaller --noconfirm --clean rpa_duvidas.spec
if errorlevel 1 exit /b 1

echo [3/5] Modelo da planilha e pastas do pacote
for %%d in (config modelos dados logs arquivo) do if not exist "%PACOTE%\%%d" mkdir "%PACOTE%\%%d"
"%PY%" scripts\gerar_modelo_config.py --saida "%PACOTE%\config\configuracao.xlsx" %SENHA_ARG%
if errorlevel 1 exit /b 1
if exist "docs\LEIA-ME_Instalacao.pdf" (
  copy /y "docs\LEIA-ME_Instalacao.pdf" "%PACOTE%\" >nul
) else (
  echo AVISO: docs\LEIA-ME_Instalacao.pdf nao encontrado - gere o PDF a partir de docs\12_guia_instalacao_v0.3.0.md
)

echo [4/5] versao.txt
"%PY%" scripts\gravar_versao.py "%PACOTE%\versao.txt"
if errorlevel 1 exit /b 1

echo [5/5] Compactando
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%PACOTE%' -DestinationPath '%ZIP%' -Force"
if errorlevel 1 exit /b 1

echo.
echo Pacote gerado: %ZIP%
echo Antes de instalar: testar em uma maquina sem Python ^(antivirus/SmartScreen^).
exit /b 0
