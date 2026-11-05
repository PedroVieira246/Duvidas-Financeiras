from rpa_duvidas import extracao
from rpa_duvidas.config import carregar
from rpa_duvidas.modelos import EmailRecebido

import pytest


@pytest.fixture()
def marcadores(cfg):
    e = cfg.get("extracao")
    return dict(
        marcadores_historico=e["marcadores_historico"],
        marcadores_assinatura=e["marcadores_assinatura"],
        marcadores_aviso_legal=e["marcadores_aviso_legal"],
    )


def _email(**kw):
    base = dict(id_mensagem="<x@y>", remetente="a@b.com", nome_remetente="A", assunto="", corpo_html="",
                corpo_texto_bruto="", data_recebimento=None)
    base.update(kw)
    return EmailRecebido(**base)


def test_html_para_texto_preserva_quebras_e_remove_estilo():
    html = "<html><head><style>p{color:red}</style></head><body><p>Linha 1</p><div>Linha&nbsp;2<br>Linha 3</div></body></html>"
    assert extracao.html_para_texto(html) == "Linha 1\n\nLinha 2\nLinha 3"


def test_html_remove_historico_do_outlook():
    html = "<body><p>Pergunta nova</p><div id='divRplyFwdMsg'>De: X</div><div>mensagem antiga sobre reembolso</div></body>"
    texto = extracao.html_para_texto(html)
    assert "Pergunta nova" in texto and "reembolso" not in texto


@pytest.mark.parametrize("marcador", [
    "De: Contas a Pagar <cap@empresa.com>",
    "-----Mensagem original-----",
    "Em seg., 13 de out. de 2026 às 10:00, Fulano escreveu:",
    "On Mon, Oct 13, 2026 at 10:00 AM Someone wrote:",
    "> texto citado",
])
def test_corta_historico(marcadores, marcador):
    texto = f"Como faço o upload da nota fiscal?\n\n{marcador}\nreembolso pedido de compra"
    limpo = extracao.limpar_corpo(texto, **marcadores)
    assert limpo == "Como faço o upload da nota fiscal?"


def test_corta_assinatura_e_aviso_legal(marcadores):
    texto = ("Bom dia,\nPreciso atualizar o cadastro.\nAtenciosamente,\nJoão\nFinanceiro\n"
             "AVISO DE CONFIDENCIALIDADE: esta mensagem é sigilosa")
    assert extracao.limpar_corpo(texto, **marcadores) == "Bom dia,\nPreciso atualizar o cadastro."


def test_obrigado_no_inicio_nao_corta_o_corpo(marcadores):
    texto = "Obrigado\nmas ainda não consegui acessar o portal connect."
    assert "connect" in extracao.limpar_corpo(texto, **marcadores)


def test_limpeza_excessiva_volta_ao_texto_original(marcadores):
    texto = "De: fulano\nPor favor ver abaixo o pedido de compra"
    assert "pedido de compra" in extracao.limpar_corpo(texto, **marcadores)


def test_limpar_assunto():
    assert extracao.limpar_assunto("RE: ENC: Fw: RES: Acesso ao Connect") == "Acesso ao Connect"


def test_normalizar_remove_acentos():
    assert extracao.normalizar("  Atualização   CADASTRAL ") == "atualizacao cadastral"


@pytest.mark.parametrize("kw, esperado", [
    (dict(classe_mensagem="REPORT.IPM.Note.NDR"), True),
    (dict(classe_mensagem="IPM.Note.Rules.OofTemplate.Microsoft"), True),
    (dict(cabecalhos={"auto-submitted": "auto-replied"}), True),
    (dict(cabecalhos={"auto-submitted": "no"}), False),
    (dict(cabecalhos={"precedence": "bulk"}), True),
    (dict(assunto="Resposta automática: Pagamento"), True),
    (dict(assunto="Undeliverable: NF 123"), True),
    (dict(assunto="Dúvida sobre pagamento"), False),
])
def test_detectar_resposta_automatica(cfg, kw, esperado):
    auto, _ = extracao.detectar_resposta_automatica(_email(**kw), cfg.get("filtros.assuntos_resposta_automatica"))
    assert auto is esperado


def test_parse_cabecalhos():
    cab = extracao.parse_cabecalhos("Received: x\r\nAuto-Submitted: auto-replied\r\nSubject: oi\r\n")
    assert cab["auto-submitted"] == "auto-replied"


def test_endereco_permitido():
    perm = ["@empresa.com.br", "fulano@gmail.com"]
    assert extracao.endereco_permitido("ana@empresa.com.br", perm)
    assert extracao.endereco_permitido("FULANO@gmail.com", perm)
    assert not extracao.endereco_permitido("ana@fornecedor.com.br", perm)
    assert not extracao.endereco_permitido("x@empresa.com.br.hacker.com", perm)
    assert extracao.endereco_permitido("qualquer@x.com", [])
