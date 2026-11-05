"""v0.3.0 – T04: raiz da aplicação × raiz dos recursos (PyInstaller simulado)."""
import shutil
import sys
from pathlib import Path

import pytest

from conftest import RAIZ, preencher_calibracao
from rpa_duvidas import config
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.config import carregar, perfil_padrao, raiz_aplicacao, raiz_recursos
from rpa_duvidas.modelos import EmailRecebido


@pytest.fixture()
def exe(tmp_path, monkeypatch):
    """Simula o onedir: <app>/RPA_DuvidasFinanceiras.exe + <app>/_internal (recursos)."""
    app = tmp_path / "RPA_DuvidasFinanceiras"
    internos = app / "_internal"
    shutil.copytree(RAIZ / "config", internos / "config")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(app / "RPA_DuvidasFinanceiras.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(internos), raising=False)
    monkeypatch.delenv("RPA_PERFIL", raising=False)
    return app


def test_fora_do_executavel_as_duas_raizes_sao_o_projeto(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    assert raiz_aplicacao() == RAIZ and raiz_recursos() == RAIZ
    monkeypatch.delenv("RPA_PERFIL", raising=False)
    assert perfil_padrao() == "dev"


def test_no_executavel_aplicacao_e_a_pasta_do_exe(exe):
    assert raiz_aplicacao() == exe.resolve()
    assert raiz_recursos() == exe / "_internal"
    assert perfil_padrao() == "calibracao"


def test_carregar_le_recursos_do_pacote_e_planilha_ao_lado_do_exe(exe):
    # a planilha é gerada com o projeto e copiada para <app>/config, como no pacote entregue
    projeto = exe.parent / "projeto"
    shutil.copytree(RAIZ / "config", projeto / "config")
    shutil.copytree(RAIZ / "dados_teste" / "tutoriais", projeto / "dados_teste" / "tutoriais")
    preencher_calibracao(projeto, destino=exe / "config" / "configuracao.xlsx")
    cfg = carregar()                                   # perfil padrão do .exe: calibracao
    assert cfg.perfil == "calibracao" and cfg.erros_xlsx == []
    assert cfg.raiz == exe.resolve() and cfg.recursos == exe / "_internal"
    # recursos empacotados são achados no _internal; dados e logs ficam ao lado do .exe
    assert cfg.caminho("respostas.pasta_modelos") == exe / "_internal" / "config" / "modelos"
    assert cfg.caminho("registro.banco_estado") == exe.resolve() / "dados" / "estado.db"
    assert cfg.caminho("registro.pasta_logs") == exe.resolve() / "logs"
    assert cfg.caminho("arquivamento.raiz") == exe.resolve() / "arquivo"


def test_sem_planilha_ao_lado_do_exe(exe):
    with pytest.raises(config.ErroConfiguracao, match="configuracao.xlsx"):
        carregar()


def test_modelo_personalizado_substitui_o_padrao(projeto):
    cfg = carregar("demo", raiz=projeto)
    pasta = projeto / "modelos"
    pasta.mkdir()
    (pasta / "TUT_REEMBOLSO.html.j2").write_text(
        '{% extends "_base.html.j2" %}{% block conteudo %}<p>TEXTO LOCAL {{ nome_arquivo }}</p>{% endblock %}',
        encoding="utf-8")
    robo = montar_dependencias(cfg)
    try:
        email = EmailRecebido("<1@x>", "a@fornecedor-exemplo.com.br", "A", "Reembolso", "", "", None)
        html = robo.respostas.resposta(email, "TUT_REEMBOLSO", nome_arquivo="t.pptx")
        assert "TEXTO LOCAL t.pptx" in html                       # o da pasta modelos\ vence
        assert "acesso ao portal Connect" in robo.respostas.resposta(email, "TUT_CONNECT", nome_arquivo="c")
    finally:
        robo.registro.fechar()
