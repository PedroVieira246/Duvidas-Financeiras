"""Carga e validação da configuração (F01).

``config/settings.yaml`` (base) + ``config/perfis/<perfil>.yaml`` (o que muda).
O perfil vem do argumento ``--perfil`` ou da variável ``RPA_PERFIL``.
"""
from __future__ import annotations

import copy
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml

RAIZ_PROJETO = Path(__file__).resolve().parents[2]
MARCADOR_PENDENTE = "<PREENCHER"
TIPOS_CAIXA = ("outlook_com", "arquivo", "graph")
TIPOS_CLASSIFICADOR = ("palavras_chave", "ia", "menu")
TIPOS_PROVEDOR_IA = ("simulado", "http_generico")


class ErroConfiguracao(Exception):
    """Configuração inválida ou incompleta."""


# --------------------------------------------------------------------------- #
# utilitários
# --------------------------------------------------------------------------- #
def mesclar(base: Dict[str, Any], sobrescrita: Dict[str, Any]) -> Dict[str, Any]:
    """Mescla recursiva: dicionários são combinados, o resto é substituído."""
    resultado = copy.deepcopy(base)
    for chave, valor in (sobrescrita or {}).items():
        if isinstance(valor, dict) and isinstance(resultado.get(chave), dict):
            resultado[chave] = mesclar(resultado[chave], valor)
        else:
            resultado[chave] = copy.deepcopy(valor)
    return resultado


_RE_PERCENT = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")


def expandir(texto: str) -> str:
    """Expande ${VAR}, $VAR, %VAR% (estilo Windows) e ~."""
    texto = _RE_PERCENT.sub(lambda m: os.environ.get(m.group(1), m.group(0)), texto)
    texto = os.path.expandvars(texto)
    if texto.startswith("~"):
        texto = os.path.expanduser(texto)
    return texto


def ler_yaml(caminho: Path) -> Dict[str, Any]:
    if not caminho.exists():
        raise ErroConfiguracao(f"Arquivo de configuração não encontrado: {caminho}")
    with caminho.open(encoding="utf-8") as f:
        dados = yaml.safe_load(f) or {}
    if not isinstance(dados, dict):
        raise ErroConfiguracao(f"Formato inválido (esperado um mapa YAML): {caminho}")
    return dados


