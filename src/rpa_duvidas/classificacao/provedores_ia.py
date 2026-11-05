"""Provedores de IA generativa (E3 – RN3.3, RN3.4; pendência PA08).

O provedor corporativo ainda NÃO está definido. Por isso o classificador só
conhece a interface ``ProvedorIA`` e há duas implementações:

* ``simulado``      – respostas fixas (roteiro) ou por regras de um YAML, sem
                      rede. Usado nos testes e na demonstração.
* ``http_generico`` – chamada HTTP POST com JSON. Endpoint, modelo, cabeçalhos,
                      nomes dos campos e caminhos da resposta vêm todos do
                      ``settings.yaml``; a credencial vem de ``segredos.obter()``.
                      Temperatura 0 e modo JSON opcional.

Nenhum endpoint, chave ou nome de provedor fica no código.
"""
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Union, runtime_checkable

from ..extracao import normalizar

Mensagens = List[Dict[str, str]]          # [{"role": "user"|"assistant", "content": "..."}]


class ErroProvedorIA(Exception):
    """Falha na chamada à IA. ``repetir=False`` = não adianta tentar de novo (ex.: sem credencial)."""

    def __init__(self, mensagem: str, *, repetir: bool = True):
        super().__init__(mensagem)
        self.repetir = repetir


class TimeoutProvedorIA(ErroProvedorIA):
    """A IA não respondeu dentro do tempo limite."""


@dataclass
class RespostaProvedor:
    texto: str
    modelo: str
    tokens: Optional[int] = None


@runtime_checkable
class ProvedorIA(Protocol):
    nome: str

    def gerar(self, mensagens: Mensagens, *, timeout: float) -> RespostaProvedor:
        """Envia as mensagens e devolve o texto gerado. Falha = ``ErroProvedorIA``."""
        ...


# --------------------------------------------------------------------------- #
# utilitários
# --------------------------------------------------------------------------- #
def ler_caminho(dados: Any, caminho: str) -> Any:
    """``ler_caminho(d, "choices.0.message.content")`` – números indexam listas."""
    atual = dados
    for parte in [p for p in (caminho or "").split(".") if p]:
        if isinstance(atual, list) and parte.isdigit():
            idx = int(parte)
            atual = atual[idx] if idx < len(atual) else None
        elif isinstance(atual, dict):
            atual = atual.get(parte)
        else:
            return None
        if atual is None:
            return None
    return atual


def trecho_entre(texto: str, inicio: str, fim: str) -> str:
    """Último trecho entre os delimitadores ``inicio`` e ``fim`` (ou vazio)."""
    i = (texto or "").rfind(inicio)
    if i == -1:
        return ""
    i += len(inicio)
    j = texto.find(fim, i)
    return texto[i:j if j != -1 else None].strip()


# --------------------------------------------------------------------------- #
# Simulado
# --------------------------------------------------------------------------- #
ItemRoteiro = Union[str, Dict[str, Any], Exception]


@dataclass
class RegraSimulada:
    """Uma regra do provedor simulado (``config/ia_simulada.yaml``)."""

    nome: str
    contem: List[str] = field(default_factory=list)          # basta um dos termos
    contem_todos: List[str] = field(default_factory=list)    # todos os termos
    resposta: Union[str, Dict[str, Any], None] = None
    falha: str = ""   # "" | timeout | erro | json_invalido | json_invalido_uma_vez

    @staticmethod
    def _tem(termo: str, texto_normalizado: str) -> bool:
        """Termo como palavra inteira (sem acento, minúsculas): "nf" não casa em "informa"."""
        alvo = re.escape(normalizar(termo))
        return bool(alvo) and re.search(r"(?<![a-z0-9])" + alvo + r"(?![a-z0-9])", texto_normalizado) is not None

    def casa(self, texto_normalizado: str) -> bool:
        if self.contem and not any(self._tem(t, texto_normalizado) for t in self.contem):
            return False
        if self.contem_todos and not all(self._tem(t, texto_normalizado) for t in self.contem_todos):
            return False
        return bool(self.contem or self.contem_todos)


