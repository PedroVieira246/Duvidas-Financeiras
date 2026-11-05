"""Localização e validação do tutorial de cada categoria (F10 – RF06, seção 6).

Regras da especificação:
  1. caminho = raiz / pasta, arquivos que seguem ``padrao`` (glob);
  2. mais de um → o de modificação mais recente;
  3. existe, tamanho > 0 e cabe no limite de anexo;
  4. qualquer falha → ``TutorialIndisponivel`` (o ciclo manda o e-mail para Erro).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

# Atributos de arquivo do Windows usados pelo OneDrive para "somente on-line"
_ATRIBUTOS_NUVEM = 0x00400000 | 0x00040000 | 0x00001000  # RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN | OFFLINE


class TutorialIndisponivel(Exception):
    """O tutorial da categoria não pode ser anexado."""


@dataclass
class Tutorial:
    categoria: str
    caminho: Path
    tamanho_mb: float
    descricao: str = ""

    @property
    def nome(self) -> str:
        return self.caminho.name


def _somente_na_nuvem(caminho: Path) -> bool:
    atributos = getattr(os.stat(caminho), "st_file_attributes", 0)  # só existe no Windows
    return bool(atributos & _ATRIBUTOS_NUVEM)


class RepositorioTutoriais:
    def __init__(self, dados: Dict, resolver: Callable[[str], Path]):
        """``dados`` = conteúdo de tutoriais.yaml; ``resolver`` expande/resolve caminhos."""
        self.raiz = resolver(str(dados.get("raiz", "")))
        self.limite_mb = float(dados.get("limite_anexo_mb", 20))
        self.exigir_local = bool(dados.get("exigir_arquivo_local", True))
        self.categorias: Dict[str, Dict] = dict(dados.get("categorias") or {})

    def localizar(self, categoria: str) -> Tutorial:
        conf = self.categorias.get(categoria)
        if not conf:
            raise TutorialIndisponivel(f"Categoria {categoria} sem tutorial configurado em tutoriais.yaml")
        pasta = self.raiz / str(conf.get("pasta", ""))
        if not pasta.is_dir():
            raise TutorialIndisponivel(f"Pasta do tutorial não encontrada: {pasta}")
        padrao = str(conf.get("padrao", "*"))
        candidatos = [p for p in pasta.glob(padrao) if p.is_file() and not p.name.startswith("~$")]
        if not candidatos:
            raise TutorialIndisponivel(f"Nenhum arquivo '{padrao}' em {pasta}")
        escolhido = max(candidatos, key=lambda p: p.stat().st_mtime)
        if self.exigir_local and _somente_na_nuvem(escolhido):
            raise TutorialIndisponivel(
                f"Arquivo existe só na nuvem (OneDrive): {escolhido}. Marque a pasta como "
                "'Sempre manter neste dispositivo'."
            )
        tamanho = escolhido.stat().st_size
        if tamanho <= 0:
            raise TutorialIndisponivel(f"Arquivo vazio: {escolhido}")
        tamanho_mb = tamanho / (1024 * 1024)
        if tamanho_mb > self.limite_mb:
            raise TutorialIndisponivel(
                f"Arquivo com {tamanho_mb:.1f} MB excede o limite de {self.limite_mb:.0f} MB: {escolhido}"
            )
        return Tutorial(categoria, escolhido, round(tamanho_mb, 2), str(conf.get("descricao", "")))

    def verificar_todos(self) -> List[Tuple[str, bool, str]]:
        """Para o comando ``verificar``: (categoria, ok, detalhe)."""
        saida = []
        for cat in self.categorias:
            try:
                t = self.localizar(cat)
                saida.append((cat, True, f"{t.nome} ({t.tamanho_mb} MB)"))
            except TutorialIndisponivel as e:
                saida.append((cat, False, str(e)))
        return saida
