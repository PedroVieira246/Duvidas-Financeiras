@echo off
chcp 65001 >nul
REM Atalho no Windows: rpa.bat executar --perfil dev
REM Usa o ambiente virtual .venv se existir.
setlocal
set "RAIZ=%~dp0"
set "PYTHONPATH=%RAIZ%src;%PYTHONPATH%"
set "PYTHONIOENCODING=utf-8"
if exist "%RAIZ%.venv\Scripts\python.exe" (
  "%RAIZ%.venv\Scripts\python.exe" -m rpa_duvidas %*
) else (
  python -m rpa_duvidas %*
)
exit /b %ERRORLEVEL%
