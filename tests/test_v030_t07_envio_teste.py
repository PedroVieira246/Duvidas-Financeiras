"""v0.3.0 – T07: envio de teste para o destino padrão e trava de destinatários (seção 6.2).

Critério de aceite 3: com destino_respostas = TESTE, NENHUMA mensagem sai para endereço
diferente do destino padrão ou de AVISO_ERRO. COM do Outlook simulado (tests/fakes_outlook.py)."""
import itertools

import pytest

from conftest import AVISO_CAL, DESTINO_CAL
from fakes_outlook import OL_CC, Caixa
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.caixa import trava_da_config
from rpa_duvidas.caixa.base import ErroSeguranca, TravaDestinatarios
from rpa_duvidas.caixa.outlook_com import CaixaOutlookCOM
from rpa_duvidas.modelos import Acao, Status

CATS = ["RPA - Respondido", "RPA - Encaminhado", "RPA - Erro", "RPA - Ignorado", "RPA - Simulado"]
FORNECEDOR = "ana@fornecedor-exemplo.com.br"
TERCEIROS = {FORNECEDOR, "socio@fornecedor-exemplo.com.br", "cobranca@outro-fornecedor.com.br",
             "analistas.cap@empresa-exemplo.com.br", "maria.laura@empresa-exemplo.com.br"}
DESTINOS = {k: f"@inbox/{k}" for k in ("respondidos", "encaminhados", "erro", "ignorados")}


def _cx(fake, trava=None):
    return CaixaOutlookCOM("", "@inbox", DESTINOS, mover_apos_tratar=False, categorias_rpa=CATS, trava=trava,
                           namespace=fake, aplicativo=fake)


def _receber_massa(fake):
    fake.receber(de=FORNECEDOR, assunto="Pedido de compra", corpo="preciso do pedido de compra", id_msg="<r@x>",
                 para="maria.laura@empresa-exemplo.com.br; socio@fornecedor-exemplo.com.br",
                 cc="cobranca@outro-fornecedor.com.br", reply_to="socio@fornecedor-exemplo.com.br")
    fake.receber(de=FORNECEDOR, assunto="Ordem de compra", corpo="sem pedido de compra", id_msg="<p@x>")
    fake.receber(de=FORNECEDOR, assunto="Pagamento", corpo="quando vou receber o pagamento?", id_msg="<s@x>")
    fake.receber(de=FORNECEDOR, assunto="Cadastro", corpo="preciso atualizar cadastro e dados bancarios",
                 id_msg="<c@x>")                                         # tutorial inexistente → erro → aviso


# --------------------------------------------------------------------------- #
# critério de aceite 3 – teste dedicado, todas as combinações de configuração
# --------------------------------------------------------------------------- #
COMBINACOES = list(itertools.product(
    [False, True],          # envio_real (modo REAL)
    [False, True],          # responder_todos
    [[], ["analistas.cap@empresa-exemplo.com.br"]],   # CC dos analistas
    ["ENCAMINHAR", "CATEGORIZAR"],                     # acao_manual
    [False, True],          # Reply() com destinatário escondido que Remove() não tira (risco da seção 11)
    [True, False],          # trava instalada na caixa pela fábrica (a do ciclo sempre existe)
))


