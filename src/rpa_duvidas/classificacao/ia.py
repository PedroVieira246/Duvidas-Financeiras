"""Classificador por IA generativa (F08 – etapas E3, E4 e E5 da especificação funcional).

Fluxo de ``ClassificadorIA.classificar``::

    mascara + trunca (RN3.1/RN3.2) ─> monta o prompt (Anexo A) ─> chama o provedor
        (timeout 30 s + 2 novas tentativas, espera 2 s e 4 s)
    ─> valida (V1–V10); inválido → 1 nova chamada de correção de formato
    ─> decide (D1–D7) ─> Classificacao (TUT_* ou MANUAL + detalhes para E7/E8)

Regras de proteção:

* falha da IA nunca vira exceção para o ciclo: o e-mail vai para MANUAL com
  ``IA_INDISPONIVEL`` (lacuna R3) – o fornecedor precisa ser atendido;
* depois de N falhas seguidas no mesmo ciclo (``max_falhas_seguidas``, 5),
  a IA não é mais chamada no ciclo e fica um alerta pendente para o robô
  avisar os analistas (RNF-IA03);
* o texto da IA nunca vai ao fornecedor (RN6.1): só o resumo vai ao analista;
* o log técnico não recebe corpo, prompt nem resumo (RN8.2).
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ..config import TIPOS_PROVEDOR_IA as TIPOS_PROVEDOR
from ..config import Config, ErroConfiguracao
from ..extracao import limpar_assunto
from ..mascaramento import mascarar, mascarar_lista, preparar_para_ia
from ..modelos import Categoria, Classificacao, EmailRecebido, MotivoManual
from .decisao_ia import CategoriasIA, Decisao, decidir
from .provedores_ia import ErroProvedorIA, Mensagens, ProvedorHttpGenerico, ProvedorIA, ProvedorSimulado, RespostaProvedor
from .validacao_ia import RespostaIAValidada, validar_resposta

log = logging.getLogger(__name__)



# --------------------------------------------------------------------------- #
# Prompt (config/prompts/classificacao_vN.txt)
# --------------------------------------------------------------------------- #
class ModeloPrompt:
    """Texto do prompt com os 4 marcadores do Anexo A."""

    MARCADORES = ("{{ASSUNTO}}", "{{CORPO}}", "{{ANEXOS}}", "{{HISTORICO}}")
    DELIMITADORES = ("<<<ASSUNTO>>>", "<<<FIM_ASSUNTO>>>", "<<<ANEXOS>>>", "<<<FIM_ANEXOS>>>",
                     "<<<CORPO>>>", "<<<FIM_CORPO>>>", "<<<HISTORICO>>>", "<<<FIM_HISTORICO>>>")
    _RE_MARCADOR = re.compile(r"\{\{(ASSUNTO|CORPO|ANEXOS|HISTORICO)\}\}")

    def __init__(self, texto: str, versao: str):
        self.texto = texto
        self.versao = versao
        self.hash = hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]

    @classmethod
    def carregar(cls, caminho: Path) -> "ModeloPrompt":
        if not caminho.exists():
            raise ErroConfiguracao(f"Prompt da IA não encontrado: {caminho}")
        return cls(caminho.read_text(encoding="utf-8"), caminho.stem)

    def problemas(self) -> List[str]:
        saida = [f"marcador {m} deve aparecer 1 vez (aparece {self.texto.count(m)})"
                 for m in self.MARCADORES if self.texto.count(m) != 1]
        saida += [f"delimitador {d} ausente" for d in self.DELIMITADORES if d not in self.texto]
        return saida

    @staticmethod
    def neutralizar(texto: str) -> str:
        """Impede que o conteúdo do e-mail feche os delimitadores do prompt (RNF-IA05 / R11)."""
        return (texto or "").replace("<<<", "<<").replace(">>>", ">>")

    def montar(self, assunto: str, corpo: str, anexos: str, historico: str) -> str:
        valores = {"ASSUNTO": assunto, "CORPO": corpo, "ANEXOS": anexos, "HISTORICO": historico}
        # Substituição em uma passada: o conteúdo inserido nunca é reprocessado
        return self._RE_MARCADOR.sub(lambda m: self.neutralizar(valores[m.group(1)]), self.texto)


# --------------------------------------------------------------------------- #
# Parâmetros
# --------------------------------------------------------------------------- #
@dataclass
class ParametrosIA:
    timeout_segundos: float = 30.0
    novas_tentativas: int = 2
    esperas_segundos: Sequence[float] = (2.0, 4.0)
    correcoes_formato: int = 1
    max_falhas_seguidas: int = 5
    limite_corpo: int = 6000
    limite_historico: int = 2000
    # Textos: vêm do settings.yaml (classificacao.ia.*) – nada de texto de negócio no código
    texto_vazio: str = ""
    mensagem_correcao: str = ""
    resumo_padrao: str = ""

    @classmethod
    def de_config(cls, conf: Dict[str, Any]) -> "ParametrosIA":
        p = cls()
        for nome in cls.__dataclass_fields__:
            if nome in conf and conf[nome] is not None:
                padrao = getattr(p, nome)
                valor = conf[nome]
                if isinstance(padrao, (list, tuple)):
                    valor = tuple(float(x) for x in valor)
                elif isinstance(padrao, bool):
                    valor = bool(valor)
                elif isinstance(padrao, int):
                    valor = int(valor)
                elif isinstance(padrao, float):
                    valor = float(valor)
                else:
                    valor = str(valor)
                setattr(p, nome, valor)
        return p


# --------------------------------------------------------------------------- #
# Resultado da consulta
# --------------------------------------------------------------------------- #
@dataclass
class ConsultaIA:
    """O que aconteceu na conversa com a IA para um e-mail (antes da decisão)."""

    resposta: Optional[RespostaIAValidada] = None
    falha: Optional[str] = None             # MotivoManual.IA_INDISPONIVEL / RESPOSTA_IA_INVALIDA
    detalhe_falha: str = ""
    erros_validacao: List[str] = field(default_factory=list)
    modelo: str = ""
    tentativas: int = 0                     # chamadas feitas ao provedor (inclui novas tentativas e correção)
    latencia_ms: int = 0
    tokens: Optional[int] = None
    correcao_usada: bool = False
    respostas_brutas: List[Dict[str, Any]] = field(default_factory=list)


class _FalhaChamada(Exception):
    def __init__(self, erro: ErroProvedorIA):
        super().__init__(str(erro))
        self.erro = erro


# --------------------------------------------------------------------------- #
# Classificador
# --------------------------------------------------------------------------- #
class ClassificadorIA:
    """Implementa a interface ``Classificador`` usando um ``ProvedorIA``."""

    def __init__(
        self,
        provedor: ProvedorIA,
        prompt: ModeloPrompt,
        categorias: CategoriasIA,
        limite_confianca: float,
        parametros: Optional[ParametrosIA] = None,
        *,
        dormir: Callable[[float], None] = time.sleep,
        relogio: Callable[[], float] = time.perf_counter,
    ):
        self.provedor = provedor
        self.prompt = prompt
        self.categorias = categorias
        self.limite = float(limite_confianca)
        self.p = parametros or ParametrosIA()
        self._dormir = dormir
        self._relogio = relogio
        self.iniciar_ciclo()

    # ---- estado por ciclo (RNF-IA03) ------------------------------------- #
    def iniciar_ciclo(self) -> None:
        self.falhas_seguidas = 0
        self.circuito_aberto = False
        self._alerta_pendente: Optional[int] = None

    def consumir_alerta(self) -> Optional[int]:
        """Nº de falhas seguidas, uma única vez, quando a IA foi desligada no ciclo."""
        alerta, self._alerta_pendente = self._alerta_pendente, None
        return alerta

    # ---- montagem do prompt (E3) ----------------------------------------- #
    def montar_prompt(self, assunto: str, corpo: str, email: Optional[EmailRecebido] = None) -> str:
        vazio = self.p.texto_vazio
        anexos = ", ".join(mascarar_lista(email.nomes_anexos)) if email and email.nomes_anexos else vazio
        historico = preparar_para_ia(email.historico_resumido, self.p.limite_historico) if email else ""
        return self.prompt.montar(
            assunto=mascarar(limpar_assunto(assunto or "")) or vazio,
            corpo=preparar_para_ia(corpo, self.p.limite_corpo) or vazio,
            anexos=anexos,
            historico=historico or vazio,
        )

    # ---- chamada com novas tentativas ------------------------------------ #
    def _chamar(self, mensagens: Mensagens, consulta: ConsultaIA) -> RespostaProvedor:
        esperas = list(self.p.esperas_segundos) or [0.0]
        ultimo: Optional[ErroProvedorIA] = None
        for tentativa in range(1 + max(0, self.p.novas_tentativas)):
            if tentativa:
                self._dormir(esperas[min(tentativa - 1, len(esperas) - 1)])
            consulta.tentativas += 1
            inicio = self._relogio()
            try:
                resp = self.provedor.gerar(mensagens, timeout=self.p.timeout_segundos)
                consulta.latencia_ms += int((self._relogio() - inicio) * 1000)
                consulta.modelo = resp.modelo or consulta.modelo
                if resp.tokens is not None:
                    consulta.tokens = (consulta.tokens or 0) + int(resp.tokens)
                return resp
            except ErroProvedorIA as erro:
                consulta.latencia_ms += int((self._relogio() - inicio) * 1000)
                ultimo = erro
                log.warning("IA: falha na chamada %d (%s: %s)", consulta.tentativas, type(erro).__name__, erro)
                if not erro.repetir:
                    break
        raise _FalhaChamada(ultimo or ErroProvedorIA("falha desconhecida"))

    def _validar(self, texto: str):
        return validar_resposta(
            texto, self.categorias.codigos_validos, self.categorias.tutoriais_validos(), self.categorias.sinais_excecao
        )

    # ---- E3 + E4 ---------------------------------------------------------- #
    def consultar(self, assunto: str, corpo: str, email: Optional[EmailRecebido] = None) -> ConsultaIA:
        """Chama a IA e valida a resposta. Nunca lança exceção."""
        consulta = ConsultaIA(modelo=getattr(self.provedor, "modelo", "") or getattr(self.provedor, "nome", ""))
        if self.circuito_aberto:
            consulta.falha = MotivoManual.IA_INDISPONIVEL
            consulta.detalhe_falha = f"IA desligada neste ciclo após {self.falhas_seguidas} falhas seguidas"
            return consulta
        try:
            mensagens: Mensagens = [{"role": "user", "content": self.montar_prompt(assunto, corpo, email)}]
            try:
                resp = self._chamar(mensagens, consulta)
            except _FalhaChamada as f:
                self._registrar_falha()
                consulta.falha = MotivoManual.IA_INDISPONIVEL
                consulta.detalhe_falha = f"{type(f.erro).__name__}: {f.erro}"
                return consulta
            self.falhas_seguidas = 0
            resultado = self._validar(resp.texto)
            consulta.respostas_brutas.append({"chamada": 1, "texto": resp.texto, "valida": resultado.valida})
            if not resultado.valida:
                consulta.erros_validacao += resultado.erros
            correcoes = 0
            while not resultado.valida and correcoes < min(1, max(0, self.p.correcoes_formato)):  # no máximo 1 (E4)
                correcoes += 1
                consulta.correcao_usada = True
                mensagens = mensagens + [
                    {"role": "assistant", "content": resp.texto},
                    {"role": "user", "content": self.p.mensagem_correcao},
                ]
                try:
                    resp = self._chamar(mensagens, consulta)
                except _FalhaChamada as f:
                    consulta.detalhe_falha = f"correção falhou – {type(f.erro).__name__}: {f.erro}"
                    break
                resultado = self._validar(resp.texto)
                consulta.respostas_brutas.append(
                    {"chamada": 1 + correcoes, "texto": resp.texto, "valida": resultado.valida}
                )
                if not resultado.valida:
                    consulta.erros_validacao += resultado.erros
            if resultado.valida:
                consulta.resposta = resultado.resposta
            else:
                consulta.falha = MotivoManual.RESPOSTA_IA_INVALIDA
                consulta.detalhe_falha = consulta.detalhe_falha or "; ".join(resultado.erros)
        except Exception as erro:  # proteção final (R3): nada de exceção para o ciclo
            log.error("IA: erro inesperado na consulta (%s)", type(erro).__name__)
            log.debug("Detalhe do erro inesperado da IA", exc_info=True)
            consulta.resposta = None
            consulta.falha = MotivoManual.IA_INDISPONIVEL
            consulta.detalhe_falha = f"erro inesperado: {type(erro).__name__}"
        return consulta

    def _registrar_falha(self) -> None:
        self.falhas_seguidas += 1
        if self.falhas_seguidas >= max(1, self.p.max_falhas_seguidas) and not self.circuito_aberto:
            self.circuito_aberto = True
            self._alerta_pendente = self.falhas_seguidas
            log.error("IA: %d falhas seguidas – IA desligada no restante do ciclo (RNF-IA03)", self.falhas_seguidas)

    # ---- E5 + montagem da Classificacao ------------------------------------ #
    def montar_classificacao(self, consulta: ConsultaIA, decisao: Decisao) -> Classificacao:
        r = consulta.resposta
        manual = not decisao.responder
        resumo = ((r.resumo_duvida if r else None) or self.p.resumo_padrao) if manual else ""
        cat_docx = r.categoria if r else ""
        partes = [f"IA {cat_docx or '—'}"]
        if r:
            partes[0] += f" ({r.confianca:.2f})"
        partes.append(f"{decisao.regra}: {decisao.explicacao}")
        if consulta.falha and consulta.detalhe_falha:
            partes.append(consulta.detalhe_falha)
        if r and r.justificativa:
            partes.append(r.justificativa)
        detalhes: Dict[str, Any] = {
            "classificador": "ia",
            "categoria_docx": cat_docx,
            "categoria_docx_descricao": self.categorias.descricao(cat_docx),
            "categoria_sugerida": cat_docx,
            "resumo_duvida": resumo,
            "categorias_secundarias": list(r.categorias_secundarias) if r else [],
            "sinais_excecao": list(r.sinais_excecao) if r else [],
            "acao_ia": r.acao if r else "",
            "tutorial_ia": (r.tutorial or "") if r else "",
            "regra_decisao": decisao.regra,
            "modelo": consulta.modelo,
            "versao_prompt": self.prompt.versao,
            "hash_prompt": self.prompt.hash,
            "latencia_ms": consulta.latencia_ms,
            "tentativas": consulta.tentativas,
            "tokens": consulta.tokens,
            "formato_corrigido": bool(r and r.formato_corrigido),
            "correcao_usada": consulta.correcao_usada,
            "ajustes_validacao": list(r.ajustes) if r else [],
            "erros_validacao": list(consulta.erros_validacao),
            "resposta_ia": r.como_dict() if r else None,
            "respostas_brutas": list(consulta.respostas_brutas),
        }
        return Classificacao(
            categoria=decisao.categoria,
            confianca=round(r.confianca, 2) if r else 0.0,
            motivo=" | ".join(partes),
            motivo_manual=decisao.motivo_manual,
            detalhes=detalhes,
        )

    def classificar(self, assunto: str, corpo: str, email: Optional[EmailRecebido] = None) -> Classificacao:
        consulta = self.consultar(assunto, corpo, email)
        decisao = decidir(consulta.resposta, self.categorias, self.limite, consulta.falha)
        return self.montar_classificacao(consulta, decisao)


# --------------------------------------------------------------------------- #
# Fábricas
# --------------------------------------------------------------------------- #
def carregar_categorias(cfg: Config) -> CategoriasIA:
    try:
        return CategoriasIA.de_dict(cfg.yaml_referenciado("classificacao.ia.arquivo_categorias"))
    except ValueError as e:
        raise ErroConfiguracao(str(e)) from None


def carregar_prompt(cfg: Config) -> ModeloPrompt:
    prompt = ModeloPrompt.carregar(cfg.caminho("classificacao.ia.arquivo_prompt"))
    problemas = prompt.problemas()
    if problemas:
        raise ErroConfiguracao("Prompt da IA inválido: " + "; ".join(problemas))
    return prompt


def criar_provedor(cfg: Config) -> ProvedorIA:
    tipo = cfg.get("classificacao.ia.provedor.tipo", "simulado")
    if tipo == "simulado":
        chave = "classificacao.ia.provedor.simulado.arquivo_regras"
        dados = cfg.yaml_referenciado(chave) if cfg.get(chave) else {}
        return ProvedorSimulado.de_dict(dados)
    if tipo == "http_generico":
        try:
            return ProvedorHttpGenerico(cfg.get("classificacao.ia.provedor.http_generico", {}) or {})
        except ValueError as e:
            raise ErroConfiguracao(str(e)) from None
    raise ErroConfiguracao(f"classificacao.ia.provedor.tipo inválido: {tipo!r} (use {', '.join(TIPOS_PROVEDOR)})")


def criar_classificador_ia(cfg: Config, provedor: Optional[ProvedorIA] = None, **kw: Any) -> ClassificadorIA:
    return ClassificadorIA(
        provedor=provedor or criar_provedor(cfg),
        prompt=carregar_prompt(cfg),
        categorias=carregar_categorias(cfg),
        limite_confianca=cfg.limite_confianca,
        parametros=ParametrosIA.de_config(cfg.get("classificacao.ia", {}) or {}),
        **kw,
    )


def verificar_ia(cfg: Config, modelos_existentes: Sequence[str], tutoriais_configurados: Sequence[str]) -> List[str]:
    """Checagens do comando ``verificar`` para a IA (item p). Devolve a lista de problemas."""
    problemas: List[str] = []
    try:
        prompt = ModeloPrompt.carregar(cfg.caminho("classificacao.ia.arquivo_prompt"))
        problemas += [f"Prompt {prompt.versao}: {p}" for p in prompt.problemas()]
    except ErroConfiguracao as e:
        problemas.append(str(e))
    try:
        cats = carregar_categorias(cfg)
        for codigo in cats.sem_mapeamento():
            problemas.append(f"categorias_ia.yaml: {codigo} sem mapeamento (vai para manual – CATEGORIA_SEM_TUTORIAL)")
        for c in cats.categorias.values():
            if c.tutorial and c.tutorial not in tutoriais_configurados:
                problemas.append(f"categorias_ia.yaml: {c.codigo} → {c.tutorial} sem entrada no arquivo de tutoriais")
            if c.tutorial and c.tutorial not in modelos_existentes:
                problemas.append(f"categorias_ia.yaml: {c.codigo} → {c.tutorial} sem modelo {c.tutorial}.html.j2")
    except ErroConfiguracao as e:
        problemas.append(str(e))
    tipo = cfg.get("classificacao.ia.provedor.tipo", "simulado")
    if tipo == "http_generico":
        conf = cfg.get("classificacao.ia.provedor.http_generico", {}) or {}
        for chave in ("endpoint", "modelo", "caminho_texto_resposta"):
            if not conf.get(chave):
                problemas.append(f"classificacao.ia.provedor.http_generico.{chave} não definido (PA08)")
        nome = conf.get("credencial")
        if nome:
            from .. import segredos

            if not segredos.obter(str(nome), obrigatorio=False):
                problemas.append(f"Credencial da IA '{nome}' não encontrada (python -m keyring set rpa_duvidas {nome})")
    elif tipo == "simulado" and cfg.ambiente == "prod":
        problemas.append("classificacao.ia.provedor.tipo = simulado em prod: a IA real não está configurada")
    elif tipo not in TIPOS_PROVEDOR:
        problemas.append(f"classificacao.ia.provedor.tipo inválido: {tipo!r}")
    return problemas
