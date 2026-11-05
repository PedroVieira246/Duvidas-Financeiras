"""Fábrica do classificador: escolhe a abordagem pela configuração."""
from __future__ import annotations

from ..config import Config, ErroConfiguracao
from .base import Classificador

__all__ = ["Classificador", "criar_classificador"]


def criar_classificador(cfg: Config) -> Classificador:
    tipo = cfg.get("classificacao.tipo", "palavras_chave")
    if tipo == "palavras_chave":
        from .palavras_chave import ClassificadorPalavrasChave

        return ClassificadorPalavrasChave(cfg.yaml_referenciado("classificacao.arquivo_termos"))
    if tipo == "ia":
        # F08 – provedor escolhido em classificacao.ia.provedor.tipo (simulado | http_generico)
        from .ia import criar_classificador_ia

        return criar_classificador_ia(cfg)
    if tipo == "menu":
        raise ErroConfiguracao("classificacao.tipo=menu ainda não implementado (F09 – depende do texto aprovado)")
    raise ErroConfiguracao(f"classificacao.tipo desconhecido: {tipo!r}")
