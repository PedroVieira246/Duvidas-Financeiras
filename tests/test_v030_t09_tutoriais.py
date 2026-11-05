"""v0.3.0 – T09: tutorial pelo caminho completo e link do Forms (D07 – seção 5.6)."""
import json

import pytest

from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.modelos import Acao, Categoria, MotivoManual, Status
from rpa_duvidas.tutoriais import RepositorioTutoriais, TutorialIndisponivel

FORNECEDOR = "ana@fornecedor-exemplo.com.br"


def _repo(cfg):
    return RepositorioTutoriais(cfg.yaml_referenciado("tutoriais.arquivo"), lambda v: cfg.caminho(v, eh_valor=True))


def _email(entrada, assunto, corpo):
    (entrada / "001.json").write_text(json.dumps({
        "id_mensagem": "<1@x>", "remetente": FORNECEDOR, "nome_remetente": "Ana", "assunto": assunto,
        "corpo_texto": corpo, "data_recebimento": "2026-11-03T09:00:00"}), encoding="utf-8")


def _rodar(cfg):
    robo = montar_dependencias(cfg)
    try:
        [r] = robo.executar_ciclo().resultados
    finally:
        robo.registro.fechar()
    return r


def test_caminho_completo_do_arquivo_oficial(projeto_cal, cfg_cal):
    t = _repo(cfg_cal).localizar(Categoria.TUT_REEMBOLSO)
    assert t.caminho == projeto_cal / "dados_teste/tutoriais/Reembolso/Como abrir um chamado de Reembolso.pptx"
    assert t.descricao == "Reembolso"                                # nome da aba Categorias
    assert all(ok for _, ok, _ in _repo(cfg_cal).verificar_todos())


def test_caminho_aceita_userprofile(projeto_cal, cfg_cal, monkeypatch):
    monkeypatch.setenv("USERPROFILE", str(projeto_cal))
    conf = cfg_cal.dados["_inline"]["tutoriais.arquivo"]["categorias"]["TUT_CONNECT"]
    conf["caminho_arquivo"] = "%USERPROFILE%/dados_teste/tutoriais/04. Suporte Connect/Tutorial - Acesso ao Connect.pptx"
    assert _repo(cfg_cal).localizar(Categoria.TUT_CONNECT).nome == "Tutorial - Acesso ao Connect.pptx"


def test_arquivo_ausente_vira_erro_no_ciclo(projeto_cal, cfg_cal, entrada):
    cfg_cal.dados["_inline"]["tutoriais.arquivo"]["categorias"]["TUT_REEMBOLSO"]["caminho_arquivo"] = "nao/existe.pptx"
    with pytest.raises(TutorialIndisponivel, match="não encontrado"):
        _repo(cfg_cal).localizar(Categoria.TUT_REEMBOLSO)
    _email(entrada, "Reembolso", "preciso de reembolso")
    r = _rodar(cfg_cal)
    assert r.status == Status.ERRO and "TutorialIndisponivel" in r.erro


def test_arquivo_so_na_nuvem(projeto_cal, cfg_cal, monkeypatch):
    monkeypatch.setattr("rpa_duvidas.tutoriais._somente_na_nuvem", lambda p: True)
    with pytest.raises(TutorialIndisponivel, match="só na nuvem"):
        _repo(cfg_cal).localizar(Categoria.TUT_REEMBOLSO)


def test_limite_por_categoria(projeto_cal, cfg_cal):
    cfg_cal.dados["_inline"]["tutoriais.arquivo"]["categorias"]["TUT_REEMBOLSO"]["limite_mb"] = 0.001
    with pytest.raises(TutorialIndisponivel, match="excede o limite"):
        _repo(cfg_cal).localizar(Categoria.TUT_REEMBOLSO)


def test_caminho_vazio(projeto_cal, cfg_cal):
    cfg_cal.dados["_inline"]["tutoriais.arquivo"]["categorias"]["TUT_CADASTRO"]["caminho_arquivo"] = ""
    with pytest.raises(TutorialIndisponivel, match="sem caminho"):
        _repo(cfg_cal).localizar(Categoria.TUT_CADASTRO)


def test_link_do_forms_da_planilha_vai_na_resposta(projeto_cal, cfg_cal, entrada):
    _email(entrada, "Pedido de compra", "preciso do pedido de compra")
    r = _rodar(cfg_cal)
    assert r.acao == Acao.RESPONDER_FORMS
    saida = projeto_cal / "dados_teste" / "caixa_simulada" / "saida"
    [resp] = [json.loads(p.read_text(encoding="utf-8")) for p in saida.glob("*_RESPOSTA.json")]
    assert "https://forms.office.com/r/EXEMPLO-PO" in resp["corpo_html"]
    assert "LINK-A-DEFINIR" not in resp["corpo_html"]


def test_link_vazio_trata_forms_po_como_manual(projeto_cal, entrada):
    from conftest import preencher_calibracao, usar_caixa_simulada
    from rpa_duvidas.config import carregar

    preencher_calibracao(projeto_cal, link_forms=None)
    cfg = usar_caixa_simulada(carregar("calibracao", raiz=projeto_cal))
    assert cfg.erros_xlsx == [] and cfg.get("respostas.link_forms_po") == ""
    _email(entrada, "Pedido de compra", "preciso do pedido de compra")
    r = _rodar(cfg)
    assert r.classificacao.categoria == Categoria.MANUAL
    assert r.classificacao.motivo_manual == MotivoManual.SEM_RESPOSTA_PADRAO
    assert r.classificacao.detalhes["categoria_sugerida"] == Categoria.FORMS_PO
