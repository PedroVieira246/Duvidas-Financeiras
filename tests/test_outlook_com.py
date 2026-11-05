"""Testa a lógica do adaptador Outlook COM com objetos FALSOS.

Não substitui o teste real no Windows (scripts/teste_conexao_outlook.py), mas
garante a navegação de pastas, a conversão do e-mail e as chamadas de
resposta/movimentação sem precisar do Outlook.
"""
from datetime import datetime

import pytest

from rpa_duvidas.caixa.outlook_com import (
    PR_ATTACH_CONTENT_ID, PR_INTERNET_MESSAGE_ID, PR_TRANSPORT_HEADERS, CaixaOutlookCOM, inserir_no_body,
)
from rpa_duvidas.caixa.base import ErroCaixa


class Colecao:
    def __init__(self, itens=()):
        self._itens = list(itens)

    @property
    def Count(self):
        return len(self._itens)

    def Item(self, i):
        return self._itens[i - 1]


class Pastas(Colecao):
    def __init__(self, pai):
        super().__init__()
        self.pai = pai

    def Add(self, nome):
        p = Pasta(nome, self.pai)
        self._itens.append(p)
        return p


class Itens(Colecao):
    def Sort(self, campo, desc=False):
        self._itens.sort(key=lambda m: m.ReceivedTime, reverse=bool(desc))

    def Restrict(self, filtro):
        return Itens([m for m in self._itens if m.UnRead])


class Pasta:
    def __init__(self, nome, pai=None):
        self.Name, self.Parent = nome, pai
        self.Folders = Pastas(self)
        self.Items = Itens()


class Acessor:
    def __init__(self, props):
        self.props = props

    def GetProperty(self, tag):
        if tag not in self.props:
            raise Exception("propriedade ausente")
        return self.props[tag]


class Anexo:
    def __init__(self, nome, inline=False):
        self.FileName = nome
        self.PropertyAccessor = Acessor({PR_ATTACH_CONTENT_ID: "img001"} if inline else {})


class Anexos(Colecao):
    def Add(self, caminho):
        self._itens.append(Anexo(caminho))


class Mensagem:
    """MailItem falso (também usado como resposta/rascunho)."""

    def __init__(self, pasta=None, **kw):
        self.pasta = pasta
        self.Class, self.MessageClass = 43, "IPM.Note"
        self.Subject, self.Body = kw.get("assunto", ""), kw.get("corpo", "")
        self.HTMLBody = kw.get("html", "<html><body><p>original</p></body></html>")
        self.SenderEmailType, self.SenderEmailAddress = kw.get("tipo", "SMTP"), kw.get("de", "")
        self.SenderName = "Fornecedor"
        self.ReceivedTime = kw.get("data", datetime(2026, 10, 19, 9, 0))
        self.UnRead, self.Categories, self.CC, self.To = True, "", "", ""
        self.ConversationID, self.EntryID = "conv", f"entry-{id(self)}"
        self.Attachments = Anexos(kw.get("anexos", []))
        self.Recipients = Colecao()
        self.Recipients.ResolveAll = lambda: True
        self.PropertyAccessor = Acessor(kw.get("props", {}))
        self.Sender = kw.get("sender")
        self.salvo = self.enviado = False
        self.gerados = []

    def Reply(self):
        r = Mensagem(html="<html><body><p>citado</p></body></html>")
        self.gerados.append(r)
        return r

    ReplyAll = Reply

    def Forward(self):
        return self.Reply()

    def Save(self):
        self.salvo = True

    def Send(self):
        self.enviado = True

    def Move(self, destino):
        self.pasta.Items._itens.remove(self)
        destino.Items._itens.append(self)
        self.pasta = destino


class Namespace:
    def __init__(self):
        self.raiz = Pasta("pedro@empresa.com.br")
        self.inbox = self.raiz.Folders.Add("Caixa de Entrada")
        self.Categories = Colecao()
        self.Categories.Add = lambda nome: self.Categories._itens.append(type("C", (), {"Name": nome})())
        self.Stores = Colecao()

    def GetDefaultFolder(self, n):
        return self.inbox


DESTINOS = {k: f"@inbox/RPA_Teste/{k.capitalize()}" for k in ("respondidos", "encaminhados", "erro", "ignorados")}


@pytest.fixture()
def ns():
    return Namespace()


def _caixa(ns, criar=True):
    return CaixaOutlookCOM("", "@inbox/RPA_Teste", DESTINOS, criar_pastas=criar, namespace=ns, aplicativo=None)


def test_inserir_no_body():
    assert inserir_no_body("<html><BODY class='x'><p>a</p></body></html>", "<p>novo</p>") == \
        "<html><BODY class='x'><p>novo</p><p>a</p></body></html>"
    assert inserir_no_body("", "<p>novo</p>") == "<p>novo</p>"


