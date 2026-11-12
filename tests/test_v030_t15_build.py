"""v0.3.0 – T15: configuração do PyInstaller e build_exe.bat.

O build real e o teste em máquina limpa (sem Python) ficam PENDENTES: precisam de Windows.
Aqui se confere que o pacote leva tudo o que o perfil calibracao precisa."""
import ast
import glob
import os
import shutil
import subprocess
import sys

import pytest

from conftest import RAIZ, preencher_calibracao, usar_caixa_simulada


def _dados_do_spec():
    arvore = ast.parse((RAIZ / "rpa_duvidas.spec").read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, ast.Assign) and getattr(no.targets[0], "id", "") in ("DADOS", "OCULTAS"):
            yield no.targets[0].id, ast.literal_eval(no.value)


def test_spec_onedir_com_importacoes_ocultas():
    spec = dict(_dados_do_spec())
    assert set(spec["OCULTAS"]) == {"win32timezone", "keyring.backends.Windows", "openpyxl.cell._writer"}
    texto = (RAIZ / "rpa_duvidas.spec").read_text(encoding="utf-8")
    assert "COLLECT(" in texto and "exclude_binaries=True" in texto       # onedir
    assert 'name="RPA_DuvidasFinanceiras"' in texto and "console=True" in texto
    for origem, _ in spec["DADOS"]:
        assert glob.glob(str(RAIZ / origem)), origem


def test_pacote_so_com_os_arquivos_do_spec_carrega_o_perfil_calibracao(tmp_path, monkeypatch):
    """Simula o _internal do onedir só com os arquivos listados em DADOS."""
    from rpa_duvidas.__main__ import montar_dependencias
    from rpa_duvidas.config import carregar

    app = tmp_path / "RPA_DuvidasFinanceiras"
    internos = app / "_internal"
    for origem, destino in dict(_dados_do_spec())["DADOS"]:
        (internos / destino).mkdir(parents=True, exist_ok=True)
        for arq in glob.glob(str(RAIZ / origem)):
            shutil.copy(arq, internos / destino)
    projeto = tmp_path / "projeto"
    shutil.copytree(RAIZ / "config", projeto / "config", copy_function=shutil.copyfile)
    shutil.copytree(RAIZ / "dados_teste" / "tutoriais", app / "dados_teste" / "tutoriais", copy_function=shutil.copyfile)
    preencher_calibracao(projeto, destino=app / "config" / "configuracao.xlsx")
    shutil.copy(projeto / "dados_teste" / "escritorios.xlsx", app / "dados_teste" / "escritorios.xlsx")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app / "RPA_DuvidasFinanceiras.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(internos), raising=False)
    monkeypatch.delenv("RPA_PERFIL", raising=False)
    cfg = usar_caixa_simulada(carregar())
    assert cfg.perfil == "calibracao" and cfg.validar() == []
    robo = montar_dependencias(cfg)
    try:
        assert robo.executar_ciclo().falha == ""
        assert robo.respostas.existe("TUT_REEMBOLSO") and robo.respostas.existe("TEXTO")
    finally:
        robo.registro.fechar()
    assert (app / "dados" / "estado.db").exists()                       # dados ao lado do .exe


def test_build_exe_bat_em_crlf_com_os_cinco_passos():
    bruto = (RAIZ / "build_exe.bat").read_bytes()
    assert b"\r\n" in bruto and b"\n" not in bruto.replace(b"\r\n", b"")
    texto = bruto.decode("utf-8")
    for passo in ("pytest", "PyInstaller --noconfirm --clean rpa_duvidas.spec", "gerar_modelo_config.py",
                  "gravar_versao.py", "Compress-Archive"):
        assert passo in texto, passo
    assert "struct.calcsize('P') == 8" in texto                             # Python 64 bits


def test_entrada_do_exe_e_versao_txt(tmp_path):
    env = {**os.environ, "PYTHONPATH": str(RAIZ / "src")}
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "rpa_exe.py"), "--version"], capture_output=True,
                       text=True, env=env, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "0.3.3"
    destino = tmp_path / "versao.txt"
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "gravar_versao.py"), str(destino)], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 0
    linhas = destino.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "versao=0.3.3" and linhas[1].startswith("data=") and linhas[2].startswith("commit=")