def _valores_pendentes(dados: Any, prefixo: str = "") -> Iterable[str]:
    if isinstance(dados, dict):
        for k, v in dados.items():
            yield from _valores_pendentes(v, f"{prefixo}.{k}" if prefixo else str(k))
    elif isinstance(dados, list):
        for i, v in enumerate(dados):
            yield from _valores_pendentes(v, f"{prefixo}[{i}]")
    elif isinstance(dados, str) and MARCADOR_PENDENTE in dados:
        yield f"{prefixo} = {dados}"


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
class Config:
    """Acesso à configuração mesclada.

    ``cfg.get("caixa.pastas_destino.erro")`` lê com notação de pontos.
    """

    def __init__(self, dados: Dict[str, Any], perfil: str, raiz: Path = RAIZ_PROJETO):
        self.dados = dados
        self.perfil = perfil
        self.raiz = raiz
        self._cache_yaml: Dict[str, Dict[str, Any]] = {}

    # ---- leitura genérica ------------------------------------------------ #
    def get(self, caminho: str, padrao: Any = None) -> Any:
        atual: Any = self.dados
        for parte in caminho.split("."):
            if not isinstance(atual, dict) or parte not in atual:
                return padrao
            atual = atual[parte]
        return atual

    def exigir(self, caminho: str) -> Any:
        valor = self.get(caminho)
        if valor is None or valor == "":
            raise ErroConfiguracao(f"Parâmetro obrigatório ausente: {caminho}")
        return valor

    def caminho(self, chave_ou_valor: str, *, eh_valor: bool = False) -> Path:
        """Resolve um caminho da configuração (relativo à raiz do projeto)."""
        bruto = chave_ou_valor if eh_valor else self.exigir(chave_ou_valor)
        p = Path(expandir(str(bruto)))
        return p if p.is_absolute() else (self.raiz / p)

    def yaml_referenciado(self, chave: str) -> Dict[str, Any]:
        """Carrega (com cache) um YAML cujo caminho está em ``chave``."""
        p = self.caminho(chave)
        k = str(p)
        if k not in self._cache_yaml:
            self._cache_yaml[k] = ler_yaml(p)
        return self._cache_yaml[k]

    # ---- atalhos de negócio --------------------------------------------- #
    @property
    def ambiente(self) -> str:
        return str(self.get("ambiente", self.perfil))

    @property
    def envio_real(self) -> bool:
        return bool(self.get("execucao.envio_real", False))

    @property
    def classificador(self) -> str:
        return str(self.get("classificacao.tipo", "palavras_chave"))

    @property
    def limite_confianca(self) -> float:
        """Limite de confiança da abordagem ativa.

        Com ``classificacao.tipo: ia`` vale ``classificacao.ia.limite_confianca``
        (0,80 – seção 6.2 da especificação funcional), se definido. Assim, trocar
        o tipo de volta para ``palavras_chave`` restaura o limite antigo sem mexer
        em mais nada (RNF-IA08).
        """
        if self.classificador == "ia" and self.get("classificacao.ia.limite_confianca") is not None:
            return float(self.get("classificacao.ia.limite_confianca"))
        return float(self.get("classificacao.limite_confianca", 0.6))

    def destino_manual(self, motivo: Optional[str]) -> List[str]:
        por_motivo = self.get("destinatarios.analise_manual.por_motivo", {}) or {}
        if motivo and por_motivo.get(motivo):
            return list(por_motivo[motivo])
        return list(self.get("destinatarios.analise_manual.padrao", []) or [])

    # ---- validação ------------------------------------------------------- #
    def pendencias(self) -> List[str]:
        """Valores ainda marcados com <PREENCHER...> (perfil + YAMLs ligados)."""
        itens = list(_valores_pendentes(self.dados))
        for chave in ("tutoriais.arquivo", "filtros.arquivo_fornecedores"):
            try:
                itens += [f"{self.get(chave)} → {x}" for x in _valores_pendentes(self.yaml_referenciado(chave))]
            except ErroConfiguracao:
                pass
        return itens

    def validar(self) -> List[str]:
        """Devolve a lista de erros que impedem a execução (vazia = ok)."""
        erros: List[str] = []
        tipo = self.get("caixa.tipo")
        if tipo not in TIPOS_CAIXA:
            erros.append(f"caixa.tipo inválido: {tipo!r} (use {', '.join(TIPOS_CAIXA)})")
        if self.get("classificacao.tipo") not in TIPOS_CLASSIFICADOR:
            erros.append(f"classificacao.tipo inválido: {self.get('classificacao.tipo')!r}")
        lim = self.get("classificacao.limite_confianca")
        if not isinstance(lim, (int, float)) or not 0 <= float(lim) <= 1:
            erros.append("classificacao.limite_confianca deve estar entre 0 e 1")
        for chave in ("respondidos", "encaminhados", "erro", "ignorados"):
            if not self.get(f"caixa.pastas_destino.{chave}"):
                erros.append(f"caixa.pastas_destino.{chave} não definido")
        if self.ambiente != "prod" and not self.get("seguranca.destinatarios_permitidos"):
            erros.append(
                "seguranca.destinatarios_permitidos vazio fora de prod: defina os domínios "
                "internos para impedir envio acidental a fornecedores"
            )
        if not self.get("destinatarios.analise_manual.padrao"):
            erros.append("destinatarios.analise_manual.padrao vazio (RF08)")
        for chave in ("tutoriais.arquivo", "filtros.arquivo_fornecedores", "classificacao.arquivo_termos"):
            try:
                self.yaml_referenciado(chave)
            except ErroConfiguracao as e:
                erros.append(str(e))
        if self.classificador == "ia":
            erros += self._validar_ia()
        pend = self.pendencias()
        if pend:
            erros.append("Valores ainda não preenchidos:\n    - " + "\n    - ".join(pend))
        return erros


    def _validar_ia(self) -> List[str]:
        """Checagens mínimas quando ``classificacao.tipo: ia`` (as completas ficam no ``verificar``)."""
        erros: List[str] = []
        lim = self.get("classificacao.ia.limite_confianca")
        if lim is not None and (not isinstance(lim, (int, float)) or not 0 <= float(lim) <= 1):
            erros.append("classificacao.ia.limite_confianca deve estar entre 0 e 1")
        for chave in ("classificacao.ia.arquivo_categorias", "classificacao.ia.arquivo_prompt"):
            if not self.get(chave):
                erros.append(f"{chave} não definido")
            elif not self.caminho(chave).exists():
                erros.append(f"Arquivo não encontrado ({chave}): {self.caminho(chave)}")
        for chave in ("mensagem_correcao", "resumo_padrao", "texto_vazio"):
            if not self.get(f"classificacao.ia.{chave}"):
                erros.append(f"classificacao.ia.{chave} não definido")
        tipo = self.get("classificacao.ia.provedor.tipo", "simulado")
        if tipo not in TIPOS_PROVEDOR_IA:
            erros.append(f"classificacao.ia.provedor.tipo inválido: {tipo!r} (use {', '.join(TIPOS_PROVEDOR_IA)})")
        elif tipo == "http_generico" and not self.get("classificacao.ia.provedor.http_generico.endpoint"):
            erros.append("classificacao.ia.provedor.http_generico.endpoint não definido (provedor corporativo – PA08)")
        return erros


def carregar(perfil: Optional[str] = None, raiz: Path = RAIZ_PROJETO) -> Config:
    """Carrega base + perfil. Não valida (use ``Config.validar``)."""
    perfil = perfil or os.environ.get("RPA_PERFIL") or "dev"
    base = ler_yaml(raiz / "config" / "settings.yaml")
    arq_perfil = raiz / "config" / "perfis" / f"{perfil}.yaml"
    if not arq_perfil.exists():
        disponiveis = sorted(p.stem for p in (raiz / "config" / "perfis").glob("*.yaml"))
        raise ErroConfiguracao(f"Perfil '{perfil}' não existe. Disponíveis: {', '.join(disponiveis)}")
    dados = mesclar(base, ler_yaml(arq_perfil))
    return Config(dados, perfil, raiz)
