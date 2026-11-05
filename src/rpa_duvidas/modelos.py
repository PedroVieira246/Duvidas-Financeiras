"""Estruturas de dados compartilhadas por todos os módulos (F02).

Nenhum módulo de negócio conhece o Outlook: tudo circula como
``EmailRecebido`` → ``Classificacao`` → ``Resultado``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class Categoria:
    """Categorias do MVP (seção 1 da especificação)."""

    TUT_CONNECT = "TUT_CONNECT"
    TUT_UPLOAD_NF = "TUT_UPLOAD_NF"
    TUT_REEMBOLSO = "TUT_REEMBOLSO"
    TUT_CADASTRO = "TUT_CADASTRO"
    FORMS_PO = "FORMS_PO"
    MANUAL = "MANUAL"

    TUTORIAIS = (TUT_CONNECT, TUT_UPLOAD_NF, TUT_REEMBOLSO, TUT_CADASTRO)
    RESPONDIVEIS = TUTORIAIS + (FORMS_PO,)
    TODAS = RESPONDIVEIS + (MANUAL,)


class MotivoManual:
    """Motivos de encaminhamento para análise manual (RF08)."""

    SAP = "SAP"
    NAO_IDENTIFICADO = "NAO_IDENTIFICADO"
    BAIXA_CONFIANCA = "BAIXA_CONFIANCA"
    FORA_DA_LISTA = "FORA_DA_LISTA"
    FORA_DO_ESCOPO = "FORA_DO_ESCOPO"   # tema conhecido, mas fora do MVP (ex.: novo cadastro)
    # Classificação por IA (F08 – RN7.1 da especificação funcional de 22/10/2026)
    MULTIPLAS_DUVIDAS = "MULTIPLAS_DUVIDAS"            # D4: há dúvida secundária
    EXCECAO = "EXCECAO"                                # D5/D7: sinal de exceção ou IA sugere manual
    SEM_RESPOSTA_PADRAO = "SEM_RESPOSTA_PADRAO"        # D2: C07 (formulários)
    CATEGORIA_DESABILITADA = "CATEGORIA_DESABILITADA"  # D6: resposta automática desligada (ex.: C06)
    CATEGORIA_SEM_TUTORIAL = "CATEGORIA_SEM_TUTORIAL"  # E5: código sem mapeamento em categorias_ia.yaml
    IA_INDISPONIVEL = "IA_INDISPONIVEL"                # D1: falha/timeout depois das novas tentativas
    RESPOSTA_IA_INVALIDA = "RESPOSTA_IA_INVALIDA"      # D1: JSON inválido depois da correção

    TODOS = (
        SAP, NAO_IDENTIFICADO, BAIXA_CONFIANCA, FORA_DA_LISTA, FORA_DO_ESCOPO,
        MULTIPLAS_DUVIDAS, EXCECAO, SEM_RESPOSTA_PADRAO, CATEGORIA_DESABILITADA,
        CATEGORIA_SEM_TUTORIAL, IA_INDISPONIVEL, RESPOSTA_IA_INVALIDA,
    )


class MotivoIgnorado:
    """Motivos de e-mails enviados para Ignorados sem tratamento (E2)."""

    RESPOSTA_AUTOMATICA = "RESPOSTA_AUTOMATICA"
    INTERNO = "INTERNO"     # RN2.2: remetente interno (domínio da Companhia ou a própria caixa)
    SPAM = "SPAM"           # RN2.3: cabeçalho SCL do Exchange acima do limite
    PROPRIO_RPA = "PROPRIO_RPA"  # v0.2.1: resposta/encaminhamento/aviso gerado pelo próprio RPA (evita laço)
    JA_TRATADO_PELO_ANALISTA = "JA_TRATADO_PELO_ANALISTA"  # v0.3.0: o analista já respondeu/encaminhou (seção 6.1)


# v0.3.0 – PR_LAST_VERB_EXECUTED: 102 respondido, 103 responder a todos, 104 encaminhado
VERBOS_JA_TRATADO = (102, 103, 104)


class Acao:
    RESPONDER_TUTORIAL = "RESPONDER_TUTORIAL"
    RESPONDER_FORMS = "RESPONDER_FORMS"
    RESPONDER_TEXTO = "RESPONDER_TEXTO"   # v0.3.0: só o texto da aba Textos, sem anexo
    ENCAMINHAR_MANUAL = "ENCAMINHAR_MANUAL"
    IGNORAR = "IGNORAR"
    NENHUMA = "NENHUMA"


class Status:
    EM_ANDAMENTO = "EM_ANDAMENTO"   # gravado ANTES de enviar (RNF01)
    CONCLUIDO = "CONCLUIDO"         # envio real feito
    SIMULADO = "SIMULADO"           # rascunho gerado (RF11 / RNF08)
    IGNORADO = "IGNORADO"           # resposta automática
    ERRO = "ERRO"
    RECONCILIADO = "RECONCILIADO"   # já tratado antes; só foi tirado da entrada


class Destino:
    """Chaves de ``caixa.pastas_destino`` na configuração."""

    RESPONDIDOS = "respondidos"
    ENCAMINHADOS = "encaminhados"
    ERRO = "erro"
    IGNORADOS = "ignorados"


@dataclass
class EmailRecebido:
    """Um e-mail lido da caixa, já independente da tecnologia (RF02)."""

    id_mensagem: str                    # Internet Message-ID (ou EntryID)
    remetente: str                      # SMTP, minúsculas
    nome_remetente: str
    assunto: str
    corpo_html: str
    corpo_texto_bruto: str              # texto como veio, com histórico
    data_recebimento: Optional[datetime]
    tem_anexos: bool = False
    nomes_anexos: List[str] = field(default_factory=list)
    cabecalhos: Dict[str, str] = field(default_factory=dict)
    classe_mensagem: str = "IPM.Note"
    id_conversa: str = ""
    # Preenchidos pela extração (extracao.py)
    corpo_limpo: str = ""
    resposta_automatica: bool = False
    motivo_resposta_automatica: str = ""
    # Trecho do histórico citado (contexto para a IA), até extracao.limite_historico
    historico_resumido: str = ""
    # v0.2.1: mensagem gerada pelo próprio RPA (filtros.mensagens_do_rpa)
    gerada_pelo_rpa: bool = False
    motivo_gerada_pelo_rpa: str = ""
    # v0.3.0: escritório do remetente (planilha de escritórios – seção 6.3)
    escritorio: str = ""
    # v0.3.0: última ação do usuário no e-mail (PR_LAST_VERB_EXECUTED; 0 = nenhuma)
    ultimo_verbo: int = 0

    @property
    def chave(self) -> str:
        """Chave de idempotência."""
        return self.id_mensagem.strip().lower()


@dataclass
class Classificacao:
    """Saída de qualquer classificador (seção 4 da especificação)."""

    categoria: str
    confianca: float            # 0.0 a 1.0
    motivo: str                 # justificativa curta, vai para o registro
    motivo_manual: Optional[str] = None
    detalhes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Resultado:
    """O que aconteceu com um e-mail – vira uma linha no registro (RF10)."""

    email: EmailRecebido
    acao: str = Acao.NENHUMA
    status: str = Status.EM_ANDAMENTO
    destino: str = ""
    classificacao: Optional[Classificacao] = None
    arquivo_enviado: str = ""
    destinatarios: List[str] = field(default_factory=list)
    id_mensagem_gerada: str = ""
    erro: str = ""
    duracao_ms: int = 0
    motivo_ignorado: str = ""       # INTERNO / SPAM (E2); vazio nos demais casos
    # v0.3.0 – calibração
    destinatario_original: str = ""     # quem receberia no envio real (destino_respostas = TESTE)
    enviado: Optional[bool] = None      # a mensagem saiu (True) ou ficou em rascunho (False); None = sem mensagem
    categoria_liberada: Optional[bool] = None   # categoria liberada para envio na aba Categorias (D10)
