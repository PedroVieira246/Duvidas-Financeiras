"""Caixa de e-mail via Outlook clássico + pywin32/COM (F03 – MVP e piloto).

Requisitos da máquina:
  * Windows com Outlook CLÁSSICO instalado e configurado (o "novo Outlook"
    não tem COM);
  * sessão Windows logada (o Agendador de Tarefas precisa da opção
    "Executar somente quando o usuário estiver conectado");
  * ``pip install pywin32``.

Nenhum endereço ou pasta é fixo aqui: tudo vem de ``caixa.*`` na
configuração. Em dev a conta é a sua caixa individual; em prod, a conta de
serviço.

v0.2.1 – modo "sem mover" (``caixa.mover_apos_tratar: false``): para contas
configuradas como Exchange ActiveSync, em que o Outlook recusa o ``Move`` via
COM, e para ler direto da Caixa de Entrada. O e-mail tratado fica onde está,
marcado como lido e com a categoria "RPA - …"; na leitura seguinte, itens com
categoria do RPA são pulados (equivale a já estar em outra pasta).
Filtros opcionais de leitura: ``caixa.filtro_assunto`` (só assuntos que
contêm o texto), ``caixa.recebidos_desde`` (data mínima) e
``caixa.max_varredura`` (quantos itens recentes examinar).

Para testes fora do Windows, ``namespace`` e ``aplicativo`` podem ser
injetados (ver tests/test_outlook_com.py).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

from ..extracao import parse_cabecalhos
from ..modelos import EmailRecebido
from .base import CaixaEmail, ErroCaixa, ErroSeguranca, TravaDestinatarios

log = logging.getLogger(__name__)

# Constantes do modelo de objetos do Outlook
OL_FOLDER_INBOX = 6
OL_ACCOUNT_EAS = 4        # OlAccountType.olEas (Exchange ActiveSync)
OL_MAIL_ITEM = 0          # CreateItem
OL_DISCARD = 1            # MailItem.Close(olDiscard)
OL_MSG = 3                # MailItem.SaveAs(caminho, olMSG)
CLASSE_MAIL = 43
CLASSE_REPORT = 46

# Propriedades MAPI (PropertyAccessor)
PR_INTERNET_MESSAGE_ID = "http://schemas.microsoft.com/mapi/proptag/0x1035001F"
PR_TRANSPORT_HEADERS = "http://schemas.microsoft.com/mapi/proptag/0x007D001F"
PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001F"
PR_SENDER_SMTP = "http://schemas.microsoft.com/mapi/proptag/0x5D01001F"
PR_LAST_VERB_EXECUTED = "http://schemas.microsoft.com/mapi/proptag/0x10810003"   # v0.3.0 (seção 6.1)

_RE_BODY = re.compile(r"(<body[^>]*>)", re.I)


def inserir_no_body(html_existente: str, trecho: str) -> str:
    """Insere ``trecho`` logo após ``<body>`` (mantém o histórico abaixo)."""
    html_existente = html_existente or ""
    if _RE_BODY.search(html_existente):
        return _RE_BODY.sub(lambda m: m.group(1) + trecho, html_existente, count=1)
    return trecho + html_existente


def _iterar(colecao: Any) -> Iterator[Any]:
    """Itera coleções COM (base 1) de forma segura."""
    for i in range(1, int(colecao.Count) + 1):
        yield colecao.Item(i)


def _prop(obj: Any, nome: str, padrao: Any = "") -> Any:
    try:
        return getattr(obj, nome)
    except Exception:
        return padrao


def _data_local(valor: Any) -> Optional[datetime]:
    """Converte a data do COM (pywintypes, com fuso) em ``datetime`` simples."""
    if not valor:
        return None
    try:
        return datetime(valor.year, valor.month, valor.day, valor.hour, valor.minute, valor.second)
    except Exception:
        return None


def _prop_mapi(obj: Any, tag: str, padrao: str = "") -> str:
    try:
        valor = obj.PropertyAccessor.GetProperty(tag)
        return str(valor) if valor is not None else padrao
    except Exception:
        return padrao


class CaixaOutlookCOM(CaixaEmail):
    def __init__(
        self,
        conta: str,
        pasta_entrada: str,
        pastas_destino: Dict[str, str],
        *,
        criar_pastas: bool = False,
        ler_todos: bool = True,
        enviar_em_nome_de: str = "",
        mover_apos_tratar: bool = True,
        filtro_assunto: str = "",
        recebidos_desde: Optional[datetime] = None,
        max_varredura: int = 500,
        categorias_rpa: Sequence[str] = (),
        trava: Optional[TravaDestinatarios] = None,
        namespace: Any = None,
        aplicativo: Any = None,
    ):
        if namespace is None:
            try:
                import pythoncom
                import win32com.client
            except ImportError as e:  # pragma: no cover - só no Windows
                raise ErroCaixa("pywin32 não instalado. Rode: pip install pywin32") from e
            pythoncom.CoInitialize()
            try:
                aplicativo = win32com.client.Dispatch("Outlook.Application")
                namespace = aplicativo.GetNamespace("MAPI")
            except Exception as e:  # pragma: no cover
                raise ErroCaixa(
                    "Não foi possível abrir o Outlook via COM. Verifique se o Outlook "
                    "CLÁSSICO está instalado e configurado nesta sessão do Windows "
                    f"(o novo Outlook não suporta COM). Detalhe: {e}"
                ) from e
        self.app = aplicativo
        self.ns = namespace
        self.conta = (conta or "").strip()
        self.criar_pastas = criar_pastas
        self.ler_todos = ler_todos
        self.enviar_em_nome_de = (enviar_em_nome_de or "").strip()
        self.mover = bool(mover_apos_tratar)
        self.filtro_assunto = (filtro_assunto or "").strip().lower()
        self.recebidos_desde = recebidos_desde
        self.max_varredura = max(1, int(max_varredura or 500))
        self.categorias_rpa = {c.strip().lower() for c in categorias_rpa if c and c.strip()}
        self._caminhos_destino = dict(pastas_destino)
        self._itens: Dict[str, Any] = {}
        self.trava = trava

        self.raiz, self.inbox = self._localizar_conta()
        self.pasta_entrada = self._resolver_pasta(pasta_entrada, criar=criar_pastas)
        self._destinos: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # pastas
    # ------------------------------------------------------------------ #
    def _localizar_conta(self):
        if not self.conta:
            inbox = self.ns.GetDefaultFolder(OL_FOLDER_INBOX)
            return inbox.Parent, inbox
        alvo = self.conta.lower()
        for store in _iterar(self.ns.Stores):
            nomes = {str(_prop(store, "DisplayName", "")).lower()}
            try:
                nomes.add(str(store.GetRootFolder().Name).lower())
            except Exception:
                pass
            if alvo in nomes:
                raiz = store.GetRootFolder()
                try:
                    inbox = store.GetDefaultFolder(OL_FOLDER_INBOX)
                except Exception:
                    inbox = self._filho(raiz, ("Caixa de Entrada", "Inbox"))
                return raiz, inbox
        raise ErroCaixa(
            f"Conta/caixa '{self.conta}' não encontrada no perfil do Outlook. "
            "Adicione-a ao Outlook (conta ou caixa compartilhada) e confira caixa.conta."
        )

    @staticmethod
    def _filho(pasta: Any, nomes: Sequence[str]) -> Optional[Any]:
        alvos = {n.lower() for n in nomes}
        for sub in _iterar(pasta.Folders):
            if str(sub.Name).lower() in alvos:
                return sub
        return None

    def _resolver_pasta(self, caminho: str, *, criar: bool) -> Any:
        partes = [p for p in str(caminho).replace("\\", "/").split("/") if p]
        if not partes:
            raise ErroCaixa("Caminho de pasta vazio na configuração")
        if partes[0].lower() == "@inbox":
            atual, partes = self.inbox, partes[1:]
        else:
            atual = self.raiz
        for nome in partes:
            filho = self._filho(atual, (nome,))
            if filho is None:
                if not criar:
                    raise ErroCaixa(f"Pasta '{nome}' não existe em '{caminho}' (caixa.criar_pastas_ausentes=false)")
                log.info("Criando pasta do Outlook: %s", nome)
                filho = atual.Folders.Add(nome)
            atual = filho
        return atual

    def _destino(self, chave: str) -> Any:
        if chave not in self._destinos:
            caminho = self._caminhos_destino.get(chave)
            if not caminho:
                raise ErroCaixa(f"Destino não configurado: caixa.pastas_destino.{chave}")
            self._destinos[chave] = self._resolver_pasta(caminho, criar=self.criar_pastas)
        return self._destinos[chave]

    # ------------------------------------------------------------------ #
    # leitura (RF01 / RF02)
    # ------------------------------------------------------------------ #
    @property
    def _leitura_filtrada(self) -> bool:
        return (not self.mover) or bool(self.filtro_assunto) or self.recebidos_desde is not None

    def _ja_tratado(self, item: Any) -> bool:
        """Item que já recebeu uma categoria do RPA (modo sem mover)."""
        if not self.categorias_rpa:
            return False
        atuais = {c.strip().lower() for c in str(_prop(item, "Categories", "") or "").split(",") if c.strip()}
        return bool(atuais & self.categorias_rpa)

    def _selecionar_filtrado(self, limite: int, aceitar=None) -> List[Any]:
        """Examina os itens mais recentes primeiro e devolve os aceitos, mais antigos primeiro.

        Assim uma Caixa de Entrada grande não é lida inteira e e-mails já
        tratados (que ficaram na pasta) não ocupam o lote.
        """
        itens = self.pasta_entrada.Items
        itens.Sort("[ReceivedTime]", True)            # mais novos primeiro
        aceitos: List[Any] = []
        for n, item in enumerate(_iterar(itens), start=1):
            if n > self.max_varredura:
                break
            recebido = _data_local(_prop(item, "ReceivedTime", None))
            if self.recebidos_desde is not None and recebido is not None and recebido < self.recebidos_desde:
                break                                  # ordenado: o resto é mais antigo
            if int(_prop(item, "Class", CLASSE_MAIL) or CLASSE_MAIL) not in (CLASSE_MAIL, CLASSE_REPORT):
                continue                               # convites de reunião, tarefas etc.
            if self.filtro_assunto and self.filtro_assunto not in str(_prop(item, "Subject", "")).lower():
                continue
            if not self.ler_todos and not _prop(item, "UnRead", True):
                continue
            if not self.mover and self._ja_tratado(item):
                continue
            if aceitar is not None:
                classe = int(_prop(item, "Class", CLASSE_MAIL) or CLASSE_MAIL)
                remetente = self._smtp_remetente(item) if classe == CLASSE_MAIL else ""
                if not aceitar(remetente):
                    self.descartados += 1          # não fornecedor: não é convertido nem alterado
                    continue
            aceitos.append(item)
        aceitos.reverse()                              # processa na ordem de chegada
        return aceitos[: max(0, int(limite))]

    def ler_pendentes(self, limite: int, aceitar_remetente=None) -> List[EmailRecebido]:
        self.descartados = 0
        if self._leitura_filtrada or aceitar_remetente is not None:
            snapshot = self._selecionar_filtrado(limite, aceitar_remetente)
        else:
            itens = self.pasta_entrada.Items
            itens.Sort("[ReceivedTime]", False)
            if not self.ler_todos:
                itens = itens.Restrict("[UnRead] = True")
            snapshot = list(_iterar(itens))[: max(0, int(limite))]
        emails: List[EmailRecebido] = []
        for item in snapshot:
            try:
                em = self._converter(item)
            except Exception as e:  # um item ruim não derruba a leitura
                log.exception("Falha ao ler item do Outlook: %s", e)
                continue
            self._itens[em.chave] = item
            emails.append(em)
        return emails

    def _converter(self, item: Any) -> EmailRecebido:
        classe = int(_prop(item, "Class", CLASSE_MAIL) or CLASSE_MAIL)
        id_msg = _prop_mapi(item, PR_INTERNET_MESSAGE_ID) or str(_prop(item, "EntryID", ""))
        anexos, tem_anexo_real = self._anexos(item)
        data = _data_local(_prop(item, "ReceivedTime", None))
        return EmailRecebido(
            id_mensagem=id_msg,
            remetente=self._smtp_remetente(item) if classe == CLASSE_MAIL else "",
            nome_remetente=str(_prop(item, "SenderName", "")),
            assunto=str(_prop(item, "Subject", "")),
            corpo_html=str(_prop(item, "HTMLBody", "")),
            corpo_texto_bruto=str(_prop(item, "Body", "")),
            data_recebimento=data,
            tem_anexos=tem_anexo_real,
            nomes_anexos=anexos,
            cabecalhos=parse_cabecalhos(_prop_mapi(item, PR_TRANSPORT_HEADERS)),
            classe_mensagem=str(_prop(item, "MessageClass", "IPM.Note")),
            id_conversa=str(_prop(item, "ConversationID", "")),
            ultimo_verbo=self._ultimo_verbo(item),
        )

    @staticmethod
    def _ultimo_verbo(item: Any) -> int:
        try:
            return int(_prop_mapi(item, PR_LAST_VERB_EXECUTED, "0") or 0)
        except ValueError:
            return 0

    @staticmethod
    def _anexos(item: Any):
        """Só registra nomes (RF02: anexos nunca são lidos). Ignora imagens inline."""
        nomes, real = [], False
        try:
            for anexo in _iterar(item.Attachments):
                nome = str(_prop(anexo, "FileName", ""))
                if _prop_mapi(anexo, PR_ATTACH_CONTENT_ID):
                    continue  # imagem embutida (ex.: logo da assinatura)
                nomes.append(nome)
                real = True
        except Exception:
            pass
        return nomes, real

    @staticmethod
    def _smtp_remetente(item: Any) -> str:
        try:
            if str(_prop(item, "SenderEmailType", "")).upper() == "EX":
                remetente = item.Sender
                usuario = remetente.GetExchangeUser() if remetente is not None else None
                if usuario is not None and usuario.PrimarySmtpAddress:
                    return str(usuario.PrimarySmtpAddress).lower()
                smtp = _prop_mapi(item, PR_SENDER_SMTP)
                if smtp:
                    return smtp.lower()
            return str(_prop(item, "SenderEmailAddress", "")).lower()
        except Exception:
            return str(_prop(item, "SenderEmailAddress", "")).lower()

    @staticmethod
    def _smtp_destinatario(rec: Any) -> str:
        smtp = _prop_mapi(rec, PR_SMTP_ADDRESS)
        return (smtp or str(_prop(rec, "Address", ""))).lower()

    def _item(self, email: EmailRecebido) -> Any:
        item = self._itens.get(email.chave)
        if item is None:
            raise ErroCaixa(f"Item do Outlook não está em memória: {email.id_mensagem}")
        return item

    # ------------------------------------------------------------------ #
    # ações (RF05, RF07, RF08, RF09, RF11)
    # ------------------------------------------------------------------ #
    def destinatarios_resposta(self, email: EmailRecebido, responder_todos: bool) -> List[str]:
        enderecos = [email.remetente]
        if responder_todos:
            item = self._item(email)
            enderecos += [self._smtp_destinatario(r) for r in _iterar(item.Recipients)]
        return [e for e in enderecos if e]

    @staticmethod
    def _smtp_envio(rec: Any) -> str:
        """SMTP de um destinatário de mensagem NOVA (ainda não enviada). Vazio = não identificado."""
        smtp = _prop_mapi(rec, PR_SMTP_ADDRESS)
        if not smtp:
            try:
                usuario = rec.AddressEntry.GetExchangeUser()
                smtp = str(usuario.PrimarySmtpAddress or "") if usuario is not None else ""
            except Exception:
                smtp = ""
        if not smtp:
            endereco = str(_prop(rec, "Address", "") or "")
            smtp = endereco if "@" in endereco else ""
        return smtp.strip().lower()

    @staticmethod
    def _limpar_destinatarios(msg: Any) -> None:
        """Remove todos os destinatários (do último para o primeiro – seção 6.2, item 2)."""
        for i in range(int(msg.Recipients.Count), 0, -1):
            msg.Recipients.Remove(i)
        for campo in ("CC", "BCC"):
            try:
                setattr(msg, campo, "")
            except Exception:
                pass

    @staticmethod
    def _descartar(msg: Any) -> None:
        try:
            msg.Close(OL_DISCARD)
        except Exception:
            pass

    def _travar(self, msg: Any, operacao: str, extra: Optional[TravaDestinatarios]) -> None:
        """Trava obrigatória (seção 6.2, item 4): relê ``Recipients`` imediatamente antes do Send/Save."""
        travas = [t for t in (self.trava, extra) if t is not None]
        if not travas:
            return
        enderecos = [self._smtp_envio(r) for r in _iterar(msg.Recipients)]
        try:
            for t in travas:
                t.conferir(operacao, enderecos)
        except ErroSeguranca:
            self._descartar(msg)
            raise

    def _concluir(self, msg: Any, enviar: bool, operacao: str = "", extra: Optional[TravaDestinatarios] = None) -> str:
        try:
            msg.Recipients.ResolveAll()
        except Exception:
            pass
        self._travar(msg, operacao, extra)
        if enviar:
            msg.Send()
            return "enviado"
        msg.Save()  # rascunho na pasta Rascunhos (RF11)
        return str(_prop(msg, "EntryID", "rascunho"))

    def responder(self, email, corpo_html, *, anexos=(), cc=(), responder_todos=False, enviar=False,
                  redirecionar_para=None, prefixo_assunto="") -> str:
        item = self._item(email)
        resp = item.ReplyAll() if responder_todos else item.Reply()
        extra = None
        if redirecionar_para:
            # envio de teste (D02): só o destino padrão, sem CC – a trava confere de novo no _concluir
            self._limpar_destinatarios(resp)
            resp.To = redirecionar_para
            extra = TravaDestinatarios([redirecionar_para], [], [])
        elif cc:
            atuais = [c.strip() for c in str(_prop(resp, "CC", "") or "").split(";") if c.strip()]
            resp.CC = "; ".join(atuais + [c for c in cc if c not in atuais])
        if self.enviar_em_nome_de:
            resp.SentOnBehalfOfName = self.enviar_em_nome_de
        if prefixo_assunto:
            resp.Subject = f"{prefixo_assunto} {_prop(resp, 'Subject', '')}".strip()
        resp.HTMLBody = inserir_no_body(resp.HTMLBody, corpo_html)
        for caminho in anexos:
            resp.Attachments.Add(str(Path(caminho)))
        return self._concluir(resp, enviar, "responder", extra)

    def encaminhar(self, email, para, prefixo_assunto, nota_html, *, enviar=False) -> str:
        item = self._item(email)
        enc = item.Forward()
        enc.To = "; ".join(para)
        enc.Subject = f"{prefixo_assunto} {_prop(item, 'Subject', '')}".strip()
        if self.enviar_em_nome_de:
            enc.SentOnBehalfOfName = self.enviar_em_nome_de
        enc.HTMLBody = inserir_no_body(enc.HTMLBody, nota_html)
        return self._concluir(enc, enviar, "encaminhar")

    def enviar_novo(self, para, assunto, corpo_html, *, enviar=False) -> str:
        if self.app is None:
            raise ErroCaixa("Aplicativo Outlook indisponível para criar mensagem")
        msg = self.app.CreateItem(OL_MAIL_ITEM)
        msg.To = "; ".join(para)
        msg.Subject = assunto
        if self.enviar_em_nome_de:
            msg.SentOnBehalfOfName = self.enviar_em_nome_de
        msg.HTMLBody = f"<html><body>{corpo_html}</body></html>"
        return self._concluir(msg, enviar, "enviar_novo")

    def finalizar(self, email: EmailRecebido, destino: str, categoria: Optional[str] = None, *,
                  marcar_lido: bool = True) -> None:
        item = self._item(email)
        pasta = self._destino(destino) if self.mover else None
        if marcar_lido:
            try:
                item.UnRead = False
            except Exception:
                pass
        if categoria:
            self._garantir_categoria(categoria)
            atuais = [c.strip() for c in str(_prop(item, "Categories", "") or "").split(",") if c.strip()]
            if categoria not in atuais:
                item.Categories = ", ".join(atuais + [categoria])
        item.Save()
        if pasta is not None:
            item.Move(pasta)
        self._itens.pop(email.chave, None)

    def arquivar(self, email: EmailRecebido, caminho: Path) -> None:
        self._item(email).SaveAs(str(caminho), OL_MSG)

    def localizar(self, id_mensagem: str) -> Optional[EmailRecebido]:
        alvo = (id_mensagem or "").strip().lower()
        pastas = [self.pasta_entrada]
        if self.mover:
            for chave in self._caminhos_destino:
                try:
                    pastas.append(self._destino(chave))
                except ErroCaixa:
                    pass
        for pasta in pastas:
            for item in _iterar(pasta.Items):
                ident = (_prop_mapi(item, PR_INTERNET_MESSAGE_ID) or str(_prop(item, "EntryID", ""))).strip().lower()
                if ident == alvo:
                    em = self._converter(item)
                    self._itens[em.chave] = item
                    return em
        return None

    def _garantir_categoria(self, nome: str) -> None:
        try:
            cats = self.ns.Categories
            if not any(str(c.Name) == nome for c in _iterar(cats)):
                cats.Add(nome)
        except Exception:  # sem permissão para criar: a string é aplicada assim mesmo
            pass

    # ------------------------------------------------------------------ #
    def tipo_conta(self) -> Optional[int]:
        """``OlAccountType`` da conta dona da pasta de entrada (None se não der para saber)."""
        try:
            store_id = str(self.pasta_entrada.Store.StoreID)
            for conta in _iterar(self.ns.Accounts):
                try:
                    if str(conta.DeliveryStore.StoreID) == store_id:
                        return int(conta.AccountType)
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def avisos(self) -> List[str]:
        """Informações que não bloqueiam a execução (comando ``verificar``)."""
        saida = [
            f"pasta de entrada: {self.pasta_entrada.Name} | mover após tratar: {'sim' if self.mover else 'NÃO'}"
            + (f" | filtro de assunto: '{self.filtro_assunto}'" if self.filtro_assunto else "")
            + (f" | recebidos desde: {self.recebidos_desde:%d/%m/%Y}" if self.recebidos_desde else "")
        ]
        if self.tipo_conta() == OL_ACCOUNT_EAS:
            saida.append("conta configurada como Exchange ActiveSync: o Outlook não deixa mover e-mails via COM "
                         "(modo sem mover em uso). Para o piloto, peça à TI a conta como Microsoft Exchange.")
        return saida

    def verificar(self) -> List[str]:
        problemas: List[str] = []
        if self.mover and self.tipo_conta() == OL_ACCOUNT_EAS:
            problemas.append(
                "A conta está no Outlook como Exchange ActiveSync, que não permite mover e-mails via COM. "
                "Use caixa.mover_apos_tratar: false ou configure a conta como Microsoft Exchange."
            )
        if not self.mover:
            return problemas                       # pastas de destino não são usadas
        for chave in self._caminhos_destino:
            try:
                self._destino(chave)
            except ErroCaixa as e:
                problemas.append(str(e))
        return problemas
