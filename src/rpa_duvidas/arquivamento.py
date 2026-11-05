"""Arquivamento dos e-mails tratados em .msg (v0.3.0 – D05, seção 6.4).

Caminho: ``<raiz>\\<Escritório>\\<AAAA-MM>\\<AAAA-MM-DD_HHMM>_<protocolo>_<assunto>.msg``

* assunto sem ``\\ / : * ? " < > |`` e com no máximo 60 caracteres;
* caminho completo com no máximo 240 caracteres (o assunto é cortado);
* pastas que faltam são criadas.

Uma falha aqui NÃO desfaz a resposta nem manda o e-mail para Erro: o registro
recebe ``FALHA: <motivo>`` e o comando ``arquivar-pendentes`` tenta de novo.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from .filtros import SEM_ESCRITORIO
from .modelos import EmailRecebido
from .respostas import protocolo

log = logging.getLogger(__name__)

LIMITE_ASSUNTO = 60
LIMITE_CAMINHO = 240
PREFIXO_FALHA = "FALHA: "
_RE_INVALIDOS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RE_ESPACOS = re.compile(r"\s+")


class ErroArquivamento(Exception):
    pass


def limpar(texto: str, limite: Optional[int] = None) -> str:
    t = _RE_ESPACOS.sub(" ", _RE_INVALIDOS.sub("", str(texto or ""))).strip()
    if limite is not None:
        t = t[:limite]
    return t.rstrip(". ")                       # o Windows não aceita nome terminado em ponto ou espaço


def caminho_msg(raiz: Path, escritorio: str, recebido: Optional[datetime], prot: str, assunto: str) -> Path:
    recebido = recebido or datetime.now()
    pasta = Path(raiz) / (limpar(escritorio) or SEM_ESCRITORIO) / f"{recebido:%Y-%m}"
    base = f"{recebido:%Y-%m-%d_%H%M}_{prot}"
    assunto_limpo = limpar(assunto, LIMITE_ASSUNTO)

    def montar(a: str) -> Path:
        return pasta / (f"{base}_{a}.msg" if a else f"{base}.msg")

    caminho = montar(assunto_limpo)
    excesso = len(str(caminho)) - LIMITE_CAMINHO
    if excesso > 0:
        assunto_limpo = limpar(assunto_limpo[: max(0, len(assunto_limpo) - excesso)])
        caminho = montar(assunto_limpo)
    if len(str(caminho)) > LIMITE_CAMINHO:
        raise ErroArquivamento(f"caminho com mais de {LIMITE_CAMINHO} caracteres mesmo sem o assunto: {caminho}")
    return caminho


class Arquivador:
    def __init__(self, raiz: Path, somente_na_nuvem: Optional[Callable[[Path], bool]] = None):
        self.raiz = Path(raiz)
        if somente_na_nuvem is None:
            from .tutoriais import _somente_na_nuvem as somente_na_nuvem
        self.somente_na_nuvem = somente_na_nuvem

    def arquivar(self, caixa, email: EmailRecebido) -> str:
        """Salva o e-mail ORIGINAL (com anexos). Devolve o caminho ou ``FALHA: <motivo>`` – nunca levanta."""
        try:
            if self.raiz.exists() and self.somente_na_nuvem(self.raiz):
                raise ErroArquivamento(f"pasta de arquivamento só na nuvem (OneDrive): {self.raiz}")
            caminho = caminho_msg(self.raiz, email.escritorio, email.data_recebimento, protocolo(email), email.assunto)
            caminho.parent.mkdir(parents=True, exist_ok=True)
            caixa.arquivar(email, caminho)
            return str(caminho)
        except Exception as erro:
            motivo = f"{PREFIXO_FALHA}{type(erro).__name__}: {erro}"
            log.warning("[%s] arquivamento .msg falhou – %s", protocolo(email), motivo)
            return motivo
