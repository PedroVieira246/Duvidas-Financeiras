"""v0.2.1 – leitura direto da Caixa de Entrada, modo sem mover (conta Exchange
ActiveSync), filtros de leitura e proteção contra laço (mensagens do RPA)."""
from datetime import datetime

import pytest

from rpa_duvidas import extracao
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.caixa import _data, criar_caixa
from rpa_duvidas.caixa.outlook_com import PR_INTERNET_MESSAGE_ID, CaixaOutlookCOM
from rpa_duvidas.config import ErroConfiguracao
from rpa_duvidas.modelos import Acao, EmailRecebido, MotivoIgnorado, Status
from rpa_duvidas.respostas import GeradorRespostas

from test_outlook_com import DESTINOS, Colecao, Mensagem, Namespace, ns  # noqa: F401 (fixture)

CATS = ["RPA - Respondido", "RPA - Encaminhado", "RPA - Erro", "RPA - Ignorado", "RPA - Simulado"]


def _caixa_inbox(ns, **kw):
    base = dict(criar_pastas=True, mover_apos_tratar=False, categorias_rpa=CATS, namespace=ns, aplicativo=None)
    base.update(kw)
    return CaixaOutlookCOM("", "@inbox", DESTINOS, **base)


def _msg(pasta, n, assunto="[RPA-TESTE] Acesso", data=None, de="maria@fornecedor-exemplo.com.br", **kw):
    return Mensagem(pasta, assunto=assunto, de=de, data=data or datetime(2026, 10, 27, 9, n),
                    props={PR_INTERNET_MESSAGE_ID: f"<{n}@x>"}, **kw)


# --------------------------------------------------------------------------- #
# adaptador
# --------------------------------------------------------------------------- #
def test_modo_sem_mover_so_marca_e_categoriza(ns):
    cx = _caixa_inbox(ns)
    assert cx.pasta_entrada is ns.inbox
    msg = _msg(ns.inbox, 1)
    ns.inbox.Items._itens.append(msg)
    [e] = cx.ler_pendentes(10)
    cx.finalizar(e, "respondidos", "RPA - Simulado")
    assert msg.pasta is ns.inbox                       # Move não é chamado
    assert msg.UnRead is False and msg.Categories == "RPA - Simulado" and msg.salvo
    assert cx.ler_pendentes(10) == []                  # já tratado: não volta


def test_modo_sem_mover_nao_cria_nem_exige_pastas_de_destino(ns):
    cx = _caixa_inbox(ns, criar_pastas=False)
    assert cx.verificar() == []
    assert ns.inbox.Folders.Count == 0


def test_leitura_filtrada_por_assunto_data_e_ordem(ns):
    cx = _caixa_inbox(ns, filtro_assunto="[rpa-teste]", recebidos_desde=datetime(2026, 10, 27))
    antigo = _msg(ns.inbox, 1, data=datetime(2026, 10, 20, 8, 0))      # antes da data
    pessoal = _msg(ns.inbox, 2, assunto="Almoço de sexta")              # sem a marca
    a, b, c = _msg(ns.inbox, 3), _msg(ns.inbox, 4), _msg(ns.inbox, 5)
    tratado = _msg(ns.inbox, 6)
    tratado.Categories = "RPA - Respondido"
    ns.inbox.Items._itens += [c, antigo, tratado, a, pessoal, b]
    assert [e.id_mensagem for e in cx.ler_pendentes(10)] == ["<3@x>", "<4@x>", "<5@x>"]  # mais antigo primeiro
    assert [e.id_mensagem for e in cx.ler_pendentes(2)] == ["<3@x>", "<4@x>"]
    assert pessoal.UnRead is True and pessoal.Categories == ""        # e-mail pessoal intocado


def test_max_varredura_limita_itens_examinados(ns):
    cx = _caixa_inbox(ns, max_varredura=2)
    ns.inbox.Items._itens += [_msg(ns.inbox, n) for n in range(1, 6)]
    assert [e.id_mensagem for e in cx.ler_pendentes(10)] == ["<4@x>", "<5@x>"]   # só os 2 mais recentes


def test_ignora_convite_de_reuniao_na_leitura_filtrada(ns):
    cx = _caixa_inbox(ns)
    convite = _msg(ns.inbox, 1)
    convite.Class = 53
    ns.inbox.Items._itens += [convite, _msg(ns.inbox, 2)]
    assert [e.id_mensagem for e in cx.ler_pendentes(10)] == ["<2@x>"]


