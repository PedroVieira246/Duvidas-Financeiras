"""Carga e validação da configuração (F01).

``config/settings.yaml`` (base) + ``config/perfis/<perfil>.yaml`` (o que muda)
+ ``config/configuracao.xlsx`` (v0.3.0 – só nos perfis com
``configuracao_xlsx.obrigatoria: true``, como o ``calibracao``).
O perfil vem do argumento ``--perfil`` ou da variável ``RPA_PERFIL``.
"""
from __future__ import annotations

import copy
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import yaml



def raiz_aplicacao() -> Path:
    """Pasta da aplicação: a do .exe (PyInstaller) ou a raiz do projeto (seção 4.4).

    Fica aqui o que a instalação edita ou gera: ``config\\configuracao.xlsx``,
    ``modelos\\`` (substitui o .j2 padrão), ``dados\\``, ``logs\\`` e ``arquivo\\``.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def raiz_recursos() -> Path:
    """Arquivos empacotados no .exe (``settings.yaml``, perfis, modelos .j2 padrão, prompts)."""
    return Path(getattr(sys, "_MEIPASS", raiz_aplicacao()))


def perfil_padrao() -> str:
    """``RPA_PERFIL`` ou, sem ela, ``calibracao`` no executável e ``dev`` no código-fonte."""
    return os.environ.get("RPA_PERFIL") or ("calibracao" if getattr(sys, "frozen", False) else "dev")


RAIZ_PROJETO = raiz_aplicacao()
MARCADOR_PENDENTE = "<PREENCHER"
MARCADORES_PENDENTE = (MARCADOR_PENDENTE, "A_PREENCHER")
DESTINOS_RESPOSTA = ("FORNECEDOR", "TESTE")
ACOES_MANUAL = ("CATEGORIZAR", "ENCAMINHAR")
_RE_EMAIL = re.compile(r"^[^@\s;,<>]+@[^@\s;,<>]+\.[^@\s;,<>]+$")
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
    elif isinstance(dados, str) and any(m in dados for m in MARCADORES_PENDENTE):
        yield f"{prefixo} = {dados}"


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
class Config:
    """Acesso à configuração mesclada.

    ``cfg.get("caixa.pastas_destino.erro")`` lê com notação de pontos.
    """

    def __init__(self, dados: Dict[str, Any], perfil: str, raiz: Path = RAIZ_PROJETO,
                 recursos: Optional[Path] = None):
        self.dados = dados
        self.perfil = perfil
        self.raiz = raiz
        self.recursos = recursos or raiz
        self._cache_yaml: Dict[str, Dict[str, Any]] = {}
        self.erros_xlsx: List[Any] = []     # ErroCelula da planilha de configuração (v0.3.0)

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
        """Resolve um caminho da configuração (relativo à raiz da aplicação).

        v0.3.0: se o caminho relativo não existe na pasta da aplicação mas existe
        entre os recursos empacotados no .exe (ex.: ``config/modelos``), vale o
        recurso. Fora do executável as duas raízes são a mesma pasta.
        """
        bruto = chave_ou_valor if eh_valor else self.exigir(chave_ou_valor)
        p = Path(expandir(str(bruto)).replace("\\", "/")) if os.sep == "/" else Path(expandir(str(bruto)))
        if p.is_absolute():
            return p
        na_aplicacao = self.raiz / p
        if self.recursos != self.raiz and not na_aplicacao.exists() and (self.recursos / p).exists():
            return self.recursos / p
        return na_aplicacao

    def yaml_referenciado(self, chave: str) -> Dict[str, Any]:
        """Carrega (com cache) um YAML cujo caminho está em ``chave``.

        v0.3.0: o conteúdo pode vir já carregado da planilha de configuração, em
        ``dados["_inline"][chave]`` (termos e tutoriais) – tem prioridade.
        """
        inline = (self.dados.get("_inline") or {}).get(chave)
        if inline is not None:
            return inline
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

    @property
    def usa_xlsx(self) -> bool:
        return bool(self.get("configuracao_xlsx.obrigatoria", False))

    @property
    def destino_teste(self) -> Optional[str]:
        """E-mail destino padrão quando ``execucao.destino_respostas = TESTE`` (D02); senão None."""
        if str(self.get("execucao.destino_respostas", "FORNECEDOR")).upper() != "TESTE":
            return None
        return str(self.get("execucao.email_destino_padrao", "") or "").strip().lower() or None

    @property
    def acao_manual(self) -> str:
        return str(self.get("destinatarios.acao_manual", "ENCAMINHAR") or "ENCAMINHAR").upper()

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
        if self.acao_manual not in ACOES_MANUAL:
            erros.append(f"destinatarios.acao_manual inválido: {self.acao_manual!r} (use {', '.join(ACOES_MANUAL)})")
        elif (self.acao_manual == "ENCAMINHAR" and self.destino_teste is None
              and not self.get("destinatarios.analise_manual.padrao")):
            erros.append("destinatarios.analise_manual.padrao vazio (RF08)")
        erros += self._validar_destino_respostas()
        if self.usa_xlsx:
            erros += self._validar_calibracao()
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
        return [str(e) for e in self.erros_xlsx] + erros

    def _validar_destino_respostas(self) -> List[str]:
        """v0.3.0 – envio de teste para o destino padrão (seção 6.2)."""
        erros: List[str] = []
        destino = str(self.get("execucao.destino_respostas", "FORNECEDOR")).upper()
        if destino not in DESTINOS_RESPOSTA:
            erros.append(f"execucao.destino_respostas inválido: {destino!r} (use {', '.join(DESTINOS_RESPOSTA)})")
            return erros
        if destino == "TESTE":
            padrao = str(self.get("execucao.email_destino_padrao", "") or "").strip().lower()
            if not _RE_EMAIL.match(padrao):
                erros.append("execucao.email_destino_padrao obrigatório e válido com destino_respostas = TESTE")
            elif padrao == str(self.get("caixa.conta", "") or "").strip().lower():
                erros.append("execucao.email_destino_padrao precisa ser diferente do e-mail da caixa (caixa.conta)")
        return erros

    def _validar_calibracao(self) -> List[str]:
        """Regras fixas dos perfis configurados pela planilha (calibração – D02, D04, D05, D06)."""
        erros: List[str] = []
        if self.classificador != "palavras_chave":
            erros.append("IA desligada nesta etapa: classificacao.tipo deve ser palavras_chave (D04)")
        if self.destino_teste is None and str(self.get("execucao.destino_respostas", "")).upper() != "TESTE":
            erros.append("Na calibração as respostas vão só para o destino padrão: destino_respostas = TESTE (D02)")
        if not self.get("escritorios.arquivo"):
            erros.append("escritorios.arquivo (caminho_planilha_escritorios) não definido (D06)")
        if not self.get("arquivamento.raiz"):
            erros.append("arquivamento.raiz (caminho_arquivo_emails) não definido (D05)")
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


def _derivar(dados: Dict[str, Any]) -> Dict[str, Any]:
    """Valores calculados a partir de outros (v0.3.0).

    Com ``destino_respostas = TESTE``, ``seguranca.destinatarios_permitidos`` é
    montado automaticamente como ``[email_destino_padrao] + AVISO_ERRO``
    (seção 6.2, item 5) – qualquer valor do perfil é substituído.
    """
    execucao = dados.get("execucao") or {}
    if str(execucao.get("destino_respostas", "")).upper() == "TESTE":
        padrao = str(execucao.get("email_destino_padrao", "") or "").strip().lower()
        avisos = [str(e).strip().lower() for e in ((dados.get("destinatarios") or {}).get("avisos_erro") or []) if e]
        permitidos = list(dict.fromkeys([e for e in [padrao] + avisos if e]))
        dados.setdefault("seguranca", {})["destinatarios_permitidos"] = permitidos
    return dados


def carregar(
    perfil: Optional[str] = None,
    raiz: Optional[Path] = None,
    *,
    recursos: Optional[Path] = None,
    usar_xlsx: bool = True,
    arquivo_xlsx: Optional[Path] = None,
) -> Config:
    """Carrega base + perfil (+ planilha de configuração). Não valida (use ``Config.validar``).

    A planilha só é lida nos perfis com ``configuracao_xlsx.obrigatoria: true``
    (ou quando ``arquivo_xlsx`` é informado). Nesses perfis, planilha ausente é
    erro; erros de célula ficam em ``Config.erros_xlsx`` e entram no ``validar()``.
    ``usar_xlsx=False`` ignora a planilha (usado pelo gerador do modelo).
    """
    if raiz is None:
        raiz, recursos = raiz_aplicacao(), recursos or raiz_recursos()
    raiz = Path(raiz)
    recursos = Path(recursos) if recursos is not None else raiz
    perfil = perfil or perfil_padrao()
    base = ler_yaml(recursos / "config" / "settings.yaml")
    arq_perfil = recursos / "config" / "perfis" / f"{perfil}.yaml"
    if not arq_perfil.exists():
        disponiveis = sorted(p.stem for p in (recursos / "config" / "perfis").glob("*.yaml"))
        raise ErroConfiguracao(f"Perfil '{perfil}' não existe. Disponíveis: {', '.join(disponiveis)}")
    dados = mesclar(base, ler_yaml(arq_perfil))
    erros_xlsx: List[Any] = []
    obrigatoria = bool((dados.get("configuracao_xlsx") or {}).get("obrigatoria", False))
    if usar_xlsx and (obrigatoria or arquivo_xlsx is not None):
        from .config_xlsx import ler_configuracao_xlsx

        caminho = Path(arquivo_xlsx) if arquivo_xlsx is not None else \
            raiz / str((dados.get("configuracao_xlsx") or {}).get("arquivo", "config/configuracao.xlsx"))
        if not caminho.exists():
            raise ErroConfiguracao(
                f"Planilha de configuração não encontrada: {caminho}. Copie o modelo configuracao.xlsx "
                "para a pasta config ao lado do executável e preencha os valores A_PREENCHER."
            )
        try:
            parcial, erros_xlsx = ler_configuracao_xlsx(caminho)
        except ErroConfiguracao:
            raise
        except Exception as e:
            raise ErroConfiguracao(f"Não foi possível ler a planilha de configuração {caminho}: {e}") from e
        dados = mesclar(dados, parcial)
    cfg = Config(_derivar(dados), perfil, raiz, recursos)
    cfg.erros_xlsx = list(erros_xlsx)
    return cfg
