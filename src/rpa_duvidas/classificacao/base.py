"""Interface única do classificador (F02, seção 4 da especificação).

O resto do robô recebe só "categoria + confiança + motivo". Palavras-chave
(F06), IA (F08) e dúvida padronizada (F09) são implementações intercambiáveis.

Desde a v0.2.0 (lacuna R1) o ciclo também passa o ``EmailRecebido`` inteiro
(anexos, histórico, remetente). O parâmetro é opcional: quem não precisa dele
(ex.: palavras-chave) simplesmente o ignora.
"""
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from ..modelos import Classificacao, EmailRecebido


@runtime_checkable
class Classificador(Protocol):
    def classificar(self, assunto: str, corpo: str, email: Optional[EmailRecebido] = None) -> Classificacao:
        ...
