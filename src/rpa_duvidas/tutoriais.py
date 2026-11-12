"""Localização e validação do tutorial de cada categoria (F10 – RF06, seção 6).

Regras da especificação:
  1. caminho = raiz / pasta, arquivos que seguem ``padrao`` (glob);
  2. mais de um → o de modificação mais recente;
  3. existe, tamanho > 0 e cabe no limite de anexo;
  4. qualquer falha → ``TutorialIndisponivel`` (o ciclo manda o e-mail para Erro).

v0.3.0 (D07 – seção 5.6): com ``caminho_arquivo`` preenchido (aba Tutoriais da
planilha), vale o caminho COMPLETO do arquivo oficial; ``raiz``/``pasta``/``padrao``
continua como alternativa para os perfis dev e demo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from . import nuvem
from .nuvem import ATRIBUTOS_NUVEM as _ATRIBUTOS_NUVEM  # noqa: F401 (compatibilidade)


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
    return nuvem.somente_na_nuvem(caminho)


def _garantir_local(arquivo: Path) -> None:
    """v0.3.2: arquivo só na nuvem é baixado antes de usar; se não der → ``TutorialIndisponivel``."""
    try:
        nuvem.garantir_local(arquivo, somente_na_nuvem=_somente_na_nuvem)
    except nuvem.ErroNuvem as e:
        raise TutorialIndisponivel(str(e)) from e


class RepositorioTutoriais:
    def __init__(self, dados: Dict, resolver: Callable[[str], Path]):
        """``dados`` = conteúdo de tutoriais.yaml; ``resolver`` expande/resolve caminhos."""
        self.resolver = resolver
        self.raiz = resolver(str(dados.get("raiz", "")))
        self.limite_mb = float(dados.get("limite_anexo_mb", 20))
        self.exigir_local = bool(dados.get("exigir_arquivo_local", True))
        self.categorias: Dict[str, Dict] = dict(dados.get("categorias") or {})

    def localizar(self, categoria: str) -> Tutorial:
        conf = self.categorias.get(categoria)
        if not conf:
            raise TutorialIndisponivel(f"Categoria {categoria} sem tutorial configurado em tutoriais.yaml")
        if "caminho_arquivo" in conf:
            return self._por_caminho(categoria, conf)
        pasta = self.raiz / str(conf.get("pasta", ""))
        if not pasta.is_dir():
            raise TutorialIndisponivel(f"Pasta do tutorial não encontrada: {pasta}")
        padrao = str(conf.get("padrao", "*"))
        candidatos = [p for p in pasta.glob(padrao) if p.is_file() and not p.name.startswith("~$")]
        if not candidatos:
            raise TutorialIndisponivel(f"Nenhum arquivo '{padrao}' em {pasta}")
        escolhido = max(candidatos, key=lambda p: p.stat().st_mtime)
        if self.exigir_local:
            _garantir_local(escolhido)
        tamanho = escolhido.stat().st_size
        if tamanho <= 0:
            raise TutorialIndisponivel(f"Arquivo vazio: {escolhido}")
        tamanho_mb = tamanho / (1024 * 1024)
        if tamanho_mb > self.limite_mb:
            raise TutorialIndisponivel(
                f"Arquivo com {tamanho_mb:.1f} MB excede o limite de {self.limite_mb:.0f} MB: {escolhido}"
            )
        return Tutorial(categoria, escolhido, round(tamanho_mb, 2), str(conf.get("descricao", "")))

    def _por_caminho(self, categoria: str, conf: Dict) -> Tutorial:
        bruto = str(conf.get("caminho_arquivo") or "").strip()
        if not bruto:
            raise TutorialIndisponivel(f"Categoria {categoria} sem caminho do arquivo do tutorial (aba Tutoriais)")
        arquivo = self.resolver(bruto)
        if not arquivo.is_file():
            raise TutorialIndisponivel(f"Arquivo do tutorial não encontrado: {arquivo}")
        if self.exigir_local:
            _garantir_local(arquivo)
        tamanho = arquivo.stat().st_size
        if tamanho <= 0:
            raise TutorialIndisponivel(f"Arquivo vazio: {arquivo}")
        limite = float(conf.get("limite_mb") or self.limite_mb)
        tamanho_mb = tamanho / (1024 * 1024)
        if tamanho_mb > limite:
            raise TutorialIndisponivel(f"Arquivo com {tamanho_mb:.1f} MB excede o limite de {limite:g} MB: {arquivo}")
        return Tutorial(categoria, arquivo, round(tamanho_mb, 2), str(conf.get("descricao", "")))

    def preparar(self) -> Tuple[int, int, List[str]]:
        """v0.3.2 – antes do ciclo: baixa da nuvem os tutoriais configurados.

        Devolve ``(disponíveis, baixados agora, problemas)``. Não levanta: um tutorial
        indisponível só afeta os e-mails daquela categoria (que vão para Erro).
        """
        ok, baixados, problemas = 0, 0, []
        for cat, conf in self.categorias.items():
            bruto = str((conf or {}).get("caminho_arquivo") or "").strip()
            if not bruto:
                continue
            arquivo = self.resolver(bruto)
            try:
                if not arquivo.is_file():
                    raise TutorialIndisponivel(f"Arquivo do tutorial não encontrado: {arquivo}")
                if self.exigir_local and nuvem.garantir_local(arquivo, somente_na_nuvem=_somente_na_nuvem):
                    baixados += 1
                ok += 1
            except (TutorialIndisponivel, nuvem.ErroNuvem, OSError) as e:
                problemas.append(f"{cat}: {e}")
        return ok, baixados, problemas

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
