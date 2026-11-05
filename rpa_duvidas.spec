# -*- mode: python ; coding: utf-8 -*-
# PyInstaller – RPA Dúvidas Financeiras v0.3.0 (seção 7.1 da especificação técnica)
#
#   python -m PyInstaller --noconfirm --clean rpa_duvidas.spec      (ou build_exe.bat)
#
# Modo ONEDIR, console. Gerar com Python 64 bits (Office 64 bits na máquina do analista).
# Os arquivos de configuração abaixo ficam em _internal\config (raiz_recursos); a
# planilha config\configuracao.xlsx, modelos\, dados\, logs\ e arquivo\ ficam ao lado
# do .exe (raiz_aplicacao) e são criados pelo build_exe.bat.
from pathlib import Path

RAIZ = Path(SPECPATH)

DADOS = [
    ("config/settings.yaml", "config"),
    ("config/categorias_ia.yaml", "config"),
    ("config/palavras_chave.yaml", "config"),
    ("config/tutoriais.yaml", "config"),
    ("config/fornecedores.yaml", "config"),
    ("config/ia_simulada.yaml", "config"),
    ("config/perfis/*.yaml", "config/perfis"),
    ("config/modelos/*.j2", "config/modelos"),
    ("config/prompts/*", "config/prompts"),
]

# Importações que o PyInstaller não acha sozinho (validar no primeiro build)
OCULTAS = ["win32timezone", "keyring.backends.Windows", "openpyxl.cell._writer"]

a = Analysis(
    [str(RAIZ / "scripts" / "rpa_exe.py")],
    pathex=[str(RAIZ / "src")],
    binaries=[],
    datas=[(str(RAIZ / origem), destino) for origem, destino in DADOS],
    hiddenimports=OCULTAS,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "pptx"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RPA_DuvidasFinanceiras",
    console=True,
    upx=False,
    debug=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="RPA_DuvidasFinanceiras")