def test_cria_pasta_de_teste_dentro_da_caixa_de_entrada(ns):
    cx = _caixa(ns)
    assert cx.pasta_entrada.Name == "RPA_Teste" and cx.pasta_entrada.Parent is ns.inbox
    assert cx.verificar() == []
    assert {p.Name for p in [cx.pasta_entrada.Folders.Item(i) for i in range(1, 5)]} == \
        {"Respondidos", "Encaminhados", "Erro", "Ignorados"}


def test_sem_permissao_para_criar_pasta(ns):
    with pytest.raises(ErroCaixa, match="não existe"):
        _caixa(ns, criar=False)


def test_leitura_converte_e_ignora_imagem_inline(ns):
    cx = _caixa(ns)
    msg = Mensagem(
        cx.pasta_entrada, assunto="Acesso", de="FIN@Fornecedor.com.br",
        anexos=[Anexo("logo.png", inline=True), Anexo("nf.pdf")],
        props={PR_INTERNET_MESSAGE_ID: "<abc@fornecedor>", PR_TRANSPORT_HEADERS: "Auto-Submitted: no\r\n"},
    )
    cx.pasta_entrada.Items._itens.append(msg)
    [e] = cx.ler_pendentes(10)
    assert e.id_mensagem == "<abc@fornecedor>" and e.remetente == "fin@fornecedor.com.br"
    assert e.nomes_anexos == ["nf.pdf"] and e.tem_anexos
    assert e.cabecalhos["auto-submitted"] == "no"


def test_remetente_exchange_interno(ns):
    cx = _caixa(ns)
    usuario = type("U", (), {"PrimarySmtpAddress": "Ana@Empresa.com.br"})()
    sender = type("S", (), {"GetExchangeUser": lambda self: usuario})()
    cx.pasta_entrada.Items._itens.append(Mensagem(cx.pasta_entrada, tipo="EX", de="/O=EXCH/CN=ANA", sender=sender))
    assert cx.ler_pendentes(10)[0].remetente == "ana@empresa.com.br"


def test_responder_em_rascunho_com_cc_anexo_e_mover(ns, tmp_path):
    cx = _caixa(ns)
    msg = Mensagem(cx.pasta_entrada, assunto="Acesso", de="f@x.com", props={PR_INTERNET_MESSAGE_ID: "<1@x>"})
    cx.pasta_entrada.Items._itens.append(msg)
    [e] = cx.ler_pendentes(10)
    anexo = tmp_path / "tut.pptx"
    cx.responder(e, "<p>RESPOSTA</p>", anexos=[anexo], cc=["analistas@empresa.com.br"], enviar=False)
    resp = msg.gerados[0]
    assert resp.salvo and not resp.enviado                       # simulação = rascunho
    assert resp.CC == "analistas@empresa.com.br"
    assert resp.HTMLBody.startswith("<html><body><p>RESPOSTA</p><p>citado</p>")
    assert resp.Attachments.Item(1).FileName == str(anexo)

    cx.finalizar(e, "respondidos", "RPA - Simulado")
    assert msg.pasta.Name == "Respondidos" and msg.UnRead is False
    assert msg.Categories == "RPA - Simulado"


def test_encaminhar_envio_real(ns):
    cx = _caixa(ns)
    msg = Mensagem(cx.pasta_entrada, assunto="Pagamento", de="f@x.com", props={PR_INTERNET_MESSAGE_ID: "<2@x>"})
    cx.pasta_entrada.Items._itens.append(msg)
    [e] = cx.ler_pendentes(10)
    cx.encaminhar(e, ["a@empresa.com.br", "b@empresa.com.br"], "[MANUAL – SAP]", "<p>nota</p>", enviar=True)
    enc = msg.gerados[0]
    assert enc.enviado and enc.To == "a@empresa.com.br; b@empresa.com.br"
    assert enc.Subject == "[MANUAL – SAP] Pagamento"


def test_ler_somente_nao_lidos(ns):
    cx = CaixaOutlookCOM("", "@inbox/RPA_Teste", DESTINOS, criar_pastas=True, ler_todos=False, namespace=ns)
    lido = Mensagem(cx.pasta_entrada, de="a@x.com", props={PR_INTERNET_MESSAGE_ID: "<l@x>"})
    lido.UnRead = False
    cx.pasta_entrada.Items._itens += [lido, Mensagem(cx.pasta_entrada, de="b@x.com", props={PR_INTERNET_MESSAGE_ID: "<n@x>"})]
    assert [e.remetente for e in cx.ler_pendentes(10)] == ["b@x.com"]
