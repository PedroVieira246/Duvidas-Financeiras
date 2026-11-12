"""v0.3.3 – correções do 2º teste da operação assistida (12/11/2026). Dados fictícios.

1. O aviso de "e-mail externo" no topo (aviso + endereço + linha horizontal) fazia o
   corpo inteiro ser descartado: a classificação usava só o assunto.
2. Com a pasta de arquivamento dentro do OneDrive, o caminho do .msg passava de 240
   caracteres para quase todo escritório.
"""
from datetime import datetime
from pathlib import PureWindowsPath

import pytest

from rpa_duvidas import extracao
from rpa_duvidas.arquivamento import LIMITE_CAMINHO, ErroArquivamento, caminho_msg
from rpa_duvidas.modelos import EmailRecebido

HTML_COM_AVISO = (
    "<html><body>"
    "<table><tr><td><b>EXTERNAL EMAIL:</b> Be cautious with links and attachments.</td>"
    "<td>ana@fornecedor-ficticio.com.br</td></tr></table><hr>"
    "<p>Prezados, bom dia.</p><p>Preciso de reembolso de uma despesa. Como abro o chamado de reembolso?</p>"
    "<p>Atenciosamente,</p><p>Ana</p>"
    "<hr><p><b>De:</b> Analista &lt;analista@empresa-ficticia.com.br&gt;</p><p>Texto antigo sobre pedido de compra</p>"
    "</body></html>"
)


def _email(**kw):
    base = dict(id_mensagem="<x@y>", remetente="ana@fornecedor-ficticio.com.br", nome_remetente="Ana", assunto="Dúvida",
                corpo_html="", corpo_texto_bruto="", data_recebimento=None)
    base.update(kw)
    return EmailRecebido(**base)


def test_configuracao_padrao_traz_os_avisos(cfg):
    assert cfg.get("extracao")["banners_ignorados"]


def test_aviso_de_email_externo_nao_esconde_o_corpo(cfg):
    e = extracao.processar(_email(corpo_html=HTML_COM_AVISO), cfg.get("extracao"))
    assert "chamado de reembolso" in e.corpo_limpo
    assert "EXTERNAL" not in e.corpo_limpo and "fornecedor-ficticio" not in e.corpo_limpo
    assert "pedido de compra" not in e.corpo_limpo                 # o histórico continua de fora
    assert "pedido de compra" in e.historico_resumido


def test_aviso_em_texto_puro(cfg):
    corpo = ("EXTERNAL EMAIL: Be cautious with links and attachments. \tana@fornecedor-ficticio.com.br"
             " <mailto:ana@fornecedor-ficticio.com.br>\n________________________________\n"
             "Bom dia, como faço o upload da nota fiscal?\n")
    e = extracao.processar(_email(corpo_texto_bruto=corpo), cfg.get("extracao"))
    assert e.corpo_limpo == "Bom dia, como faço o upload da nota fiscal?"


def test_sem_aviso_nada_muda(cfg):
    banners = cfg.get("extracao")["banners_ignorados"]
    texto = "Bom dia.\nSegue a dúvida.\n____________\nDe: alguém"
    assert extracao.remover_preambulo(texto, banners) == texto
    e = extracao.processar(_email(corpo_texto_bruto=texto), cfg.get("extracao"))
    assert e.corpo_limpo == "Bom dia.\nSegue a dúvida."            # linha horizontal no MEIO ainda corta o histórico


def test_endereco_solto_so_sai_depois_do_aviso(cfg):
    banners = cfg.get("extracao")["banners_ignorados"]
    texto = "contato@fornecedor-ficticio.com.br\nesse é o nosso novo e-mail"
    assert extracao.remover_preambulo(texto, banners) == texto
    assert extracao.remover_preambulo("____________\n\nOlá", banners) == "Olá"
    so_aviso = "EXTERNAL EMAIL: Be cautious with links and attachments."
    assert extracao.remover_preambulo(so_aviso, banners) == so_aviso   # nunca devolve vazio


def test_classificacao_volta_a_ler_o_corpo(projeto, cfg, novo_email):
    from rpa_duvidas.__main__ import montar_dependencias
    from rpa_duvidas.modelos import Categoria

    novo_email("Dúvida", "", corpo_html=HTML_COM_AVISO)
    robo = montar_dependencias(cfg)
    try:
        resumo = robo.executar_ciclo()
    finally:
        robo.registro.fechar()
    assert resumo.resultados[0].classificacao.categoria == Categoria.TUT_REEMBOLSO


# --------------------------------------------------------------------------- #
# arquivamento
# --------------------------------------------------------------------------- #
def _raiz(tmp_path, tamanho):
    return tmp_path / ("p" * (tamanho - len(str(tmp_path)) - 1))


def test_raiz_comprida_encurta_o_escritorio(tmp_path):
    raiz = _raiz(tmp_path, 182)                                   # tamanho da pasta real do 2º teste
    quando = datetime(2026, 11, 3, 14, 37)
    p = caminho_msg(raiz, "ESCRITORIO FICTICIO & ASSOCIADOS ADVOGADOS", quando, "FE1E9BCD", "RES: assunto qualquer")
    assert len(str(p)) <= LIMITE_CAMINHO
    assert p.name == "2026-11-03_1437_FE1E9BCD.msg" and p.parent.name == "2026-11"
    pasta = p.parent.parent.name
    assert pasta == "ESCRITORIO FICTICIO" and p.parent.parent.parent == raiz   # 20 caracteres, sem espaço no fim
    outro = caminho_msg(raiz, "ESCRITORIO FICTICIO & ASSOCIADOS ADVOGADOS", datetime(2026, 11, 9, 8, 1), "0A0B0C0D", "x")
    assert outro.parent.parent.name == pasta                      # mesmo escritório, mesma pasta


def test_escritorio_curto_nao_e_alterado(tmp_path):
    p = caminho_msg(_raiz(tmp_path, 182), "ALFA ADVOGADOS", datetime(2026, 11, 3, 14, 37), "FE1E9BCD", "Assunto comprido demais")
    assert p.parent.parent.name == "ALFA ADVOGADOS" and len(str(p)) <= LIMITE_CAMINHO
    assert p.name.startswith("2026-11-03_1437_FE1E9BCD_Ass")


def test_raiz_comprida_demais_continua_falhando(tmp_path):
    with pytest.raises(ErroArquivamento, match="escritório encurtado"):
        caminho_msg(_raiz(tmp_path, 198), "ESCRITORIO FICTICIO & ASSOCIADOS", datetime(2026, 11, 3, 14, 37), "FE1E9BCD", "x")