@pytest.mark.parametrize("envio_real, responder_todos, cc, acao_manual, escondido, trava_caixa", COMBINACOES)
def test_criterio_3_nada_sai_fora_do_destino_padrao_ou_aviso_erro(
        projeto_cal, cfg_cal, envio_real, responder_todos, cc, acao_manual, escondido, trava_caixa):
    cfg = cfg_cal
    cfg.dados["execucao"]["envio_real"] = envio_real
    for conf in cfg.dados["categorias"].values():          # no modo REAL, tudo liberado (pior caso para a trava)
        conf["liberada"], conf["data_liberacao"] = envio_real, "2026-11-01"
    cfg.dados["respostas"]["responder_todos"] = responder_todos
    cfg.dados["destinatarios"]["analistas_cc"] = cc
    cfg.dados["destinatarios"]["acao_manual"] = acao_manual
    cfg.dados["destinatarios"]["analise_manual"]["padrao"] = ["analistas.cap@empresa-exemplo.com.br"]
    cfg.dados["_inline"]["tutoriais.arquivo"]["categorias"]["TUT_CADASTRO"]["caminho_arquivo"] = "nao/existe.pptx"
    fake = Caixa(remove_defeituoso=escondido)
    _receber_massa(fake)
    robo = montar_dependencias(cfg, caixa=_cx(fake, trava_da_config(cfg) if trava_caixa else None))
    try:
        resumo = robo.executar_ciclo()
    finally:
        robo.registro.fechar()

    permitidos = {DESTINO_CAL, AVISO_CAL}
    saidas = fake.saidas()
    assert saidas, "o ciclo deveria ter gerado mensagens"
    for m in saidas:
        enderecos = set(m.Recipients.enderecos())
        assert enderecos and enderecos <= permitidos, (m.Subject, enderecos)
        assert not (enderecos & TERCEIROS)
        if m.Subject.startswith(("RE:", "ENC:", "[MANUAL")):
            assert enderecos == {DESTINO_CAL}, (m.Subject, enderecos)       # respostas/encaminhamentos: só o destino
    assert all(m.enviado == envio_real for m in saidas if not m.Subject.startswith("[RPA"))
    por_id = {r.email.id_mensagem: r for r in resumo.resultados}
    if escondido:
        # a trava pegou o destinatário escondido: a resposta foi descartada e o e-mail foi para Erro
        for chave in ("<r@x>", "<p@x>"):
            assert por_id[chave].status == Status.ERRO
            assert por_id[chave].erro.startswith("ErroSeguranca: destinatário fora do destino padrão")
        assert all(m.descartado for m in fake.geradas if m.Subject.startswith("RE:"))
    else:
        assert por_id["<r@x>"].destinatarios == [DESTINO_CAL]
        assert FORNECEDOR in por_id["<r@x>"].destinatario_original.split("; ")


# --------------------------------------------------------------------------- #
# adaptador COM
# --------------------------------------------------------------------------- #
def _primeiro(fake, cx):
    [e] = cx.ler_pendentes(10)
    return e


def test_responder_redireciona_remove_todos_e_zera_cc(projeto_cal):
    fake = Caixa()
    fake.receber(de=FORNECEDOR, assunto="Reembolso", para="maria.laura@empresa-exemplo.com.br",
                 cc="cobranca@outro-fornecedor.com.br")
    cx = _cx(fake)
    e = _primeiro(fake, cx)
    cx.responder(e, "<p>R</p>", cc=["analistas.cap@empresa-exemplo.com.br"], responder_todos=True,
                 redirecionar_para=DESTINO_CAL)
    [resp] = fake.geradas
    assert resp.Recipients.enderecos() == [DESTINO_CAL] and resp.CC == "" and resp.salvo
    assert resp.Subject == "RE: Reembolso"                       # mantém o fio (Reply)


def test_trava_aborta_endereco_fora_e_descarta_a_mensagem(projeto_cal):
    fake = Caixa()
    fake.receber(de=FORNECEDOR, assunto="Pagamento")
    trava = TravaDestinatarios.destino_padrao(DESTINO_CAL, [AVISO_CAL])
    cx = _cx(fake, trava)
    e = _primeiro(fake, cx)
    with pytest.raises(ErroSeguranca, match="destinatário fora do destino padrão"):
        cx.responder(e, "<p>R</p>")                              # sem redirecionar: iria ao fornecedor
    with pytest.raises(ErroSeguranca):
        cx.encaminhar(e, [AVISO_CAL], "[MANUAL – SAP]", "<p>n</p>")   # encaminhar: só o destino padrão
    with pytest.raises(ErroSeguranca):
        cx.enviar_novo(["outro@empresa-exemplo.com.br"], "Aviso", "<p>a</p>")
    assert all(m.descartado and not m.salvo and not m.enviado for m in fake.geradas)
    cx.enviar_novo([AVISO_CAL], "Aviso", "<p>a</p>", enviar=True)  # aviso para AVISO_ERRO passa
    assert fake.geradas[-1].enviado


