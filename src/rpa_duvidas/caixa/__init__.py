"""Fábrica da caixa de e-mail: escolhe a implementação pela configuração."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from ..config import Config, ErroConfiguracao
from .base import CaixaEmail, ErroCaixa

__all__ = ["CaixaEmail", "ErroCaixa", "criar_caixa"]


def _data(valor: Any, chave: str) -> Optional[datetime]:
    """Aceita vazio, ``AAAA-MM-DD`` (texto) ou data já interpretada pelo YAML."""
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    try:
        return datetime.strptime(str(valor).strip(), "%Y-%m-%d")
    except ValueError as e:
        raise ErroConfiguracao(f"{chave} deve estar no formato AAAA-MM-DD (recebido: {valor!r})") from e


def criar_caixa(cfg: Config) -> CaixaEmail:
    tipo = cfg.get("caixa.tipo")
    destinos = dict(cfg.exigir("caixa.pastas_destino"))
    criar = bool(cfg.get("caixa.criar_pastas_ausentes", False))
    if tipo == "arquivo":
        from .arquivo import CaixaArquivo

        return CaixaArquivo(
            raiz=cfg.caminho("caixa.arquivo.raiz"),
            pasta_entrada=cfg.exigir("caixa.pasta_entrada"),
            pastas_destino=destinos,
            criar=criar,
        )
    if tipo == "outlook_com":
        from .outlook_com import CaixaOutlookCOM

        return CaixaOutlookCOM(
            conta=cfg.get("caixa.conta", ""),
            pasta_entrada=cfg.exigir("caixa.pasta_entrada"),
            pastas_destino=destinos,
            criar_pastas=criar,
            ler_todos=bool(cfg.get("caixa.ler_todos_da_pasta", True)),
            enviar_em_nome_de=cfg.get("caixa.enviar_em_nome_de", ""),
            mover_apos_tratar=bool(cfg.get("caixa.mover_apos_tratar", True)),
            filtro_assunto=str(cfg.get("caixa.filtro_assunto", "") or ""),
            recebidos_desde=_data(cfg.get("caixa.recebidos_desde", ""), "caixa.recebidos_desde"),
            max_varredura=int(cfg.get("caixa.max_varredura", 500) or 500),
            categorias_rpa=[str(v) for v in (cfg.get("caixa.categorias_outlook", {}) or {}).values() if v],
        )
    if tipo == "graph":
        raise ErroConfiguracao(
            "caixa.tipo=graph ainda não implementado (F18 – depende do aplicativo no Entra ID)"
        )
    raise ErroConfiguracao(f"caixa.tipo desconhecido: {tipo!r}")
