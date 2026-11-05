"""Orquestração de um ciclo (F17 base + F12, F13, F14, F16).

Todo e-mail lido termina em um destino: respondido, encaminhado, ignorado
(resposta automática) ou erro. O erro em um e-mail não interrompe o ciclo
(RNF02) e nenhum e-mail é respondido duas vezes (RNF01).

Sequência por e-mail::

    já está no registro? ──sim──> reconcilia (só move) ou reprocessa se deu erro antes
          │não
    extrai texto ─> resposta automática? ─> Ignorados
          │
    mensagem do próprio RPA? ─> Ignorados (motivo PROPRIO_RPA)              [v0.2.1]
          │
    remetente interno? / spam (SCL)? ─> Ignorados (motivo INTERNO / SPAM)   [v0.2.0 – E2]
          │
    fornecedor na lista? ──não──> encaminha [MANUAL – FORA DA LISTA]
          │sim
    classifica (palavras-chave ou IA) ─> confiança < limite? ─> MANUAL (BAIXA CONFIANÇA)
          │
    grava EM_ANDAMENTO ─> responde/encaminha ─> grava ação executada
          ─> marca lido + categoria + move ─> grava evento
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from . import extracao
from .caixa.base import CaixaEmail
from .classificacao.base import Classificador
from .config import Config
from .filtros import ErroEscritorios, FiltroInterno, FiltroSpam, ListaFornecedores, MapaEscritorios
from .modelos import (VERBOS_JA_TRATADO, Acao, Categoria, Classificacao, Destino, EmailRecebido, MotivoIgnorado,
                      MotivoManual, Resultado, Status)
from .registro import Registro
from .respostas import GeradorRespostas, protocolo
from .tutoriais import RepositorioTutoriais

log = logging.getLogger(__name__)


from .caixa.base import ErroSeguranca  # noqa: E402  (mantém rpa_duvidas.ciclo.ErroSeguranca)


@dataclass
class ResumoCiclo:
    ciclo_id: str
    modo: str
    inicio: datetime = field(default_factory=datetime.now)
    resultados: List[Resultado] = field(default_factory=list)
    # v0.3.0: e-mails de não fornecedores deixados intactos (seção 6.1) e falha que impediu o ciclo
    nao_fornecedores: int = 0
    falha: str = ""

    def contagem(self) -> Dict[str, int]:
        c = {"lidos": len(self.resultados), "respondidos": 0, "encaminhados": 0, "ignorados": 0, "erros": 0, "reconciliados": 0}
        for r in self.resultados:
            if r.status == Status.ERRO:
                c["erros"] += 1
            elif r.status == Status.RECONCILIADO:
                c["reconciliados"] += 1
            elif r.acao in (Acao.RESPONDER_TUTORIAL, Acao.RESPONDER_FORMS):
                c["respondidos"] += 1
            elif r.acao == Acao.ENCAMINHAR_MANUAL:
                c["encaminhados"] += 1
            elif r.acao == Acao.IGNORAR:
                c["ignorados"] += 1
        return c


class Robo:
    """Reúne as peças configuradas e executa ciclos."""

    def __init__(
        self,
        cfg: Config,
        caixa: CaixaEmail,
        classificador: Classificador,
        registro: Registro,
        tutoriais: RepositorioTutoriais,
        respostas: GeradorRespostas,
        fornecedores: ListaFornecedores,
        filtro_interno: Optional[FiltroInterno] = None,
        filtro_spam: Optional[FiltroSpam] = None,
        fonte_escritorios: Optional[Callable[[], MapaEscritorios]] = None,
    ):
        self.cfg = cfg
        self.caixa = caixa
        self.classificador = classificador
        self.registro = registro
        self.tutoriais = tutoriais
        self.respostas = respostas
        self.fornecedores = fornecedores
        self.envio_real = cfg.envio_real
        self.modo = "REAL" if self.envio_real else "SIMULACAO"
        self.destino_teste = cfg.destino_teste      # v0.3.0 – D02: todas as mensagens vão para o destino padrão
        # v0.3.0 – envio liberado por categoria (D10 – seção 6.7). Vazio = todas liberadas (v0.2.1)
        self.categorias: Dict[str, Dict] = dict(cfg.get("categorias", {}) or {})
        self.bloqueadas: Dict[str, str] = {}        # categoria → protocolo do "Tutorial errado" (T13)
        self.acao_manual = cfg.acao_manual
        self.permitidos = list(cfg.get("seguranca.destinatarios_permitidos", []) or [])
        self.cats = cfg.get("caixa.categorias_outlook", {}) or {}
        self.mover = bool(cfg.get("caixa.mover_apos_tratar", True))
        self.marcas_rpa = cfg.get("filtros.mensagens_do_rpa", {}) or {}
        self.filtro_interno = filtro_interno or FiltroInterno(
            cfg.get("filtros.dominios_internos", []) or [],
            [cfg.get("caixa.conta", ""), cfg.get("caixa.enviar_em_nome_de", "")],
        )
        self.filtro_spam = filtro_spam or FiltroSpam.de_config(cfg.get("filtros.spam", {}))
        # v0.3.0 – planilha de escritórios (lida a cada ciclo – seção 5.9)
        self.fonte_escritorios = fonte_escritorios
        self.escritorios: Optional[MapaEscritorios] = None
        # v0.3.0 – caixa pessoal (seção 6.1)
        self.marcar_nao_fornecedores = bool(cfg.get("caixa.marcar_nao_fornecedores", True))
        self.pular_ja_respondidos = bool(cfg.get("caixa.pular_ja_respondidos", False))

    # ---- envio por categoria (v0.3.0 – seção 6.7) ---------------------------- #
    @staticmethod
    def codigo_categoria(c: Classificacao) -> str:
        """Código da aba Categorias para a classificação (o manual se divide por motivo)."""
        if c.categoria != Categoria.MANUAL:
            return c.categoria
        return {MotivoManual.SAP: "MANUAL_SAP", MotivoManual.FORA_DO_ESCOPO: "MANUAL_FORA_ESCOPO"}.get(
            c.motivo_manual or "", "MANUAL")

    def categoria_liberada(self, codigo: str) -> bool:
        if not self.categorias:
            return True                                  # sem aba Categorias: comportamento da v0.2.1
        return bool((self.categorias.get(codigo) or {}).get("liberada", False))

    def _deve_enviar(self, codigo: str, r: Resultado) -> bool:
        """Envia só com modo REAL + categoria liberada + categoria não bloqueada (a trava vem depois)."""
        r.categoria_liberada = self.categoria_liberada(codigo) and codigo not in self.bloqueadas
        return bool(self.envio_real and r.categoria_liberada)

    def _aplicar_config_categoria(self, c: Classificacao) -> None:
        """Ativa = N ou Ação = MANUAL na aba Categorias → sempre análise manual."""
        conf = self.categorias.get(c.categoria) if c.categoria != Categoria.MANUAL else None
        if not conf or (conf.get("ativa", True) and str(conf.get("acao", "")).upper() != "MANUAL"):
            return
        c.detalhes.setdefault("categoria_sugerida", c.categoria)
        situacao = "desativada" if not conf.get("ativa", True) else "configurada como MANUAL"
        c.motivo = f"categoria {c.categoria} {situacao} na planilha | {c.motivo}"
        c.categoria, c.motivo_manual = Categoria.MANUAL, MotivoManual.CATEGORIA_DESABILITADA

    def eh_fornecedor(self, remetente: str) -> bool:
        """Remetente que o robô pode tratar: não interno e (se exigido) na lista de fornecedores."""
        if not remetente or self.filtro_interno.interno(remetente)[0]:
            return False
        return (not self.cfg.get("filtros.validar_fornecedor", True)) or self.fornecedores.conhecido(remetente)

    def ler_pendentes(self, lote: int) -> List[EmailRecebido]:
        """Com ``marcar_nao_fornecedores = N``, o filtro de remetente roda na varredura (antes do lote)."""
        if self.marcar_nao_fornecedores:
            return self.caixa.ler_pendentes(lote)
        return self.caixa.ler_pendentes(lote, aceitar_remetente=self.eh_fornecedor)

    def atualizar_escritorios(self) -> None:
        """Relê a planilha de escritórios e troca a lista de fornecedores. Erro → ``ErroEscritorios``."""
        if self.fonte_escritorios is None:
            return
        self.escritorios = self.fonte_escritorios()
        self.fornecedores = self.escritorios.lista_fornecedores()
        for aviso in self.escritorios.avisos:
            log.warning("Planilha de escritórios: %s", aviso)

    # ------------------------------------------------------------------ #
    def executar_ciclo(self) -> ResumoCiclo:
        resumo = ResumoCiclo(ciclo_id=f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}", modo=self.modo)
        lote = int(self.cfg.get("caixa.lote_maximo", 50))
        log.info("Ciclo %s iniciado | perfil=%s | modo=%s | lote=%d", resumo.ciclo_id, self.cfg.perfil, self.modo, lote)
        try:
            self.atualizar_escritorios()
        except ErroEscritorios as erro:              # seção 5.9: sem a planilha, o ciclo não roda
            resumo.falha = str(erro)
            log.error("Ciclo %s não executado: %s", resumo.ciclo_id, erro)
            self._avisar_falha_ciclo(str(erro))
            self.registro.gravar_ciclo(resumo.ciclo_id, self.modo, resumo.inicio, resumo.contagem(),
                                       obs=f"NÃO EXECUTADO: {erro}"[:500])
            return resumo
        if hasattr(self.classificador, "iniciar_ciclo"):
            self.classificador.iniciar_ciclo()          # zera o contador de falhas da IA (RNF-IA03)
        emails = self.ler_pendentes(lote)
        if not self.marcar_nao_fornecedores:
            resumo.nao_fornecedores = int(getattr(self.caixa, "descartados", 0) or 0)
            if resumo.nao_fornecedores:
                log.info("%d e-mail(s) de não fornecedores deixados sem alteração", resumo.nao_fornecedores)
        log.info("%d e-mail(s) pendente(s)", len(emails))
        for email in emails:
            inicio = time.perf_counter()
            r = self._tratar_com_protecao(email)
            r.duracao_ms = int((time.perf_counter() - inicio) * 1000)
            try:
                self.registro.gravar(r, resumo.ciclo_id, self.modo)
            except Exception:  # o registro não pode derrubar o ciclo
                log.exception("Falha ao gravar o registro do e-mail %s", email.id_mensagem)
            log.info(
                "[%s] %s | %s | %s | %s → %s %s",
                protocolo(email), email.remetente or "-", (email.assunto or "")[:60],
                r.classificacao.categoria if r.classificacao else "-", r.acao, r.status,
                f"| erro: {r.erro}" if r.erro else "",
            )
            resumo.resultados.append(r)
        self.registro.gravar_ciclo(resumo.ciclo_id, self.modo, resumo.inicio, resumo.contagem(),
                                   nao_fornecedores=resumo.nao_fornecedores)
        log.info("Ciclo %s concluído: %s | não fornecedores: %d", resumo.ciclo_id, resumo.contagem(),
                 resumo.nao_fornecedores)
        return resumo

    # ------------------------------------------------------------------ #
    def _tratar_com_protecao(self, email: EmailRecebido) -> Resultado:
        r = Resultado(email=email)
        try:
            anterior = self.registro.estado(email.chave)
            if anterior is not None and self._deve_reconciliar(anterior):
                return self._reconciliar(email, anterior, r)
            if self.escritorios is not None:
                email.escritorio = self.escritorios.escritorio(email.remetente)
            extracao.processar(
                email, self.cfg.get("extracao", {}) or {}, self.cfg.get("filtros.assuntos_resposta_automatica", []),
                self.marcas_rpa,
            )
            self._tratar(email, r)
        except Exception as erro:  # RNF02
            log.error("Erro ao tratar %s: %s", email.id_mensagem, erro)
            log.debug("Detalhe do erro", exc_info=True)
            self._registrar_erro(email, r, erro)
        return r

    @staticmethod
    def _deve_reconciliar(anterior) -> bool:
        if anterior["acao_executada"]:
            return True                       # já respondeu/encaminhou: nunca repetir
        if anterior["status"] == Status.EM_ANDAMENTO:
            return True                       # ciclo anterior caiu no meio: não arriscar
        if anterior["status"] == Status.IGNORADO:
            return True
        return False                          # ERRO sem ação executada: pode tentar de novo

    def _reconciliar(self, email: EmailRecebido, anterior, r: Resultado) -> Resultado:
        r.acao = anterior["acao"] or Acao.NENHUMA
        if anterior["status"] == Status.EM_ANDAMENTO and not anterior["acao_executada"]:
            raise RuntimeError(
                "Execução anterior foi interrompida durante o tratamento deste e-mail. "
                "Verifique em Itens Enviados/Rascunhos se a resposta saiu antes de reprocessar."
            )
        destino = anterior["destino"]
        if destino not in (self.cfg.get("caixa.pastas_destino", {}) or {}):
            destino = Destino.ERRO
        # Modo sem mover: a categoria é o que marca o e-mail como tratado. Sem ela,
        # ele voltaria a ser lido a cada ciclo.
        categoria = None if self.mover else self._categoria_reconciliacao(anterior, destino)
        self.caixa.finalizar(email, destino, categoria)
        r.status = Status.RECONCILIADO
        r.destino = destino if self.mover else ""
        acao = f"apenas movido para {destino}" if self.mover else "apenas marcado com a categoria do RPA"
        r.erro = f"já tratado antes (status {anterior['status']}); {acao}"
        log.warning("[%s] e-mail já tratado reapareceu na entrada – %s", protocolo(email), acao)
        return r

    def _categoria_reconciliacao(self, anterior, destino: str) -> Optional[str]:
        if anterior["status"] == Status.SIMULADO:
            return self.cats.get("simulado")
        chave = {Destino.RESPONDIDOS: "respondido", Destino.ENCAMINHADOS: "encaminhado",
                 Destino.IGNORADOS: "ignorado"}.get(destino, "erro")
        return self.cats.get(chave)

    # ------------------------------------------------------------------ #
    def _tratar(self, email: EmailRecebido, r: Resultado) -> None:
        # 0. o analista já respondeu ou encaminhou (v0.3.0 – seção 6.1): só a categoria
        if self.pular_ja_respondidos and email.ultimo_verbo in VERBOS_JA_TRATADO:
            r.acao, r.destino = Acao.IGNORAR, Destino.IGNORADOS
            r.motivo_ignorado = f"{MotivoIgnorado.JA_TRATADO_PELO_ANALISTA}: última ação no Outlook = {email.ultimo_verbo}"
            self.registro.marcar_em_andamento(email.chave, protocolo(email), r.acao)
            self.caixa.finalizar(email, Destino.IGNORADOS, self.cats.get("ignorado"), marcar_lido=False)
            r.status = Status.IGNORADO
            return

        # 1. resposta automática (RF03)
        if email.resposta_automatica:
            r.acao, r.destino = Acao.IGNORAR, Destino.IGNORADOS
            self.registro.marcar_em_andamento(email.chave, protocolo(email), r.acao)
            self.caixa.finalizar(email, Destino.IGNORADOS, self.cats.get("ignorado"))
            r.status = Status.IGNORADO
            return

        # 1a. mensagem gerada pelo próprio RPA que voltou para a caixa (v0.2.1 – evita laço)
        if email.gerada_pelo_rpa:
            self._ignorar(email, r, MotivoIgnorado.PROPRIO_RPA, email.motivo_gerada_pelo_rpa)
            return

        # 1b. remetente interno e spam (E2 – RN2.2, RN2.3): Ignorados, sem chamar a IA
        interno, detalhe = self.filtro_interno.interno(email.remetente)
        if interno:
            self._ignorar(email, r, MotivoIgnorado.INTERNO, detalhe)
            return
        spam, detalhe = self.filtro_spam.spam(email.cabecalhos)
        if spam:
            self._ignorar(email, r, MotivoIgnorado.SPAM, detalhe)
            return

        # 2. remetente fora da lista (RF03)
        if self.cfg.get("filtros.validar_fornecedor", True) and not self.fornecedores.conhecido(email.remetente):
            c = Classificacao(Categoria.MANUAL, 0.0, "remetente fora da lista de fornecedores",
                              motivo_manual=MotivoManual.FORA_DA_LISTA)
        else:
            # 3. classificação (RF04). O e-mail inteiro vai junto (lacuna R1)
            c = self.classificador.classificar(email.assunto, email.corpo_limpo, email=email)
            c.detalhes.setdefault("classificador", self.cfg.classificador)
            self._apos_classificacao_ia(email, c)
            if c.categoria != Categoria.MANUAL and c.confianca < self.cfg.limite_confianca:
                c.detalhes.setdefault("categoria_sugerida", c.categoria)
                c.motivo = f"confiança {c.confianca:.2f} < limite {self.cfg.limite_confianca:.2f} | {c.motivo}"
                c.categoria, c.motivo_manual = Categoria.MANUAL, MotivoManual.BAIXA_CONFIANCA
            self._aplicar_config_categoria(c)
            if c.categoria == Categoria.FORMS_PO and not str(self.cfg.get("respostas.link_forms_po", "") or "").strip():
                # seção 5.6: sem o link do Forms, a categoria FORMS_PO é tratada como MANUAL
                c.detalhes.setdefault("categoria_sugerida", c.categoria)
                c.motivo = f"link do formulário vazio na aba Tutoriais | {c.motivo}"
                c.categoria, c.motivo_manual = Categoria.MANUAL, MotivoManual.SEM_RESPOSTA_PADRAO
        r.classificacao = c

        # 4. ação
        if c.categoria in Categoria.TUTORIAIS:
            self._responder_tutorial(email, c, r)
        elif c.categoria == Categoria.FORMS_PO:
            self._responder_forms(email, r)
        else:
            self._encaminhar_manual(email, c, r)

    # ---- filtros e IA (v0.2.0) -------------------------------------------- #
    def _ignorar(self, email: EmailRecebido, r: Resultado, motivo: str, detalhe: str) -> None:
        r.acao, r.destino = Acao.IGNORAR, Destino.IGNORADOS
        r.motivo_ignorado = f"{motivo}: {detalhe}" if detalhe else motivo
        self.registro.marcar_em_andamento(email.chave, protocolo(email), r.acao)
        self.caixa.finalizar(email, Destino.IGNORADOS, self.cats.get("ignorado"))
        r.status = Status.IGNORADO

    def _apos_classificacao_ia(self, email: EmailRecebido, c: Classificacao) -> None:
        """Log técnico da IA (RNF-IA01, sem corpo/prompt/resumo) e alerta de falhas seguidas."""
        d = c.detalhes
        if d.get("classificador") != "ia":
            return
        log.info(
            "[%s] IA | categoria %s | confiança %.2f | regra %s | ação %s | motivo %s | latência %s ms | "
            "tentativas %s | tokens %s",
            protocolo(email), d.get("categoria_docx") or "-", c.confianca, d.get("regra_decisao"),
            c.categoria, c.motivo_manual or "-", d.get("latencia_ms"), d.get("tentativas"), d.get("tokens"),
        )
        consumir = getattr(self.classificador, "consumir_alerta", None)
        falhas = consumir() if callable(consumir) else None
        if falhas:
            self._avisar_ia_indisponivel(falhas)

    def _avisar_ia_indisponivel(self, falhas: int) -> None:
        para = list(self.cfg.get("destinatarios.avisos_erro", []) or [])
        if not para:
            log.warning("destinatarios.avisos_erro vazio – aviso de IA indisponível não enviado")
            return
        try:
            self._verificar_destinatarios(para)
            corpo = self.respostas.aviso_ia_indisponivel(falhas)
            assunto = str(self.cfg.get("classificacao.ia.assunto_alerta", "[RPA Dúvidas Financeiras] IA indisponível"))
            self.caixa.enviar_novo(para, assunto, corpo, enviar=self.envio_real)
        except Exception:
            log.exception("Falha ao enviar o aviso de IA indisponível")

    def _avisar_falha_ciclo(self, mensagem: str) -> None:
        """Aviso de ciclo não executado – no máximo um por dia para o mesmo erro."""
        para = list(self.cfg.get("destinatarios.avisos_erro", []) or [])
        if not para:
            log.warning("destinatarios.avisos_erro vazio – aviso de ciclo não executado não enviado")
            return
        chave = f"falha_ciclo:{datetime.now():%Y-%m-%d}:{mensagem[:200]}"
        try:
            if self.registro.ja_avisado(chave):
                return
            self._verificar_destinatarios(para)
            corpo = self.respostas.aviso_falha_ciclo(mensagem)
            self.caixa.enviar_novo(para, "[RPA Dúvidas Financeiras] Ciclo não executado", corpo, enviar=self.envio_real)
            self.registro.registrar_aviso(chave)
        except Exception:
            log.exception("Falha ao enviar o aviso de ciclo não executado")

    # ---- ações ----------------------------------------------------------- #
    def _verificar_destinatarios(self, enderecos: List[str]) -> None:
        bloqueados = [e for e in enderecos if not extracao.endereco_permitido(e, self.permitidos)]
        if bloqueados:
            raise ErroSeguranca(
                f"Destinatário(s) fora de seguranca.destinatarios_permitidos no ambiente "
                f"'{self.cfg.ambiente}': {', '.join(bloqueados)}"
            )

    def _finalizar_ok(self, email: EmailRecebido, destino: str, categoria_chave: str, r: Resultado,
                      enviado: Optional[bool] = None) -> None:
        """v0.3.0: o status é calculado POR E-MAIL (seção 6.7): CONCLUIDO se saiu, SIMULADO se é rascunho."""
        enviado = self.envio_real if enviado is None else enviado
        r.destino = destino
        categoria = self.cats.get(categoria_chave) if enviado else self.cats.get("simulado")
        self.caixa.finalizar(email, destino, categoria)
        r.status = Status.CONCLUIDO if enviado else Status.SIMULADO

    def _destinatarios_resposta(self, email: EmailRecebido, r: Resultado) -> List[str]:
        """Preenche ``r.destinatarios`` / ``r.destinatario_original`` e devolve o CC a usar."""
        responder_todos = bool(self.cfg.get("respostas.responder_todos", False))
        cc = list(self.cfg.get("destinatarios.analistas_cc", []) or [])
        originais = list(dict.fromkeys(self.caixa.destinatarios_resposta(email, responder_todos)))
        if self.destino_teste:
            r.destinatario_original = "; ".join(originais)
            r.destinatarios = [self.destino_teste]
            return []                                   # seção 6.2: CC ignorado no envio de teste
        r.destinatarios = list(dict.fromkeys(originais + cc))
        return cc

    def _responder(self, email: EmailRecebido, corpo: str, anexos, r: Resultado, cc: Optional[List[str]] = None,
                   prefixo_assunto: str = "", codigo: str = "") -> None:
        responder_todos = bool(self.cfg.get("respostas.responder_todos", False))
        enviar = self._deve_enviar(codigo, r) if codigo else self.envio_real
        if cc is None:
            cc = self._destinatarios_resposta(email, r)
        self._verificar_destinatarios(r.destinatarios)
        self.registro.marcar_em_andamento(email.chave, protocolo(email), r.acao)
        extra = {}
        if self.destino_teste:
            extra["redirecionar_para"] = self.destino_teste
        if prefixo_assunto:
            extra["prefixo_assunto"] = prefixo_assunto
        r.id_mensagem_gerada = self.caixa.responder(
            email, corpo, anexos=anexos, cc=cc, responder_todos=responder_todos, enviar=enviar, **extra
        )
        r.enviado = enviar
        self.registro.marcar_acao_executada(email.chave)
        self._finalizar_ok(email, Destino.RESPONDIDOS, "respondido", r, enviar)

    def _responder_tutorial(self, email: EmailRecebido, c: Classificacao, r: Resultado) -> None:
        r.acao = Acao.RESPONDER_TUTORIAL
        tutorial = self.tutoriais.localizar(c.categoria)          # RF06: falha → Erro
        r.arquivo_enviado = tutorial.nome
        cc = self._destinatarios_resposta(email, r)
        corpo = self.respostas.resposta(
            email, c.categoria, nome_arquivo=tutorial.nome, descricao_tutorial=tutorial.descricao,
            destinatario_original=r.destinatario_original,
        )
        self._responder(email, corpo, [tutorial.caminho], r, cc, codigo=c.categoria)

    def _responder_forms(self, email: EmailRecebido, r: Resultado) -> None:
        r.acao = Acao.RESPONDER_FORMS
        r.arquivo_enviado = "(link do Forms)"
        cc = self._destinatarios_resposta(email, r)
        corpo = self.respostas.resposta(email, Categoria.FORMS_PO, destinatario_original=r.destinatario_original)
        self._responder(email, corpo, [], r, cc, codigo=Categoria.FORMS_PO)

    def _encaminhar_manual(self, email: EmailRecebido, c: Classificacao, r: Resultado) -> None:
        r.acao = Acao.ENCAMINHAR_MANUAL
        motivo = c.motivo_manual or MotivoManual.NAO_IDENTIFICADO
        rotulo = (self.cfg.get("respostas.rotulos_motivo_manual", {}) or {}).get(motivo, motivo)
        prefixo = str(self.cfg.get("respostas.prefixo_manual", "[MANUAL – {motivo}]")).format(motivo=rotulo)
        codigo = self.codigo_categoria(c)
        if self.acao_manual == "CATEGORIZAR":
            # v0.3.0 – caixa pessoal: o caso manual fica na entrada com "RPA - Encaminhado", sem mensagem nova
            r.categoria_liberada = self.categoria_liberada(codigo)
            r.enviado = False
            self.registro.marcar_em_andamento(email.chave, protocolo(email), r.acao)
            self.registro.marcar_acao_executada(email.chave)
            r.destino = Destino.ENCAMINHADOS
            self.caixa.finalizar(email, Destino.ENCAMINHADOS, self.cats.get("encaminhado"))
            r.status = Status.CONCLUIDO
            return
        para = self.cfg.destino_manual(motivo)
        if self.destino_teste:                          # seção 6.2: encaminhamento também só ao destino padrão
            r.destinatario_original = "; ".join(para)
            para = [self.destino_teste]
        if not para:
            raise RuntimeError("Nenhum destinatário de análise manual configurado")
        r.destinatarios = para
        self._verificar_destinatarios(para)
        nota = self.respostas.nota_manual(email, c, rotulo)
        self.registro.marcar_em_andamento(email.chave, protocolo(email), r.acao)
        enviar = self._deve_enviar(codigo, r)
        r.id_mensagem_gerada = self.caixa.encaminhar(email, para, prefixo, nota, enviar=enviar)
        r.enviado = enviar
        self.registro.marcar_acao_executada(email.chave)
        self._finalizar_ok(email, Destino.ENCAMINHADOS, "encaminhado", r, enviar)

    # ---- erro (RNF02) ---------------------------------------------------- #
    def _registrar_erro(self, email: EmailRecebido, r: Resultado, erro: Exception) -> None:
        r.status = Status.ERRO
        r.erro = f"{type(erro).__name__}: {erro}"
        r.destino = Destino.ERRO if self.mover else ""
        try:
            self.caixa.finalizar(email, Destino.ERRO, self.cats.get("erro"))
        except Exception:
            log.exception("Não foi possível mover %s para Erro – permanece na entrada", email.id_mensagem)
            r.destino = ""
            r.erro += " | e-mail NÃO movido para Erro (permanece na entrada)"
        self._avisar_erro(email, r)

    def _avisar_erro(self, email: EmailRecebido, r: Resultado) -> None:
        para = list(self.cfg.get("destinatarios.avisos_erro", []) or [])
        if not para:
            log.warning("destinatarios.avisos_erro vazio – aviso de erro não enviado")
            return
        try:
            self._verificar_destinatarios(para)
            corpo = self.respostas.aviso_erro(
                email, r.erro, r.classificacao.categoria if r.classificacao else "",
                str(self.cfg.get("caixa.pastas_destino.erro", "Erro")),
                movido=self.mover and bool(r.destino),
            )
            assunto = f"[RPA Dúvidas Financeiras] Erro no tratamento – protocolo {protocolo(email)}"
            self.caixa.enviar_novo(para, assunto, corpo, enviar=self.envio_real)
        except Exception:
            log.exception("Falha ao enviar o aviso de erro de %s", email.id_mensagem)
