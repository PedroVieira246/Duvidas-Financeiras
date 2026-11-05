"""Credenciais fora do código (RNF04).

O MVP com Outlook COM NÃO precisa de credencial: usa o login que o Outlook
já resolveu. Este módulo fica pronto para o que vem depois (Microsoft Graph,
provedor de IA), lendo do Gerenciador de Credenciais do Windows via
``keyring`` ou de variável de ambiente.

Cadastrar uma credencial (uma vez, na máquina):
    python -m keyring set rpa_duvidas graph_client_secret
"""
from __future__ import annotations

import os
from typing import Optional

SERVICO = "rpa_duvidas"


def obter(nome: str, *, obrigatorio: bool = True) -> Optional[str]:
    """Busca ``nome`` em: variável RPA_<NOME> → Gerenciador de Credenciais."""
    valor = os.environ.get(f"RPA_{nome.upper()}")
    if not valor:
        try:
            import keyring  # import tardio: só exigido quando usado

            valor = keyring.get_password(SERVICO, nome)
        except Exception:  # pragma: no cover - depende da máquina
            valor = None
    if obrigatorio and not valor:
        raise KeyError(
            f"Credencial '{nome}' não encontrada. Cadastre com: "
            f"python -m keyring set {SERVICO} {nome}"
        )
    return valor