class ProvedorSimulado:
    """IA de mentira, determinística e sem rede.

    * ``roteiro``: lista de respostas devolvidas em ordem (texto, dict ou
      exceção a lançar) – usada nos testes;
    * ``regras``: a primeira regra cujo termo aparece no assunto/corpo do
      e-mail (lido entre os delimitadores do prompt) define a resposta;
    * ``padrao``: resposta quando nenhuma regra casa.
    """

    nome = "simulado"

    def __init__(
        self,
        regras: Sequence[RegraSimulada] = (),
        padrao: Union[str, Dict[str, Any], None] = None,
        *,
        modelo: str = "simulado",
        roteiro: Optional[Sequence[ItemRoteiro]] = None,
        texto_invalido: str = "Não foi possível classificar.",
    ):
        self.regras = list(regras)
        self.padrao = padrao
        self.modelo = modelo
        self.roteiro: Optional[List[ItemRoteiro]] = list(roteiro) if roteiro is not None else None
        self.texto_invalido = texto_invalido
        self.chamadas: List[Mensagens] = []

    @classmethod
    def de_dict(cls, dados: Dict[str, Any]) -> "ProvedorSimulado":
        regras = [
            RegraSimulada(
                nome=str(r.get("nome", f"regra_{i + 1}")),
                contem=[str(t) for t in (r.get("contem") or [])],
                contem_todos=[str(t) for t in (r.get("contem_todos") or [])],
                resposta=r.get("resposta"),
                falha=str(r.get("falha") or ""),
            )
            for i, r in enumerate(dados.get("regras") or [])
        ]
        return cls(regras, dados.get("padrao"), modelo=str(dados.get("modelo", "simulado")),
                   texto_invalido=str(dados.get("texto_invalido", "Não foi possível classificar.")))

    @staticmethod
    def _texto(resposta: Union[str, Dict[str, Any], None]) -> str:
        if resposta is None:
            return ""
        return resposta if isinstance(resposta, str) else json.dumps(resposta, ensure_ascii=False)

    def _tokens(self, mensagens: Mensagens, saida: str) -> int:
        return sum(len(m.get("content", "")) for m in mensagens) // 4 + len(saida) // 4

    def gerar(self, mensagens: Mensagens, *, timeout: float) -> RespostaProvedor:
        self.chamadas.append([dict(m) for m in mensagens])
        if self.roteiro is not None:
            if not self.roteiro:
                raise ErroProvedorIA("roteiro do provedor simulado esgotado")
            item = self.roteiro.pop(0)
            if isinstance(item, Exception):
                raise item
            texto = self._texto(item)
            return RespostaProvedor(texto, self.modelo, self._tokens(mensagens, texto))

        prompt = next((m.get("content", "") for m in mensagens if m.get("role") == "user"), "")
        alvo = normalizar(
            trecho_entre(prompt, "<<<ASSUNTO>>>", "<<<FIM_ASSUNTO>>>") + "\n"
            + trecho_entre(prompt, "<<<CORPO>>>", "<<<FIM_CORPO>>>")
        )
        correcao = len(mensagens) > 1
        regra = next((r for r in self.regras if r.casa(alvo)), None)
        resposta = regra.resposta if regra else self.padrao
        if regra and regra.falha:
            if regra.falha == "timeout":
                raise TimeoutProvedorIA(f"timeout simulado (regra {regra.nome})")
            if regra.falha == "erro":
                raise ErroProvedorIA(f"erro simulado (regra {regra.nome})")
            if regra.falha == "json_invalido" or (regra.falha == "json_invalido_uma_vez" and not correcao):
                resposta = self.texto_invalido
        texto = self._texto(resposta)
        return RespostaProvedor(texto, self.modelo, self._tokens(mensagens, texto))


