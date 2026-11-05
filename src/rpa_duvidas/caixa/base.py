"""Interface única da caixa de e-mail (F02, seção 5 da especificação).

O resto do robô só conhece estes métodos. Trocar Outlook COM por Microsoft
Graph (produção) ou pela caixa simulada (demo/testes) não muda nada fora
deste pacote.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional, Sequence

from ..modelos import EmailRecebido


class ErroCaixa(Exception):
    """Falha de comunicação ou operação na caixa de e-mail."""


class CaixaEmail(ABC):
    """Operações que o robô faz sobre uma caixa de e-mail."""

    @abstractmethod
    def ler_pendentes(self, limite: int) -> List[EmailRecebido]:
        """Devolve até ``limite`` e-mails da pasta de entrada, mais antigos primeiro."""

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
    ) -> str:
        """Responde no mesmo fio. ``enviar=False`` só salva rascunho.

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
    def finalizar(self, email: EmailRecebido, destino: str, categoria: Optional[str] = None) -> None:
        """Marca como lido, aplica categoria e move para a pasta ``destino`` (RF09).

        ``destino`` é a chave de ``caixa.pastas_destino`` (respondidos,
        encaminhados, erro, ignorados).
        """

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
