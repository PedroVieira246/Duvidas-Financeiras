"""v0.3.2 – download automático do OneDrive e decisões de negócio do 1º teste.

Decisões da área (12/11/2026):
  1. a planilha aceita e-mail exato E domínio (@fornecedor.com.br);
  5. linha com "CNPJ não consta na base de fornecedores" continua fornecedor;
  9. arquivo de dependência só na nuvem é baixado antes de prosseguir.
"""
import io
import logging
import time

from pathlib import Path

import pytest

from conftest import criar_planilha_escritorios
from rpa_duvidas import nuvem
from rpa_duvidas.config import carregar
from rpa_duvidas.filtros import SEM_ESCRITORIO, ErroEscritorios, ler_planilha_escritorios
from rpa_duvidas.tutoriais import RepositorioTutoriais, TutorialIndisponivel


class NuvemFalsa:
    """Simula o OneDrive: o arquivo fica "só na nuvem" até ser lido por inteiro."""

    def __init__(self, monkeypatch, baixa=True):
        self.lidos = []
        self.nuvem = set()
        original = open

        def abrir(caminho, *a, **k):
            f = original(caminho, *a, **k)
            if baixa:
                self.lidos.append(str(caminho))
                self.nuvem.discard(str(caminho))
            return f

        monkeypatch.setattr(nuvem, "open", abrir, raising=False)

    def __call__(self, caminho):
        return str(caminho) in self.nuvem


@pytest.fixture()
def arquivo(tmp_path):
    p = tmp_path / "tutorial.pdf"
    p.write_bytes(b"%PDF-1.4 conteudo" * 1000)
    return p


def test_arquivo_local_nao_e_lido(arquivo, monkeypatch):
    falsa = NuvemFalsa(monkeypatch)
    assert nuvem.garantir_local(arquivo, somente_na_nuvem=falsa) is False and falsa.lidos == []


def test_arquivo_na_nuvem_e_baixado_antes_de_usar(arquivo, monkeypatch, caplog):
    falsa = NuvemFalsa(monkeypatch)
    falsa.nuvem.add(str(arquivo))
    with caplog.at_level(logging.INFO, logger="rpa_duvidas.nuvem"):
        assert nuvem.garantir_local(arquivo, somente_na_nuvem=falsa) is True
    assert falsa.lidos == [str(arquivo)] and "Baixado do OneDrive" in caplog.text


def test_onedrive_fechado_ou_sem_rede(arquivo, monkeypatch):
    def falha(*a, **k):
        raise OSError(362, "O provedor de nuvem não está em execução")

    monkeypatch.setattr(nuvem, "open", falha, raising=False)
    with pytest.raises(nuvem.ErroNuvem, match="só na nuvem.*download falhou.*provedor"):
        nuvem.garantir_local(arquivo, somente_na_nuvem=lambda p: True)


def test_download_lento_respeita_o_tempo_limite(arquivo, monkeypatch):
    def lento(*a, **k):
        time.sleep(5)
        return io.BytesIO(b"")

    monkeypatch.setattr(nuvem, "open", lento, raising=False)
    inicio = time.monotonic()
    with pytest.raises(nuvem.ErroNuvem, match="não terminou em 1 s"):
        nuvem.garantir_local(arquivo, somente_na_nuvem=lambda p: True, tempo_limite_s=1)
    assert time.monotonic() - inicio < 4                           # não trava o robô


def test_continua_na_nuvem_depois_da_leitura(arquivo):
    with pytest.raises(nuvem.ErroNuvem, match="não o manteve"):
        nuvem.garantir_local(arquivo, somente_na_nuvem=lambda p: True)


def test_download_desligado_mantem_o_erro_da_v031(arquivo):
    with pytest.raises(nuvem.ErroNuvem, match="download automático está desligado"):
        nuvem.garantir_local(arquivo, somente_na_nuvem=lambda p: True, baixar=False)


def test_configuracao_onedrive_vem_do_settings(projeto):
    try:
        cfg = carregar("demo", raiz=projeto)
        assert cfg.get("onedrive.baixar_automaticamente") is True and nuvem._CONF["tempo_limite_s"] == 120
        nuvem.configurar(False, 5)
        assert nuvem._CONF == {"baixar": False, "tempo_limite_s": 5.0}
    finally:
        nuvem.configurar(True, 120)


