"""Classificador BASE por palavras-chave (F06 – RF04, seção 4).

Simples, previsível e sem custo: permite rodar o fluxo de ponta a ponta já,
enquanto a massa real e o provedor de IA não chegam. Termos e pesos ficam em
``config/palavras_chave.yaml``.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..extracao import limpar_assunto, normalizar
from ..modelos import Categoria, Classificacao, EmailRecebido, MotivoManual

# Categorias especiais do arquivo de termos → motivo de encaminhamento
ESPECIAIS = {
    "MANUAL_SAP": MotivoManual.SAP,
    "MANUAL_FORA_ESCOPO": MotivoManual.FORA_DO_ESCOPO,
}


def _padrao(termo: str) -> re.Pattern:
    partes = [re.escape(p) for p in normalizar(termo).split()]
    return re.compile(r"(?<![a-z0-9])" + r"\s+".join(partes) + r"(?![a-z0-9])")


class ClassificadorPalavrasChave:
    def __init__(self, dados: Dict):
        self.peso_assunto = float(dados.get("peso_assunto", 2.0))
        self.saturacao = float(dados.get("saturacao", 5.0))
        self.termos: Dict[str, List[Tuple[str, re.Pattern, float]]] = {}
        for cat, conf in (dados.get("categorias") or {}).items():
            if cat not in Categoria.RESPONDIVEIS and cat not in ESPECIAIS:
                raise ValueError(f"Categoria desconhecida em palavras_chave.yaml: {cat}")
            self.termos[cat] = [
                (str(t), _padrao(str(t)), float(p)) for t, p in ((conf or {}).get("termos") or {}).items()
            ]

    def pontuar(self, assunto: str, corpo: str) -> Dict[str, Tuple[float, List[str]]]:
        a = normalizar(limpar_assunto(assunto))
        c = normalizar(corpo)
        pontos: Dict[str, Tuple[float, List[str]]] = {}
        for cat, termos in self.termos.items():
            total, achados = 0.0, []
            for texto, rx, peso in termos:
                no_assunto, no_corpo = bool(rx.search(a)), bool(rx.search(c))
                if no_assunto or no_corpo:
                    valor = peso * (self.peso_assunto if no_assunto else 1.0)
                    total += valor
                    achados.append(f"{texto}(+{valor:g})")
            if total > 0:
                pontos[cat] = (total, achados)
        return pontos

    def classificar(self, assunto: str, corpo: str, email: Optional[EmailRecebido] = None) -> Classificacao:
        """``email`` é aceito pela interface (lacuna R1), mas não é usado aqui."""
        pontos = self.pontuar(assunto, corpo)
        ranking = sorted(pontos.items(), key=lambda kv: kv[1][0], reverse=True)
        resumo = {cat: round(v[0], 2) for cat, v in ranking}
        if not ranking:
            return Classificacao(
                Categoria.MANUAL, 0.0, "nenhum termo conhecido encontrado",
                motivo_manual=MotivoManual.NAO_IDENTIFICADO, detalhes={"pontuacoes": {}},
            )

        (cat1, (s1, achados1)), s2 = ranking[0], (ranking[1][1][0] if len(ranking) > 1 else 0.0)
        dominancia = s1 / (s1 + s2)
        forca = min(1.0, s1 / self.saturacao)
        confianca = round(dominancia * forca, 2)
        motivo = f"{cat1}: " + ", ".join(achados1)
        if len(ranking) > 1:
            motivo += f" | 2ª: {ranking[1][0]} ({s2:g})"
        detalhes = {"pontuacoes": resumo, "categoria_sugerida": cat1}

        if cat1 in ESPECIAIS:
            return Classificacao(Categoria.MANUAL, confianca, motivo, motivo_manual=ESPECIAIS[cat1], detalhes=detalhes)
        return Classificacao(cat1, confianca, motivo, detalhes=detalhes)
