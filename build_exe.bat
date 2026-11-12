@echo off
setlocal EnableExtensions
chcp 65001 >nul
REM ===========================================================================
REM RPA Duvidas Financeiras - build do executavel (secao 7.1 da especificacao v0.3.0)
REM
REM   build_exe.bat [senha_das_abas_protegidas]
REM
REM Maquina de build: Windows, Python 3.11/3.12 64 bits, com
REM   python -m pip install -r requirements-build.txt
REM Passos: 1) testes  2) PyInstaller (onedir)  3) modelo da planilha e pastas
REM         4) versao.txt  5) RPA_DuvidasFinanceiras_v<versao>.zip
REM A janela fica aberta no final (sucesso ou erro). Para rodar sem pausa
REM (ex.: em outro script), defina antes: set BUILD_SEM_PAUSA=1
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
set "CODIGO=1"

echo Pasta do projeto: %RAIZ%
echo Python usado....: %PY%
echo.

REM --- Pre-requisitos -------------------------------------------------------
"%PY%" --version >nul 2>&1
if errorlevel 1 (
  echo ERRO: Python nao encontrado ^("%PY%"^). Instale o Python 3.11/3.12 64 bits
  echo       e marque "Add python.exe to PATH", ou crie o .venv nesta pasta.
  goto :fim
)
"%PY%" -c "import struct,sys; sys.exit(0 if struct.calcsize('P') == 8 else 1)"
if errorlevel 1 (
  echo ERRO: o build precisa de Python 64 bits ^(Office 64 bits na maquina do analista^).
  goto :fim
)
"%PY%" -c "import sys; print('Executavel......: ' + sys.executable); print('Versao..........: ' + sys.version.split()[0])"
echo.
"%PY%" -c "import importlib.util as u, sys; f=[m for m in ('PyInstaller','pytest','yaml','jinja2','bs4','openpyxl','keyring','win32com') if u.find_spec(m) is None]; print('Modulos faltando: ' + ', '.join(f)) if f else None; sys.exit(1 if f else 0)"
if errorlevel 1 (
  echo ERRO: dependencias nao instaladas NESTE Python ^(executavel acima^). Rode uma vez:
  echo       "%PY%" -m pip install -r requirements-build.txt
  echo       e confira se o pip terminou com "Successfully installed" sem erros.
  goto :fim
)
set "VERSAO="
set "ARQ_VERSAO=%TEMP%\rpa_duvidas_versao.txt"
"%PY%" -c "import rpa_duvidas; print(rpa_duvidas.__version__)" > "%ARQ_VERSAO%"
if errorlevel 1 goto :erro_versao
set /p VERSAO=<"%ARQ_VERSAO%"
del /q "%ARQ_VERSAO%" >nul 2>&1
if not defined VERSAO goto :erro_versao
echo Versao do pacote: %VERSAO%
echo.
set "PACOTE=dist\RPA_DuvidasFinanceiras"
set "ZIP=dist\RPA_DuvidasFinanceiras_v%VERSAO%.zip"

echo [1/5] Testes automatizados
"%PY%" -m pytest -q -p no:cacheprovider
if errorlevel 1 (
  echo ERRO: testes falharam - build cancelado.
  goto :fim
)

echo [2/5] PyInstaller ^(onedir^)
"%PY%" -m PyInstaller --noconfirm --clean rpa_duvidas.spec
if errorlevel 1 (
  echo ERRO: PyInstaller falhou - veja as mensagens acima.
  goto :fim
)

echo [3/5] Modelo da planilha e pastas do pacote
for %%d in (config modelos dados logs arquivo) do if not exist "%PACOTE%\%%d" mkdir "%PACOTE%\%%d"
"%PY%" scripts\gerar_modelo_config.py --saida "%PACOTE%\config\configuracao.xlsx" %SENHA_ARG%
if errorlevel 1 (
  echo ERRO: falha ao gerar config\configuracao.xlsx.
  goto :fim
)
if exist "docs\LEIA-ME_Instalacao.pdf" (
  copy /y "docs\LEIA-ME_Instalacao.pdf" "%PACOTE%\" >nul
) else (
  echo AVISO: docs\LEIA-ME_Instalacao.pdf nao encontrado - gere o PDF a partir de docs\12_guia_instalacao_v0.3.0.md
)

echo [4/5] versao.txt
"%PY%" scripts\gravar_versao.py "%PACOTE%\versao.txt"
if errorlevel 1 (
  echo ERRO: falha ao gravar versao.txt.
  goto :fim
)

echo [5/5] Compactando
if exist "%ZIP%" del /q "%ZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -LiteralPath $env:PACOTE -DestinationPath $env:ZIP -Force"
if errorlevel 1 (
  echo ERRO: falha ao compactar o pacote.
  goto :fim
)

echo.
echo Pacote gerado: %RAIZ%%ZIP%
echo Antes de instalar: testar em uma maquina sem Python ^(antivirus/SmartScreen^).
set "CODIGO=0"
goto :fim

:erro_versao
echo ERRO: nao foi possivel ler a versao do pacote rpa_duvidas ^(src\rpa_duvidas\__init__.py^).
goto :fim

:fim
echo.
if "%CODIGO%"=="0" (echo BUILD CONCLUIDO.) else (echo BUILD FALHOU - codigo %CODIGO%.)
if not defined BUILD_SEM_PAUSA pause
exit /b %CODIGO%
