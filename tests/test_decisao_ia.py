"""E5 – regras de decisão D1 a D7, na ordem da seção 6.1."""
import pytest
import yaml

from conftest import RAIZ, json_ia
from rpa_duvidas.classificacao.decisao_ia import CategoriasIA, decidir
from rpa_duvidas.classificacao.validacao_ia import validar_objeto
from rpa_duvidas.modelos import Acao, Categoria, MotivoManual

LIMITE = 0.80


@pytest.fixture(scope="module")
def cats():
    return CategoriasIA.de_dict(yaml.safe_load((RAIZ / "config" / "categorias_ia.yaml").read_text(encoding="utf-8")))


def _resp(cats, **kw):
    r = validar_objeto(json_ia(**kw), cats.codigos_validos, cats.tutoriais_validos(), cats.sinais_excecao)
    assert r.valida, r.erros
    return r.resposta


def test_configuracao_inicial_da_secao_6_4(cats):
    c = cats.categorias
    assert (c["C03"].tutorial, c["C03"].resposta_automatica) == ("TUT_UPLOAD_NF", True)
    assert (c["C05"].tutorial, c["C05"].resposta_automatica) == ("TUT_CADASTRO", True)
    assert (c["C06"].tutorial, c["C06"].resposta_automatica) == ("TUT_REEMBOLSO", False)
    assert c["C07"].tutorial is None and c["C99"].tutorial is None


def test_resposta_automatica_quando_nenhuma_regra_barra(cats):
    d = decidir(_resp(cats), cats, LIMITE)
    assert (d.acao, d.categoria, d.motivo_manual, d.regra) == (Acao.RESPONDER_TUTORIAL, Categoria.TUT_UPLOAD_NF, None, "RESPONDER")
    d = decidir(_resp(cats, categoria="C05", tutorial="TUT_CADASTRO"), cats, LIMITE)
    assert d.categoria == Categoria.TUT_CADASTRO


@pytest.mark.parametrize("falha", [MotivoManual.IA_INDISPONIVEL, MotivoManual.RESPOSTA_IA_INVALIDA])
def test_d1_falha_da_ia(cats, falha):
    d = decidir(None, cats, LIMITE, falha)
    assert (d.categoria, d.motivo_manual, d.regra) == (Categoria.MANUAL, falha, "D1")


def test_d1_sem_resposta_e_sem_motivo_vira_invalida(cats):
    assert decidir(None, cats, LIMITE).motivo_manual == MotivoManual.RESPOSTA_IA_INVALIDA


@pytest.mark.parametrize("codigo, motivo", [("C07", MotivoManual.SEM_RESPOSTA_PADRAO), ("C99", MotivoManual.NAO_IDENTIFICADO)])
def test_d2_categoria_sem_tutorial(cats, codigo, motivo):
    d = decidir(_resp(cats, categoria=codigo, tutorial=None, confianca=0.99), cats, LIMITE)
    assert (d.motivo_manual, d.regra) == (motivo, "D2")


def test_d3_baixa_confianca(cats):
    d = decidir(_resp(cats, confianca=0.79), cats, LIMITE)
    assert (d.motivo_manual, d.regra) == (MotivoManual.BAIXA_CONFIANCA, "D3")
    assert decidir(_resp(cats, confianca=0.80), cats, LIMITE).acao == Acao.RESPONDER_TUTORIAL   # limite inclusivo


def test_d4_multiplas_duvidas(cats):
    d = decidir(_resp(cats, categorias_secundarias=["C05"]), cats, LIMITE)
    assert (d.motivo_manual, d.regra) == (MotivoManual.MULTIPLAS_DUVIDAS, "D4")


def test_d5_sinal_de_excecao(cats):
    d = decidir(_resp(cats, sinais_excecao=["PEDIDO_PO"]), cats, LIMITE)
    assert (d.motivo_manual, d.regra) == (MotivoManual.EXCECAO, "D5")


def test_d6_categoria_desabilitada(cats):
    d = decidir(_resp(cats, categoria="C06", tutorial="TUT_REEMBOLSO"), cats, LIMITE)
    assert (d.motivo_manual, d.regra) == (MotivoManual.CATEGORIA_DESABILITADA, "D6")


def test_d7_ia_sugere_manual(cats):
    d = decidir(_resp(cats, acao="ENCAMINHAR_MANUAL", tutorial=None, resumo_duvida="O fornecedor pede orientação."), cats, LIMITE)
    assert (d.motivo_manual, d.regra) == (MotivoManual.EXCECAO, "D7")


@pytest.mark.parametrize("tutorial", ["TUT_CADASTRO", None])
def test_d7_tutorial_diferente_do_da_categoria(cats, tutorial):
    d = decidir(_resp(cats, tutorial=tutorial), cats, LIMITE)
    assert (d.motivo_manual, d.regra) == (MotivoManual.EXCECAO, "D7")


def test_ordem_das_regras_d2_antes_de_d3_d3_antes_de_d4_d4_antes_de_d5(cats):
    assert decidir(_resp(cats, categoria="C07", tutorial=None, confianca=0.1), cats, LIMITE).regra == "D2"
    assert decidir(_resp(cats, confianca=0.5, categorias_secundarias=["C05"]), cats, LIMITE).regra == "D3"
    assert decidir(_resp(cats, categorias_secundarias=["C05"], sinais_excecao=["ERRO_SISTEMA"]), cats, LIMITE).regra == "D4"
    assert decidir(_resp(cats, categoria="C06", tutorial="TUT_REEMBOLSO", sinais_excecao=["DOCUMENTACAO_REEMBOLSO"]),
                   cats, LIMITE).regra == "D5"


def test_e5_codigo_sem_mapeamento(cats):
    dados = yaml.safe_load((RAIZ / "config" / "categorias_ia.yaml").read_text(encoding="utf-8"))
    del dados["categorias"]["C05"]
    parcial = CategoriasIA.de_dict(dados)
    assert parcial.sem_mapeamento() == ["C05"]
    d = decidir(_resp(cats, categoria="C05", tutorial="TUT_CADASTRO"), parcial, LIMITE)
    assert (d.motivo_manual, d.regra) == (MotivoManual.CATEGORIA_SEM_TUTORIAL, "E5")


@pytest.mark.parametrize("mexer, trecho", [
    (lambda d: d["categorias"]["C03"].update(tutorial="TUT_INEXISTENTE"), "não é uma categoria de tutorial"),
    (lambda d: d["categorias"]["C07"].update(resposta_automatica=True), "sem tutorial"),
    (lambda d: d["categorias"]["C99"].update(motivo_manual="QUALQUER"), "motivo_manual"),
    (lambda d: d["categorias"].update(C42={"tutorial": None, "resposta_automatica": False}), "codigos_validos"),
])
def test_categorias_ia_yaml_invalido(mexer, trecho):
    dados = yaml.safe_load((RAIZ / "config" / "categorias_ia.yaml").read_text(encoding="utf-8"))
    mexer(dados)
    with pytest.raises(ValueError, match=trecho):
        CategoriasIA.de_dict(dados)
