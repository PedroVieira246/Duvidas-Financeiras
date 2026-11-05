"""Outlook COM FALSO com destinatários "de verdade" (v0.3.0 – testes da trava, seção 6.2).

Diferente dos objetos de test_outlook_com, aqui ``To``/``CC``/``BCC`` e a coleção
``Recipients`` ficam sincronizados como no Outlook: atribuir ``To`` troca os
destinatários do tipo Para, ``Recipients.Remove(i)`` remove um item, ``Reply()``
traz o remetente (e o ``Reply-To``), ``ReplyAll()`` traz também Para e CC
originais. Dá para simular o risco da seção 11 ("Recipients.Remove deixar um
destinatário escondido") com ``remove_defeituoso=True``.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from rpa_duvidas.caixa.outlook_com import PR_INTERNET_MESSAGE_ID, PR_SMTP_ADDRESS

OL_TO, OL_CC, OL_BCC = 1, 2, 3
OL_ESCONDIDO = 0          # só nos testes: destinatário que Remove() e To/CC/BCC não alcançam


class Colecao:
    def __init__(self, itens=()):
        self._itens = list(itens)

    @property
    def Count(self):
        return len(self._itens)

    def Item(self, i):
        return self._itens[i - 1]


class Acessor:
    def __init__(self, props):
        self.props = props

    def GetProperty(self, tag):
        if tag not in self.props:
            raise Exception("propriedade ausente")
        return self.props[tag]


class Destinatario:
    def __init__(self, endereco: str, tipo: int = OL_TO, smtp_visivel: bool = True):
        self.Address = endereco
        self.Type = tipo
        self.PropertyAccessor = Acessor({PR_SMTP_ADDRESS: endereco} if smtp_visivel else {})
        self.AddressEntry = None


class Destinatarios(Colecao):
    def __init__(self, dono, remove_defeituoso=False):
        super().__init__()
        self.dono = dono
        self.remove_defeituoso = remove_defeituoso

    def Add(self, endereco, tipo=OL_TO):
        d = Destinatario(endereco, tipo)
        self._itens.append(d)
        return d

    def Remove(self, i):
        if self._itens[i - 1].Type == OL_ESCONDIDO:
            return                                    # o "destinatário escondido" da seção 11 não sai
        del self._itens[i - 1]

    def ResolveAll(self):
        return True

    def enderecos(self) -> List[str]:
        return [d.Address.lower() for d in self._itens]


class Anexos(Colecao):
    def Add(self, caminho):
        self._itens.append(type("A", (), {"FileName": str(caminho), "PropertyAccessor": Acessor({})})())


class Email:
    """MailItem falso: e-mail recebido, resposta, encaminhamento ou mensagem nova."""

    def __init__(self, caixa: "Caixa", pasta=None, *, de="", assunto="", corpo="", para="", cc="", reply_to="",
                 data=None, id_msg=None, remove_defeituoso=False):
        self.caixa, self.pasta = caixa, pasta
        self.Class, self.MessageClass = 43, "IPM.Note"
        self.Subject, self.Body = assunto, corpo
        self.HTMLBody = f"<html><body><p>{corpo}</p></body></html>"
        self.SenderEmailType, self.SenderEmailAddress, self.SenderName = "SMTP", de, "Remetente"
        self.ReceivedTime = data or datetime(2026, 11, 3, 9, 0)
        self.UnRead, self.Categories, self.ConversationID = True, "", "conv"
        self.EntryID = f"entry-{id(self)}"
        self.Attachments = Anexos()
        self.PropertyAccessor = Acessor({PR_INTERNET_MESSAGE_ID: id_msg or f"<{id(self)}@x>"})
        self.Sender = None
        self.Recipients = Destinatarios(self, remove_defeituoso)
        self.reply_to = reply_to
        self.remove_defeituoso = remove_defeituoso
        self.salvo = self.enviado = self.descartado = False
        self.salvo_como: Optional[str] = None
        for e in filter(None, [x.strip() for x in para.split(";")]):
            self.Recipients.Add(e, OL_TO)
        for e in filter(None, [x.strip() for x in cc.split(";")]):
            self.Recipients.Add(e, OL_CC)

    # To/CC/BCC sincronizados com Recipients, como no Outlook
    def _campo(self, tipo):
        return "; ".join(d.Address for d in self.Recipients._itens if d.Type == tipo)

    def _definir(self, tipo, valor):
        self.Recipients._itens = [d for d in self.Recipients._itens if d.Type != tipo]
        for e in filter(None, [x.strip() for x in str(valor or "").split(";")]):
            self.Recipients.Add(e, tipo)

    To = property(lambda self: self._campo(OL_TO), lambda self, v: self._definir(OL_TO, v))
    CC = property(lambda self: self._campo(OL_CC), lambda self, v: self._definir(OL_CC, v))
    BCC = property(lambda self: self._campo(OL_BCC), lambda self, v: self._definir(OL_BCC, v))

    def _nova(self, assunto):
        m = Email(self.caixa, assunto=assunto, remove_defeituoso=self.remove_defeituoso)
        self.caixa.geradas.append(m)
        return m

    def Reply(self):
        r = self._nova(f"RE: {self.Subject}")
        r.Recipients.Add(self.reply_to or self.SenderEmailAddress, OL_TO)
        if self.remove_defeituoso:
            r.Recipients.Add(self.SenderEmailAddress, OL_ESCONDIDO)
        return r

    def ReplyAll(self):
        r = self.Reply()
        for d in self.Recipients._itens:
            r.Recipients.Add(d.Address, d.Type if d.Type != OL_BCC else OL_CC)
        return r

    def Forward(self):
        return self._nova(f"ENC: {self.Subject}")

    def Save(self):
        self.salvo = True

    def Send(self):
        self.enviado = True

    def Close(self, modo):
        self.descartado = True

    def SaveAs(self, caminho, tipo):
        self.salvo_como = caminho
        self.caixa.salvos_como.append((caminho, tipo))
        from pathlib import Path

        Path(caminho).write_bytes(b"MSG-FALSO")

    def Move(self, destino):
        raise AssertionError("na caixa pessoal nada é movido")


class Pasta:
    def __init__(self, nome, pai=None):
        self.Name, self.Parent = nome, pai
        self.Folders = Colecao()
        self.Folders.Add = lambda n: self._add(n)
        self.Items = Itens()

    def _add(self, nome):
        p = Pasta(nome, self)
        self.Folders._itens.append(p)
        return p


class Itens(Colecao):
    def Sort(self, campo, desc=False):
        self._itens.sort(key=lambda m: m.ReceivedTime, reverse=bool(desc))

    def Restrict(self, filtro):
        return Itens([m for m in self._itens if m.UnRead])


class Caixa:
    """Namespace + Application falsos. ``geradas``: todas as mensagens criadas pelo robô."""

    def __init__(self, remove_defeituoso=False):
        self.raiz = Pasta("maria.laura@empresa-exemplo.com.br")
        self.inbox = self.raiz._add("Caixa de Entrada")
        self.Categories = Colecao()
        self.Categories.Add = lambda nome: self.Categories._itens.append(type("C", (), {"Name": nome})())
        self.Stores = Colecao()
        self.Accounts = Colecao()
        self.geradas: List[Email] = []
        self.salvos_como = []
        self.remove_defeituoso = remove_defeituoso

    def GetDefaultFolder(self, n):
        return self.inbox

    def CreateItem(self, tipo):
        m = Email(self, remove_defeituoso=self.remove_defeituoso)
        self.geradas.append(m)
        return m

    def receber(self, **kw) -> Email:
        m = Email(self, self.inbox, remove_defeituoso=self.remove_defeituoso, **kw)
        self.inbox.Items._itens.append(m)
        return m

    def saidas(self) -> List[Email]:
        """Mensagens que saíram (enviadas) ou ficaram salvas como rascunho."""
        return [m for m in self.geradas if m.enviado or m.salvo]
