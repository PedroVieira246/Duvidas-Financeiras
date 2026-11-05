import csv
from pathlib import Path

import pytest

from rpa_duvidas.classificacao import criar_classificador
from rpa_duvidas.classificacao.base import Classificador
from rpa_duvidas.modelos import Categoria, MotivoManual

MASSA = Path(__file__).parent / "dados" / "massa_emails_sintetica.csv"


@pytest.fixture()
def clf(cfg):
    return criar_classificador(cfg)


def test_implementa_a_interface(clf):
    assert isinstance(clf, Classificador)


@pytest.mark.parametrize("assunto, corpo, esperado", [
    ("Acesso", "não consigo acessar o portal Connect", Categoria.TUT_CONNECT),
    ("NF", "como faço o upload da nota fiscal no PYM?", Categoria.TUT_UPLOAD_NF),
    ("Despesas", "preciso pedir reembolso", Categoria.TUT_REEMBOLSO),
    ("Banco", "mudamos os dados bancários, como atualizar o cadastro?", Categoria.TUT_CADASTRO),
    ("PO", "não recebemos o pedido de compra", Categoria.FORMS_PO),
])
def test_categorias_basicas(clf, assunto, corpo, esperado):
    c = clf.classificar(assunto, corpo)
    assert c.categoria == esperado
    assert 0 < c.confianca <= 1
    assert c.motivo


def test_dependente_de_sap_vai_para_manual_com_motivo(clf):
    c = clf.classificar("Pagamento", "Quando vou receber o pagamento da NF 123?")
    assert c.categoria == Categoria.MANUAL and c.motivo_manual == MotivoManual.SAP


def test_novo_cadastro_e_fora_do_escopo(clf):
    c = clf.classificar("Novo cadastro", "Quero me cadastrar como fornecedor")
    assert c.categoria == Categoria.MANUAL and c.motivo_manual == MotivoManual.FORA_DO_ESCOPO


def test_sem_termos_conhecidos(clf):
    c = clf.classificar("Olá", "Podemos marcar uma reunião?")
    assert (c.categoria, c.confianca, c.motivo_manual) == (Categoria.MANUAL, 0.0, MotivoManual.NAO_IDENTIFICADO)


def test_assunto_pesa_mais_que_corpo(clf):
    a = clf.pontuar("reembolso", "")[Categoria.TUT_REEMBOLSO][0]
    b = clf.pontuar("", "reembolso")[Categoria.TUT_REEMBOLSO][0]
    assert a > b


def test_termo_casa_palavra_inteira(clf):
    """'po' não pode casar dentro de 'portal' ou 'depois'."""
    assert Categoria.FORMS_PO not in clf.pontuar("", "depois do portal")


def test_dois_temas_reduzem_a_confianca(clf):
    unico = clf.classificar("Connect", "não consigo acessar o connect")
    duplo = clf.classificar("Connect", "não consigo acessar o connect para fazer upload da nota fiscal")
    assert duplo.confianca < unico.confianca


def test_massa_sintetica_sem_erro_grave(cfg, clf):
    """Regressão da MECÂNICA (a massa sintética foi escrita junto com os termos)."""
    limite = cfg.limite_confianca
    graves = acertos = total = 0
    with MASSA.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            c = clf.classificar(row["assunto"], row["corpo"])
            final = c.categoria if (c.categoria == Categoria.MANUAL or c.confianca >= limite) else Categoria.MANUAL
            total += 1
            acertos += final == row["categoria_esperada"]
            graves += final in Categoria.RESPONDIVEIS and final != row["categoria_esperada"]
    assert graves == 0
    assert acertos / total >= 0.9