def test_tutorial_na_nuvem_e_baixado(arquivo, monkeypatch):
    falsa = NuvemFalsa(monkeypatch)
    falsa.nuvem.add(str(arquivo))
    monkeypatch.setattr("rpa_duvidas.tutoriais._somente_na_nuvem", falsa)
    repo = RepositorioTutoriais({"categorias": {"TUT_X": {"caminho_arquivo": str(arquivo)}}}, Path)
    assert repo.localizar("TUT_X").nome == "tutorial.pdf"


def test_preparar_baixa_todos_os_tutoriais_antes_do_ciclo(tmp_path, arquivo, monkeypatch):
    falsa = NuvemFalsa(monkeypatch)
    outro = tmp_path / "outro.pptx"
    outro.write_bytes(b"x" * 10)
    falsa.nuvem.update({str(arquivo), str(outro)})
    monkeypatch.setattr("rpa_duvidas.tutoriais._somente_na_nuvem", falsa)
    repo = RepositorioTutoriais({"categorias": {
        "A": {"caminho_arquivo": str(arquivo)}, "B": {"caminho_arquivo": str(outro)},
        "C": {"caminho_arquivo": str(tmp_path / "nao_existe.pdf")}, "D": {"link_formulario": "https://x"},
    }}, Path)
    ok, baixados, problemas = repo.preparar()
    assert (ok, baixados) == (2, 2) and len(problemas) == 1 and problemas[0].startswith("C: ")
    assert not falsa(arquivo) and not falsa(outro)


def test_planilha_de_escritorios_na_nuvem_e_baixada(tmp_path, monkeypatch):
    arq = criar_planilha_escritorios(tmp_path / "esc.xlsx", [("a@x.com.br", "X")])
    falsa = NuvemFalsa(monkeypatch)
    falsa.nuvem.add(str(arq))
    assert ler_planilha_escritorios(arq, somente_na_nuvem=falsa).escritorio("b@x.com.br") == "X"
    with pytest.raises(ErroEscritorios, match="Planilha de escritórios: Arquivo existe só na nuvem"):
        ler_planilha_escritorios(arq, somente_na_nuvem=lambda p: True)


# ---- decisões de negócio 1 e 5 -------------------------------------------- #
def test_decisao_1_email_exato_e_dominio(tmp_path):
    arq = criar_planilha_escritorios(tmp_path / "esc.xlsx", [
        ("fulano@escritorio-a.com.br", "A"),       # e-mail exato: libera o domínio corporativo
        ("@escritorio-b.com.br", "B"),             # só o domínio
        ("escritorio-c.adv.br", "C"),              # domínio sem @
        ("pessoa@gmail.com", "D"),                 # domínio público: só o endereço
    ])
    mapa = ler_planilha_escritorios(arq, somente_na_nuvem=lambda p: False)
    forn = mapa.lista_fornecedores()
    for remetente, esc in [("fulano@escritorio-a.com.br", "A"), ("outro@escritorio-a.com.br", "A"),
                           ("qualquer@escritorio-b.com.br", "B"), ("x@escritorio-c.adv.br", "C"),
                           ("pessoa@gmail.com", "D")]:
        assert forn.conhecido(remetente) and mapa.escritorio(remetente) == esc, remetente
    assert not forn.conhecido("outra.pessoa@gmail.com")


def test_decisao_5_cnpj_nao_consta_continua_fornecedor(tmp_path):
    arq = criar_planilha_escritorios(tmp_path / "esc.xlsx", [
        ("idn@sem-cnpj.com.br", "CNPJ não consta na base de fornecedores"),
    ])
    mapa = ler_planilha_escritorios(arq, somente_na_nuvem=lambda p: False)
    assert mapa.lista_fornecedores().conhecido("idn@sem-cnpj.com.br")
    assert mapa.lista_fornecedores().conhecido("outro@sem-cnpj.com.br")
    assert mapa.escritorio("idn@sem-cnpj.com.br") == SEM_ESCRITORIO
