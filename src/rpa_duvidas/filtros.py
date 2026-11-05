"""Filtros de entrada (F05 parcial – RF03; etapa E2 da especificação funcional).

* respostas automáticas são detectadas na extração (extracao.py);
* e-mails já processados são barrados pelo registro (registro.py, RNF01);
* aqui: remetente está ou não na lista de fornecedores;
* v0.2.0: remetente interno (RN2.2) e spam pelo cabeçalho SCL (RN2.3).

A lista oficial ainda não chegou (S06); em dev/demo usam-se listas de teste.
Domínios internos, caixas da automação e o limite de spam vêm da configuração
(``filtros.dominios_internos``, ``caixa.conta``/``caixa.enviar_em_nome_de`` e
``filtros.spam``). Com as listas vazias e o spam desligado (padrão), nada muda
em relação à v0.1.0.
"""
from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Tuple


class ListaFornecedores:
    def __init__(self, dados: Dict):
        self.emails = {str(e).strip().lower() for e in (dados.get("emails") or []) if e}
        self.dominios = {str(d).strip().lower().lstrip("@") for d in (dados.get("dominios") or []) if d}

    @classmethod
    def de_listas(cls, emails: Iterable[str] = (), dominios: Iterable[str] = ()) -> "ListaFornecedores":
        return cls({"emails": list(emails), "dominios": list(dominios)})

    def conhecido(self, remetente: str) -> bool:
        r = (remetente or "").strip().lower()
        if not r:
            return False
        if r in self.emails:
            return True
        dominio = r.rsplit("@", 1)[-1]
        return dominio in self.dominios

    def __len__(self) -> int:
        return len(self.emails) + len(self.dominios)


class FiltroInterno:
    """RN2.2: e-mail escrito pela própria Companhia não é dúvida de fornecedor."""

    def __init__(self, dominios: Iterable[str] = (), caixas: Iterable[str] = ()):
        self.dominios = {str(d).strip().lower().lstrip("@") for d in dominios or [] if d and str(d).strip()}
        self.caixas = {str(c).strip().lower() for c in caixas or [] if c and "@" in str(c)}

    def interno(self, remetente: str) -> Tuple[bool, str]:
        r = (remetente or "").strip().lower()
        if not r:
            return False, ""
        if r in self.caixas:
            return True, "remetente é a própria caixa da automação"
        dominio = r.rsplit("@", 1)[-1] if "@" in r else ""
        if dominio and any(dominio == d or dominio.endswith("." + d) for d in self.dominios):
            return True, f"remetente de domínio interno (@{dominio})"
        return False, ""

    def __len__(self) -> int:
        return len(self.dominios) + len(self.caixas)


class FiltroSpam:
    """RN2.3 (opcional): nível de confiança de spam do Exchange (SCL) no cabeçalho."""

    def __init__(self, ativo: bool = False, cabecalho: str = "x-ms-exchange-organization-scl", limite: int = 5):
        self.ativo = bool(ativo)
        self.cabecalho = (cabecalho or "").strip().lower()
        self.limite = int(limite)

    @classmethod
    def de_config(cls, conf: Optional[Mapping]) -> "FiltroSpam":
        conf = conf or {}
        return cls(
            bool(conf.get("ativo", False)),
            str(conf.get("cabecalho", "x-ms-exchange-organization-scl")),
            int(conf.get("limite_scl", 5)),
        )

    def spam(self, cabecalhos: Mapping[str, str]) -> Tuple[bool, str]:
        if not self.ativo:
            return False, ""
        bruto = {str(k).lower(): str(v) for k, v in (cabecalhos or {}).items()}.get(self.cabecalho, "").strip()
        try:
            scl = int(bruto)
        except ValueError:
            return False, ""
        if scl >= self.limite:
            return True, f"cabeçalho {self.cabecalho} = {scl} (limite {self.limite})"
        return False, ""