def test_comportamento_original_sem_opcoes_novas(ns):
    cx = CaixaOutlookCOM("", "@inbox/RPA_Teste", DESTINOS, criar_pastas=True, namespace=ns)
    assert not cx._leitura_filtrada
    msg = _msg(cx.pasta_entrada, 1)
    cx.pasta_entrada.Items._itens.append(msg)
    [e] = cx.ler_pendentes(10)
    cx.finalizar(e, "respondidos", "RPA - Simulado")
    assert msg.pasta.Name == "Respondidos"


class _Store:
    StoreID = "store-1"


def _com_conta(ns, tipo):
    ns.inbox.Store = _Store()
    conta = type("Conta", (), {"AccountType": tipo, "DeliveryStore": _Store()})()
    ns.Accounts = Colecao([conta])


def test_verificar_bloqueia_activesync_quando_vai_mover(ns):
    _com_conta(ns, 4)
    cx = CaixaOutlookCOM("", "@inbox/RPA_Teste", DESTINOS, criar_pastas=True, namespace=ns)
    cx.pasta_entrada.Store = _Store()
    assert any("ActiveSync" in p for p in cx.verificar())


def test_verificar_aceita_activesync_no_modo_sem_mover(ns):
    _com_conta(ns, 4)
    cx = _caixa_inbox(ns, filtro_assunto="[RPA-TESTE]")
    assert cx.verificar() == []
    avisos = " ".join(cx.avisos())
    assert "mover após tratar: NÃO" in avisos and "ActiveSync" in avisos and "[rpa-teste]" in avisos


def test_verificar_exchange_normal(ns):
    _com_conta(ns, 0)
    cx = CaixaOutlookCOM("", "@inbox/RPA_Teste", DESTINOS, criar_pastas=True, namespace=ns)
    assert cx.verificar() == [] and not any("ActiveSync" in a for a in cx.avisos())


def test_data_da_configuracao():
    assert _data("", "x") is None and _data(None, "x") is None
    assert _data("2026-10-27", "x") == datetime(2026, 10, 27)
    from datetime import date
    assert _data(date(2026, 10, 27), "x") == datetime(2026, 10, 27)
    with pytest.raises(ErroConfiguracao):
        _data("27/10/2026", "caixa.recebidos_desde")


# --------------------------------------------------------------------------- #
# proteção contra laço
# --------------------------------------------------------------------------- #
def _email(**kw):
    base = dict(id_mensagem="<h@t>", remetente="a@b.com", nome_remetente="A", assunto="", corpo_html="",
                corpo_texto_bruto="", data_recebimento=None)
    base.update(kw)
    return EmailRecebido(**base)


def _processar(cfg, e):
    return extracao.processar(e, cfg.get("extracao"), cfg.get("filtros.assuntos_resposta_automatica", []),
                              cfg.get("filtros.mensagens_do_rpa"))


def test_resposta_do_proprio_rpa_e_reconhecida(cfg):
    html = ("<html><body><div><p>Prezado(a) fornecedor(a),</p><p>Anexamos o tutorial.</p>"
            "<p>Atenciosamente,<br><b>Equipe Financeiro</b></p>"
            "<p>Resposta automática · protocolo 24921544 · 27/10/2026 16:53</p></div>"
            "<p><b>De:</b> Pedro<br><b>Assunto:</b> [RPA-TESTE] Como enviar a nota fiscal</p>"
            "<p>Bom dia, como envio a NF pelo portal?</p></body></html>")
    e = _processar(cfg, _email(assunto="RE: [RPA-TESTE] Como enviar a nota fiscal", corpo_html=html))
    assert e.gerada_pelo_rpa and "texto" in e.motivo_gerada_pelo_rpa


def test_fornecedor_que_cita_o_rpa_no_historico_nao_e_ignorado(cfg):
    texto = ("Obrigado, mas o link do tutorial não abre. Podem reenviar?\n\n"
             "De: Contas a Pagar\nEnviado: segunda-feira\n"
             "Prezado(a) fornecedor(a), anexamos o tutorial.\n"
             "Resposta automática · protocolo 24921544 · 27/10/2026 16:53")
    e = _processar(cfg, _email(assunto="RE: Como enviar a nota fiscal", corpo_texto_bruto=texto))
    assert not e.gerada_pelo_rpa


@pytest.mark.parametrize("assunto", [
    "[MANUAL – SAP] ENC: [RPA-TESTE] Pagamento",
    "RE: [MANUAL - FORA DA LISTA] Upload",
    "[RPA Dúvidas Financeiras] Erro no tratamento – protocolo 24921544",
])
def test_encaminhamentos_e_avisos_do_rpa_pelo_assunto(cfg, assunto):
    assert _processar(cfg, _email(assunto=assunto, corpo_texto_bruto="qualquer texto")).gerada_pelo_rpa


def test_protecao_desligada(cfg):
    marcas = dict(cfg.get("filtros.mensagens_do_rpa"), ativo=False)
    e = extracao.processar(_email(assunto="[MANUAL – SAP] x"), cfg.get("extracao"), [], marcas)
    assert not e.gerada_pelo_rpa