# --------------------------------------------------------------------------- #
# HTTP genérico
# --------------------------------------------------------------------------- #
class ProvedorHttpGenerico:
    """POST JSON num endpoint configurável. Tudo o que é específico do provedor vem da configuração.

    ``conf`` (``classificacao.ia.provedor.http_generico``):
      endpoint, modelo, credencial (nome em ``segredos``), cabecalhos (o texto
      ``{credencial}`` é trocado pelo segredo), temperatura, modo_json,
      campo_modelo, campo_mensagens, campo_temperatura, parametros_modo_json,
      corpo_extra, caminho_texto_resposta, caminho_tokens, caminho_modelo.
    """

    nome = "http_generico"

    def __init__(
        self,
        conf: Dict[str, Any],
        obter_segredo: Optional[Callable[..., Optional[str]]] = None,
        abrir: Optional[Callable[..., Any]] = None,
    ):
        self.conf = dict(conf or {})
        self.endpoint = str(self.conf.get("endpoint") or "")
        self.modelo = str(self.conf.get("modelo") or "")
        if not self.endpoint:
            raise ValueError("classificacao.ia.provedor.http_generico.endpoint não definido (PA08)")
        if obter_segredo is None:
            from .. import segredos

            obter_segredo = segredos.obter
        self._obter_segredo = obter_segredo
        self._abrir = abrir or urllib.request.urlopen

    def montar_corpo(self, mensagens: Mensagens) -> Dict[str, Any]:
        c = self.conf
        corpo: Dict[str, Any] = {}
        if c.get("campo_modelo") and self.modelo:
            corpo[str(c["campo_modelo"])] = self.modelo
        corpo[str(c.get("campo_mensagens") or "messages")] = mensagens
        if c.get("campo_temperatura"):
            corpo[str(c["campo_temperatura"])] = c.get("temperatura", 0)
        if c.get("modo_json") and isinstance(c.get("parametros_modo_json"), dict):
            corpo.update(c["parametros_modo_json"])
        corpo.update(c.get("corpo_extra") or {})
        return corpo

    def _cabecalhos(self) -> Dict[str, str]:
        nome = str(self.conf.get("credencial") or "")
        segredo = ""
        if nome:
            try:
                segredo = self._obter_segredo(nome, obrigatorio=True) or ""
            except KeyError as e:
                raise ErroProvedorIA(str(e), repetir=False) from None
        cab = {"Content-Type": "application/json"}
        for k, v in (self.conf.get("cabecalhos") or {}).items():
            cab[str(k)] = str(v).replace("{credencial}", segredo)
        return cab

    def gerar(self, mensagens: Mensagens, *, timeout: float) -> RespostaProvedor:
        corpo = json.dumps(self.montar_corpo(mensagens), ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.endpoint, data=corpo, headers=self._cabecalhos(), method="POST")
        try:
            with self._abrir(req, timeout=timeout) as resp:
                dados = json.loads(resp.read().decode("utf-8"))
        except (socket.timeout, TimeoutError) as e:
            raise TimeoutProvedorIA(f"timeout após {timeout:.0f} s") from e
        except urllib.error.HTTPError as e:
            # Só o código: o corpo do erro pode ecoar o prompt (RN8.2)
            raise ErroProvedorIA(f"HTTP {e.code}") from None
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise TimeoutProvedorIA(f"timeout após {timeout:.0f} s") from None
            raise ErroProvedorIA(f"falha de conexão: {type(e.reason).__name__}") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ErroProvedorIA("resposta do provedor não é JSON") from None
        texto = ler_caminho(dados, str(self.conf.get("caminho_texto_resposta") or ""))
        if not isinstance(texto, str):
            raise ErroProvedorIA("texto da resposta não encontrado em caminho_texto_resposta")
        tokens = ler_caminho(dados, str(self.conf.get("caminho_tokens") or ""))
        modelo = ler_caminho(dados, str(self.conf.get("caminho_modelo") or "")) or self.modelo
        return RespostaProvedor(texto, str(modelo), int(tokens) if isinstance(tokens, (int, float)) else None)
