"""Decisão do RPA sobre a classificação da IA (E5 – regras D1 a D7, seção 6.1).

Princípio de controle: a IA **sugere** e o RPA **decide**. A ação final é
sempre recalculada aqui, com regras fixas aplicadas NESTA ordem:

====  ==========================================================  ==========================
D1    falha da IA ou resposta inválida após as novas tentativas   IA_INDISPONIVEL / RESPOSTA_IA_INVALIDA
(E5)  código sem mapeamento em ``categorias_ia.yaml``             CATEGORIA_SEM_TUTORIAL
D2    categoria sem tutorial (C07, C99)                           SEM_RESPOSTA_PADRAO / NAO_IDENTIFICADO
D3    confiança < limite                                          BAIXA_CONFIANCA
D4    há categorias secundárias                                   MULTIPLAS_DUVIDAS
D5    há sinais de exceção                                        EXCECAO
D6    categoria com ``resposta_automatica: false``                CATEGORIA_DESABILITADA
D7    IA sugere ENCAMINHAR_MANUAL ou tutorial ≠ o da categoria    EXCECAO
—     nenhuma das anteriores                                      RESPONDER_TUTORIAL
====  ==========================================================  ==========================

Funções puras: nada aqui chama a IA, lê arquivo ou grava registro.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from ..modelos import Acao, Categoria, MotivoManual
from .validacao_ia import ENCAMINHAR_MANUAL, RespostaIAValidada

REGRA_RESPONDER = "RESPONDER"
REGRA_SEM_MAPEAMENTO = "E5"


# --------------------------------------------------------------------------- #
# config/categorias_ia.yaml
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CategoriaIA:
    codigo: str
    descricao: str
    tutorial: Optional[str]
    resposta_automatica: bool
    motivo_manual: Optional[str] = None


@dataclass(frozen=True)
class CategoriasIA:
    """Conteúdo validado de ``config/categorias_ia.yaml``."""

    codigos_validos: Tuple[str, ...]
    sinais_excecao: Tuple[str, ...]
    categorias: Dict[str, CategoriaIA]

    @classmethod
    def de_dict(cls, dados: Dict[str, Any]) -> "CategoriasIA":
        """Monta e valida. Erros de estrutura viram ``ValueError`` com todas as falhas."""
        problemas: List[str] = []
        codigos = tuple(str(c).strip() for c in (dados.get("codigos_validos") or []))
        sinais = tuple(str(s).strip() for s in (dados.get("sinais_excecao") or []))
        if not codigos:
            problemas.append("codigos_validos vazio")
        if not sinais:
            problemas.append("sinais_excecao vazio")
        categorias: Dict[str, CategoriaIA] = {}
        for codigo, conf in (dados.get("categorias") or {}).items():
            codigo = str(codigo).strip()
            conf = conf or {}
            if codigo not in codigos:
                problemas.append(f"categoria {codigo} não está em codigos_validos")
            tutorial = conf.get("tutorial")
            tutorial = str(tutorial).strip() if tutorial not in (None, "", "null") else None
            if tutorial is not None and tutorial not in Categoria.TUTORIAIS:
                problemas.append(f"{codigo}: tutorial '{tutorial}' não é uma categoria de tutorial do robô {Categoria.TUTORIAIS}")
            motivo = conf.get("motivo_manual")
            if motivo is not None and motivo not in MotivoManual.TODOS:
                problemas.append(f"{codigo}: motivo_manual '{motivo}' desconhecido")
            if "resposta_automatica" not in conf or not isinstance(conf.get("resposta_automatica"), bool):
                problemas.append(f"{codigo}: resposta_automatica deve ser true ou false")
            if tutorial is None and conf.get("resposta_automatica") is True:
                problemas.append(f"{codigo}: resposta_automatica true sem tutorial")
            categorias[codigo] = CategoriaIA(
                codigo=codigo,
                descricao=str(conf.get("descricao", "")),
                tutorial=tutorial,
                resposta_automatica=conf.get("resposta_automatica") is True,
                motivo_manual=motivo,
            )
        if not categorias:
            problemas.append("nenhuma categoria em 'categorias'")
        if problemas:
            raise ValueError("categorias_ia.yaml inválido: " + "; ".join(problemas))
        return cls(codigos, sinais, categorias)

    def tutoriais_validos(self) -> Set[str]:
        """Códigos de tutorial aceitos na regra V5."""
        return {c.tutorial for c in self.categorias.values() if c.tutorial}

    def sem_mapeamento(self) -> List[str]:
        """Códigos válidos que não têm entrada em ``categorias`` (alerta do ``verificar``)."""
        return [c for c in self.codigos_validos if c not in self.categorias]

    def descricao(self, codigo: Optional[str]) -> str:
        cat = self.categorias.get(codigo or "")
        return cat.descricao if cat else ""


# --------------------------------------------------------------------------- #
# Decisão
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Decisao:
    acao: str                       # Acao.RESPONDER_TUTORIAL ou Acao.ENCAMINHAR_MANUAL
    categoria: str                  # TUT_* ou MANUAL (categoria do robô)
    motivo_manual: Optional[str]
    regra: str                      # D1..D7, E5 ou RESPONDER
    explicacao: str

    @property
    def responder(self) -> bool:
        return self.acao == Acao.RESPONDER_TUTORIAL


def _manual(motivo: str, regra: str, explicacao: str) -> Decisao:
    return Decisao(Acao.ENCAMINHAR_MANUAL, Categoria.MANUAL, motivo, regra, explicacao)


def decidir(
    resposta: Optional[RespostaIAValidada],
    categorias: CategoriasIA,
    limite_confianca: float,
    falha: Optional[str] = None,
) -> Decisao:
    """Aplica D1–D7 na ordem e devolve a ação final do RPA."""
    # D1
    if falha or resposta is None:
        motivo = falha if falha in (MotivoManual.IA_INDISPONIVEL, MotivoManual.RESPOSTA_IA_INVALIDA) \
            else MotivoManual.RESPOSTA_IA_INVALIDA
        return _manual(motivo, "D1", "IA indisponível" if motivo == MotivoManual.IA_INDISPONIVEL
                       else "resposta da IA inválida após a correção")

    cat = categorias.categorias.get(resposta.categoria)
    if cat is None:
        return _manual(MotivoManual.CATEGORIA_SEM_TUTORIAL, REGRA_SEM_MAPEAMENTO,
                       f"{resposta.categoria} sem mapeamento em categorias_ia.yaml")
    # D2
    if cat.tutorial is None:
        return _manual(cat.motivo_manual or MotivoManual.NAO_IDENTIFICADO, "D2",
                       f"{cat.codigo} não tem resposta padrão")
    # D3
    if resposta.confianca < limite_confianca:
        return _manual(MotivoManual.BAIXA_CONFIANCA, "D3",
                       f"confiança {resposta.confianca:.2f} < limite {limite_confianca:.2f}")
    # D4
    if resposta.categorias_secundarias:
        return _manual(MotivoManual.MULTIPLAS_DUVIDAS, "D4",
                       "dúvidas secundárias: " + ", ".join(resposta.categorias_secundarias))
    # D5
    if resposta.sinais_excecao:
        return _manual(MotivoManual.EXCECAO, "D5", "sinais de exceção: " + ", ".join(resposta.sinais_excecao))
    # D6
    if not cat.resposta_automatica:
        return _manual(MotivoManual.CATEGORIA_DESABILITADA, "D6",
                       f"resposta automática desligada para {cat.codigo}")
    # D7
    if resposta.acao == ENCAMINHAR_MANUAL:
        return _manual(MotivoManual.EXCECAO, "D7", "a IA sugeriu encaminhar para análise manual")
    if resposta.tutorial != cat.tutorial:
        return _manual(MotivoManual.EXCECAO, "D7",
                       f"tutorial sugerido ({resposta.tutorial}) diferente do tutorial de {cat.codigo} ({cat.tutorial})")
    return Decisao(Acao.RESPONDER_TUTORIAL, cat.tutorial, None, REGRA_RESPONDER,
                   f"{cat.codigo} habilitada, sem exceções → {cat.tutorial}")