def test_trava_falha_fechada_quando_o_smtp_nao_e_identificado(projeto_cal):
    """Endereço Exchange (/o=...) sem SMTP legível: a trava bloqueia em vez de deixar passar."""
    fake = Caixa()
    fake.receber(de=FORNECEDOR, assunto="Reembolso")
    cx = _cx(fake, TravaDestinatarios.destino_padrao(DESTINO_CAL))
    [mail] = fake.inbox.Items._itens
    resp = mail.Reply()
    resp.To = ""
    resp.Recipients.Add("/o=ExchangeLabs/ou=Exchange/cn=Recipients/cn=anelise")
    resp.Recipients._itens[0].PropertyAccessor.props.clear()
    with pytest.raises(ErroSeguranca, match="não identificado"):
        cx._concluir(resp, False, "responder")
    assert resp.descartado and not resp.salvo


def test_smtp_do_usuario_exchange_e_aceito(projeto_cal):
    fake = Caixa()
    cx = _cx(fake, TravaDestinatarios.destino_padrao(DESTINO_CAL))
    msg = fake.CreateItem(0)
    rec = msg.Recipients.Add("/o=ExchangeLabs/cn=anelise")
    rec.PropertyAccessor.props.clear()
    usuario = type("U", (), {"PrimarySmtpAddress": DESTINO_CAL.upper()})()
    rec.AddressEntry = type("AE", (), {"GetExchangeUser": lambda self: usuario})()
    assert cx._concluir(msg, False, "responder")
    assert msg.salvo


def test_trava_sem_destinatario_nenhum():
    with pytest.raises(ErroSeguranca, match="sem destinatário"):
        TravaDestinatarios.destino_padrao(DESTINO_CAL).conferir("responder", [])


def test_fabrica_instala_a_trava_e_permitidos_automaticos(cfg_cal):
    trava = trava_da_config(cfg_cal)
    assert trava.permitidos["responder"] == {DESTINO_CAL}
    assert trava.permitidos["encaminhar"] == {DESTINO_CAL}
    assert trava.permitidos["enviar_novo"] == {DESTINO_CAL, AVISO_CAL}
    cfg_cal.dados["execucao"]["destino_respostas"] = "FORNECEDOR"
    assert trava_da_config(cfg_cal) is None


def test_faixa_e_registro_mostram_o_destinatario_original(projeto_cal, cfg_cal, entrada):
    import json

    (entrada / "001.json").write_text(json.dumps({
        "id_mensagem": "<1@x>", "remetente": FORNECEDOR, "nome_remetente": "Ana", "assunto": "Pedido de compra",
        "corpo_texto": "preciso do pedido de compra", "data_recebimento": "2026-11-03T09:00:00"}), encoding="utf-8")
    robo = montar_dependencias(cfg_cal)
    try:
        [r] = robo.executar_ciclo().resultados
        [ev] = robo.registro.eventos()
    finally:
        robo.registro.fechar()
    assert r.acao == Acao.RESPONDER_FORMS and r.status == Status.SIMULADO
    assert (ev["destinatario_original"], ev["destinatarios"], ev["destino_respostas"]) == (FORNECEDOR, DESTINO_CAL, "TESTE")
    saida = projeto_cal / "dados_teste" / "caixa_simulada" / "saida"
    [resp] = [json.loads(p.read_text(encoding="utf-8")) for p in saida.glob("*_RESPOSTA.json")]
    assert resp["para"] == [DESTINO_CAL] and resp["cc"] == [] and resp["destinatario_original"] == FORNECEDOR
    assert f"No envio real, este e-mail iria para: {FORNECEDOR}" in resp["corpo_html"]
