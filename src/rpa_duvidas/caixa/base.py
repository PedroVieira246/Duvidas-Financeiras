"""Interface única da caixa de e-mail (F02, seção 5 da especificação).

O resto do robô só conhece estes métodos. Trocar Outlook COM por Microsoft
Graph (produção) ou pela caixa simulada (demo/testes) não muda nada fora
deste pacote.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from ..modelos import EmailRecebido


class ErroCaixa(Exception):
    """Falha de comunicação ou operação na caixa de e-mail."""


class ErroSeguranca(Exception):
    """Destinatário fora da lista permitida (trava de destinatários)."""


class TravaDestinatarios:
    """Lista fechada de endereços por operação (v0.3.0 – seção 6.2, item 4).

    Com ``destino_respostas = TESTE``: ``responder`` e ``encaminhar`` só podem
    sair para o e-mail destino padrão; ``enviar_novo`` (avisos) para o destino
    padrão ou AVISO_ERRO (decisão da Etapa 1, pergunta 1). A caixa confere os
    destinatários REAIS da mensagem imediatamente antes do ``Send``/``Save``.
    """

    OPERACOES = ("responder", "encaminhar", "enviar_novo")

    def __init__(self, responder: Sequence[str], encaminhar: Sequence[str], enviar_novo: Sequence[str]):
        norm = lambda xs: {str(x).strip().lower() for x in xs if x and str(x).strip()}  # noqa: E731
        self.permitidos = {"responder": norm(responder), "encaminhar": norm(encaminhar), "enviar_novo": norm(enviar_novo)}

    @classmethod
    def destino_padrao(cls, destino: str, avisos_erro: Sequence[str] = ()) -> "TravaDestinatarios":
        return cls([destino], [destino], [destino, *avisos_erro])

    def conferir(self, operacao: str, enderecos: Sequence[str]) -> None:
        permitidos = self.permitidos.get(operacao, set())
        lista = [str(e or "").strip().lower() for e in enderecos]
        if not lista:
            raise ErroSeguranca("destinatário fora do destino padrão (mensagem sem destinatário)")
        fora = [e or "(endereço não identificado)" for e in lista if not e or e not in permitidos]
        if fora:
            raise ErroSeguranca(f"destinatário fora do destino padrão ({operacao}: {', '.join(fora)})")


class CaixaEmail(ABC):
    """Operações que o robô faz sobre uma caixa de e-mail."""

    #: v0.3.0 – quantos itens o último ``ler_pendentes`` deixou de lado por ``aceitar_remetente``
    descartados: int = 0

    @abstractmethod
    def ler_pendentes(self, limite: int, aceitar_remetente: Optional[Callable[[str], bool]] = None) -> List[EmailRecebido]:
        """Devolve até ``limite`` e-mails da pasta de entrada, mais antigos primeiro.

        v0.3.0: ``aceitar_remetente(smtp)`` é aplicado durante a varredura, ANTES
        do corte do lote. Os itens recusados não são convertidos nem alterados
        (caixa pessoal – seção 6.1) e só contam em ``descartados``.
        """

    @abstractmethod
    def responder(
        self,
        email: EmailRecebido,
        corpo_html: str,
        *,
        anexos: Sequence[Path] = (),
        cc: Sequence[str] = (),
        responder_todos: bool = False,
        enviar: bool = False,
        redirecionar_para: Optional[str] = None,
        prefixo_assunto: str = "",
    ) -> str:
        """Responde no mesmo fio. ``enviar=False`` só salva rascunho.

        v0.3.0: ``redirecionar_para`` (envio de teste – seção 6.2) remove TODOS os
        destinatários montados pelo ``Reply()`` e deixa só esse endereço, sem CC;
        a trava confere de novo antes de salvar/enviar. ``prefixo_assunto`` vem
        da aba Textos.

        Devolve um identificador da mensagem gerada.
        """

    @abstractmethod
    def encaminhar(
        self,
        email: EmailRecebido,
        para: Sequence[str],
        prefixo_assunto: str,
        nota_html: str,
        *,
        enviar: bool = False,
    ) -> str:
        """Encaminha o e-mail original (com anexos) para análise manual."""

    @abstractmethod
    def enviar_novo(self, para: Sequence[str], assunto: str, corpo_html: str, *, enviar: bool = False) -> str:
        """Mensagem nova (ex.: aviso de erro aos analistas)."""

    @abstractmethod
    def finalizar(self, email: EmailRecebido, destino: str, categoria: Optional[str] = None, *,
                  marcar_lido: bool = True) -> None:
        """Marca como lido, aplica categoria e move para a pasta ``destino`` (RF09).

        v0.3.0: ``marcar_lido=False`` só aplica a categoria (e-mail que o analista
        já tratou – seção 6.1).

        ``destino`` é a chave de ``caixa.pastas_destino`` (respondidos,
        encaminhados, erro, ignorados).
        """

    def arquivar(self, email: EmailRecebido, caminho: Path) -> None:
        """v0.3.0 – salva o e-mail ORIGINAL em ``caminho`` (.msg, com anexos – seção 6.4)."""
        raise ErroCaixa("arquivamento em .msg não suportado por esta caixa")

    def localizar(self, id_mensagem: str) -> Optional[EmailRecebido]:
        """v0.3.0 – reencontra um e-mail já tratado (comando ``arquivar-pendentes``)."""
        return None

    def destinatarios_resposta(self, email: EmailRecebido, responder_todos: bool) -> List[str]:
        """Endereços que receberão a resposta (usado pela trava de segurança)."""
        return [email.remetente]

    def verificar(self) -> List[str]:
        """Checagens de saúde para o comando ``verificar``. Lista de problemas."""
        return []

    def avisos(self) -> List[str]:
        """Informações para o comando ``verificar`` que não bloqueiam a execução."""
        return []

    def fechar(self) -> None:  # pragma: no cover - opcional
        pass