def test_aviso_de_erro_sem_mover(cfg):
    g = GeradorRespostas(cfg.caminho("respostas.pasta_modelos"), {"faixa_ambiente": ""})
    e = _email(assunto="x")
    assert "foi movido para a pasta" in g.aviso_erro(e, "falha", "", "Erro")
    assert "continua na pasta de entrada" in g.aviso_erro(e, "falha", "", "Erro", movido=False)


# --------------------------------------------------------------------------- #
# ciclo completo com o adaptador COM falso, lendo a Caixa de Entrada
# --------------------------------------------------------------------------- #
@pytest.fixture()
def robo_inbox(cfg, ns):
    cfg.dados["caixa"].update(mover_apos_tratar=False, filtro_assunto="[RPA-TESTE]")
    cx = _caixa_inbox(ns, filtro_assunto="[RPA-TESTE]")
    r = montar_dependencias(cfg, caixa=cx)
    yield r
    r.registro.fechar()


def test_ciclo_na_caixa_de_entrada_responde_uma_vez_e_ignora_a_propria_resposta(robo_inbox, ns):
    original = _msg(ns.inbox, 1, assunto="[RPA-TESTE] Acesso ao Connect",
                    corpo="não consigo acessar o portal connect, esqueci a senha",
                    html="<html><body><p>não consigo acessar o portal connect, esqueci a senha</p></body></html>")
    pessoal = _msg(ns.inbox, 2, assunto="Reunião de equipe", corpo="pauta")
    ns.inbox.Items._itens += [original, pessoal]

    r1 = robo_inbox.executar_ciclo()
    assert r1.contagem()["respondidos"] == 1 and r1.contagem()["erros"] == 0
    resposta = original.gerados[0]
    assert resposta.salvo and resposta.Attachments.Count == 1      # rascunho com o tutorial
    assert original.pasta is ns.inbox and original.Categories == "RPA - Simulado"
    assert pessoal.Categories == "" and pessoal.UnRead is True     # fora do filtro: intocado

    # 2º ciclo: nada novo
    assert robo_inbox.executar_ciclo().contagem()["lidos"] == 0

    # a resposta do robô chega na Caixa de Entrada (teste em que você é o fornecedor)
    volta = _msg(ns.inbox, 3, assunto="RE: [RPA-TESTE] Acesso ao Connect", html=resposta.HTMLBody,
                 de="pedro@empresa.com.br")
    ns.inbox.Items._itens.append(volta)
    r3 = robo_inbox.executar_ciclo()
    [res] = r3.resultados
    assert res.status == Status.IGNORADO and res.acao == Acao.IGNORAR
    assert res.motivo_ignorado.startswith(MotivoIgnorado.PROPRIO_RPA)
    assert volta.gerados == [] and volta.Categories == "RPA - Ignorado"


def test_erro_no_modo_sem_mover_nao_gera_aviso_em_laco(robo_inbox, ns, cfg):
    cfg.dados["seguranca"]["destinatarios_permitidos"] = ["@empresa-exemplo.com.br"]  # bloqueia o fornecedor
    robo_inbox.permitidos = cfg.dados["seguranca"]["destinatarios_permitidos"]
    msg = _msg(ns.inbox, 1, assunto="[RPA-TESTE] Reembolso", corpo="preciso de reembolso",
               html="<html><body><p>preciso de reembolso</p></body></html>")
    ns.inbox.Items._itens.append(msg)
    [res] = robo_inbox.executar_ciclo().resultados
    assert res.status == Status.ERRO and "NÃO movido" not in res.erro
    assert msg.Categories == "RPA - Erro" and msg.pasta is ns.inbox
    assert robo_inbox.executar_ciclo().contagem()["lidos"] == 0    # não volta a cada ciclo


def test_fabrica_le_as_opcoes_novas(cfg, monkeypatch):
    capturado = {}

    class Falsa:
        def __init__(self, *a, **kw):
            capturado.update(kw)

    monkeypatch.setattr("rpa_duvidas.caixa.outlook_com.CaixaOutlookCOM", Falsa)
    cfg.dados["caixa"].update(tipo="outlook_com", mover_apos_tratar=False, filtro_assunto="[RPA-TESTE]",
                              recebidos_desde="2026-10-27", max_varredura=300)
    criar_caixa(cfg)
    assert capturado["mover_apos_tratar"] is False and capturado["filtro_assunto"] == "[RPA-TESTE]"
    assert capturado["recebidos_desde"] == datetime(2026, 10, 27) and capturado["max_varredura"] == 300
    assert "RPA - Simulado" in capturado["categorias_rpa"]
