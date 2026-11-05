"""E1 (historico_resumido) e E2 (filtros de e-mail interno e spam)."""
import json

import pytest

from rpa_duvidas import extracao
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.filtros import FiltroInterno, FiltroSpam
from rpa_duvidas.modelos import Acao, EmailRecebido, Status


def _email(**kw):
    base = dict(id_mensagem="<h@t>", remetente="a@b.com", nome_remetente="A", assunto="", corpo_html="",
                corpo_texto_bruto="", data_recebimento=None)
    base.update(kw)
    return EmailRecebido(**base)


# ---- E1 -------------------------------------------------------------------- #
def test_historico_resumido_em_texto(cfg):
    e = _email(corpo_texto_bruto="Ainda não consegui subir a NF.\n\nDe: Contas a Pagar\nSegue o tutorial de upload.")
    extracao.processar(e, cfg.get("extracao"))
    assert e.corpo_limpo == "Ainda não consegui subir a NF."
    assert e.historico_resumido.startswith("De: Contas a Pagar") and "tutorial de upload" in e.historico_resumido


def test_historico_resumido_em_html_do_outlook(cfg):
    html = ("<body><p>Pergunta nova</p><div id='divRplyFwdMsg'><b>De:</b> CAP</div>"
            "<div>Segue o tutorial em anexo.</div></body>")
    e = _email(corpo_html=html)
    extracao.processar(e, cfg.get("extracao"))
    assert e.corpo_limpo == "Pergunta nova"
    assert "Segue o tutorial em anexo." in e.historico_resumido


def test_historico_resumido_limitado_a_2000_caracteres(cfg):
    e = _email(corpo_texto_bruto="Pergunta nova sobre NF\nDe: CAP\n" + "h" * 5000)
    extracao.processar(e, cfg.get("extracao"))
    assert len(e.historico_resumido) <= 2000 and e.historico_resumido.endswith("[...]")


def test_sem_historico(cfg):
    e = _email(corpo_texto_bruto="Só uma pergunta, sem histórico.")
    extracao.processar(e, cfg.get("extracao"))
    assert e.historico_resumido == ""


# ---- E2 -------------------------------------------------------------------- #
def test_filtro_interno():
    f = FiltroInterno(["empresa-exemplo.com.br", "@grupo.com"], ["automacao@empresa-exemplo.com.br", ""])
    assert f.interno("ana@empresa-exemplo.com.br")[0]
    assert f.interno("ANA@sub.empresa-exemplo.com.br")[0]
    assert f.interno("x@grupo.com")[0]
    assert not f.interno("ana@fornecedor-exemplo.com.br")[0]
    assert not f.interno("ana@empresa-exemplo.com.br.outro.com")[0]
    assert not FiltroInterno().interno("ana@empresa-exemplo.com.br")[0]     # vazio = desligado (v0.1.0)


def test_filtro_spam():
    assert not FiltroSpam().spam({"x-ms-exchange-organization-scl": "9"})[0]   # desligado por padrão
    f = FiltroSpam(ativo=True)
    assert f.spam({"X-MS-Exchange-Organization-SCL": "5"})[0]
    assert not f.spam({"x-ms-exchange-organization-scl": "1"})[0]
    assert not f.spam({"x-ms-exchange-organization-scl": "-1"})[0]
    assert not f.spam({})[0]


def _saidas(projeto, tipo="*"):
    pasta = projeto / "dados_teste" / "caixa_simulada" / "saida"
    return [json.loads(p.read_text(encoding="utf-8")) for p in pasta.glob(f"*_{tipo}.json")]


def test_ciclo_ignora_interno_e_spam_sem_chamar_a_ia(projeto, cfg_ia, novo_email):
    cfg_ia.dados["filtros"]["spam"]["ativo"] = True
    robo = montar_dependencias(cfg_ia)
    chamadas = []
    original = robo.classificador.classificar
    robo.classificador.classificar = lambda *a, **k: chamadas.append(1) or original(*a, **k)
    novo_email("Upload", "como faço upload da nf?", remetente="analista@empresa-exemplo.com.br")
    novo_email("Promoção", "ganhe um prêmio", cabecalhos={"X-MS-Exchange-Organization-SCL": "9"})
    resumo = robo.executar_ciclo()
    ev = robo.registro.eventos()
    robo.registro.fechar()
    assert [r.acao for r in resumo.resultados] == [Acao.IGNORAR, Acao.IGNORAR]
    assert [r.status for r in resumo.resultados] == [Status.IGNORADO, Status.IGNORADO]
    assert chamadas == []
    assert ev[0]["motivo"].startswith("INTERNO") and ev[1]["motivo"].startswith("SPAM")
    assert len(list((projeto / "dados_teste" / "caixa_simulada" / "ignorados").glob("*.json"))) == 2
    assert not _saidas(projeto)
