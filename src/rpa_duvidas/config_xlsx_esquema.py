"""Estrutura do ``configuracao.xlsx`` (v0.3.0 – seção 5 da especificação técnica).

Fonte única do layout da planilha: o gerador do modelo
(``scripts/gerar_modelo_config.py``) e o leitor (``config_xlsx.py``) usam as
mesmas definições de abas, colunas, chaves e listas. Mudou o layout? Mude aqui
e suba ``VERSAO_MODELO``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

VERSAO_MODELO = "0.3.0"
PLACEHOLDER = "A_PREENCHER"

# Abas, na ordem em que aparecem no arquivo
ABA_LEIAME = "LEIA-ME"
ABA_GERAL = "Geral"
ABA_CATEGORIAS = "Categorias"
ABA_PALAVRAS = "Palavras_chave"
ABA_TEXTOS = "Textos"
ABA_TUTORIAIS = "Tutoriais"
ABA_DESTINATARIOS = "Destinatarios"
ABA_FILTROS = "Filtros"
ABA_LISTAS = "Listas"
ABAS = [ABA_LEIAME, ABA_GERAL, ABA_CATEGORIAS, ABA_PALAVRAS, ABA_TEXTOS, ABA_TUTORIAIS,
        ABA_DESTINATARIOS, ABA_FILTROS, ABA_LISTAS]
ABAS_PROTEGIDAS = [ABA_GERAL, ABA_FILTROS, ABA_LISTAS]   # senha da BT (seção 5)

# --------------------------------------------------------------------------- #
# listas fechadas (aba Listas)
# --------------------------------------------------------------------------- #
SIM_NAO = ["S", "N"]
CODIGOS_CATEGORIA = ["TUT_CONNECT", "TUT_UPLOAD_NF", "TUT_REEMBOLSO", "TUT_CADASTRO", "FORMS_PO",
                     "MANUAL", "MANUAL_SAP", "MANUAL_FORA_ESCOPO"]
CODIGOS_TUTORIAL = ["TUT_CONNECT", "TUT_UPLOAD_NF", "TUT_REEMBOLSO", "TUT_CADASTRO"]
ACOES = ["RESPONDER_TUTORIAL", "RESPONDER_FORMS", "RESPONDER_TEXTO", "MANUAL"]
# Ações aceitas por código (decisão da Etapa 1, pergunta 4)
ACOES_POR_CODIGO: Dict[str, List[str]] = {
    **{c: ["RESPONDER_TUTORIAL", "RESPONDER_TEXTO", "MANUAL"] for c in CODIGOS_TUTORIAL},
    "FORMS_PO": ["RESPONDER_FORMS", "RESPONDER_TEXTO", "MANUAL"],
    "MANUAL": ["MANUAL"], "MANUAL_SAP": ["MANUAL"], "MANUAL_FORA_ESCOPO": ["MANUAL"],
}
# Categorias que podem ter termos na aba Palavras_chave (as do classificador)
CATEGORIAS_TERMOS = CODIGOS_TUTORIAL + ["FORMS_PO", "MANUAL_SAP", "MANUAL_FORA_ESCOPO"]
DESTINO_RESPOSTAS = ["TESTE"]                 # FORNECEDOR fica reservado para a próxima etapa
DESTINO_RESERVADO = ["FORNECEDOR"]
MODOS_EXECUCAO = ["SIMULACAO", "REAL"]
ACOES_MANUAL = ["CATEGORIZAR", "ENCAMINHAR"]
NIVEIS_LOG = ["INFO", "DEBUG"]
TIPOS_DESTINATARIO = ["AVISO_ERRO", "CC", "MANUAL_PADRAO", "MANUAL_SAP", "MANUAL_NAO_IDENTIFICADO"]
TIPOS_FILTRO = ["DOMINIO_INTERNO", "ASSUNTO_RESPOSTA_AUTOMATICA", "MARCADOR_ASSUNTO_RPA", "MARCADOR_TEXTO_RPA"]
CODIGOS_TEXTO_FIXOS = ["AVISO_AUTOMATICO", "ASSINATURA", "NOTA_MANUAL"]
CAMPOS_TEXTO = ["nome_fornecedor", "protocolo", "nome_arquivo", "link_formulario", "analista", "data"]

LISTAS: Dict[str, List[str]] = {
    "S/N": SIM_NAO,
    "Códigos de categoria": CODIGOS_CATEGORIA,
    "Ações": ACOES,
    "Destino das respostas": DESTINO_RESPOSTAS,
    "Modo de execução": MODOS_EXECUCAO,
    "Ação manual": ACOES_MANUAL,
    "Nível de log": NIVEIS_LOG,
    "Tipos de destinatário": TIPOS_DESTINATARIO,
    "Tipos de filtro": TIPOS_FILTRO,
}

TEXTO_AVISO_AUTOMATICO = (
    "Esta é uma resposta automática do time financeiro. Se a sua dúvida não foi resolvida, "
    "responda este e-mail que um analista dará continuidade."
)
TEXTO_ASSINATURA = "{analista}\nEquipe Financeiro – Contas a Pagar"


# --------------------------------------------------------------------------- #
# aba Geral (seção 5.2)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CampoGeral:
    chave: str
    tipo: str                 # email | texto | lista | inteiro | decimal | sn | data | caminho
    destino: str              # chave do dicionário de configuração
    obrigatoria: bool
    descricao: str
    lista: Optional[str] = None       # nome da lista (aba Listas) para tipo "lista"/"sn"
    padrao_doc: str = ""              # padrão exibido na descrição


CAMPOS_GERAL: List[CampoGeral] = [
    CampoGeral("email_caixa_entrada", "email", "caixa.conta", True,
               "Conta do Outlook desta máquina (a caixa pessoal lida pelo robô)."),
    CampoGeral("email_destino_padrao", "email", "execucao.email_destino_padrao", True,
               "Recebe TODAS as respostas no lugar do fornecedor. Diferente do e-mail da caixa."),
    CampoGeral("destino_respostas", "lista", "execucao.destino_respostas", True,
               "Na v0.3.0 só TESTE (FORNECEDOR fica para a próxima etapa).", "Destino das respostas", "TESTE"),
    CampoGeral("modo_execucao", "lista", "execucao.envio_real", True,
               "SIMULACAO gera só rascunhos. REAL envia, só nas categorias liberadas e só ao destino padrão.",
               "Modo de execução", "SIMULACAO"),
    CampoGeral("pasta_entrada", "texto", "caixa.pasta_entrada", False,
               "Pasta lida. @inbox = Caixa de Entrada.", padrao_doc="@inbox"),
    CampoGeral("recebidos_desde", "data", "caixa.recebidos_desde", True,
               "Ignora e-mails anteriores (use a data da instalação)."),
    CampoGeral("filtro_assunto", "texto", "caixa.filtro_assunto", False,
               "Só assuntos que contêm o texto. Vazio na calibração."),
    CampoGeral("lote_maximo", "inteiro", "caixa.lote_maximo", False, "E-mails tratados por ciclo.", padrao_doc="20"),
    CampoGeral("max_varredura", "inteiro", "caixa.max_varredura", False,
               "Quantos e-mails recentes examinar por ciclo.", padrao_doc="300"),
    CampoGeral("intervalo_minutos", "inteiro", "execucao.intervalo_minutos", False,
               "Intervalo do modo contínuo e do Agendador.", padrao_doc="15"),
    CampoGeral("mover_apos_tratar", "sn", "caixa.mover_apos_tratar", False,
               "N = o e-mail fica na Caixa de Entrada com a categoria RPA.", "S/N", "N"),
    CampoGeral("marcar_nao_fornecedores", "sn", "caixa.marcar_nao_fornecedores", False,
               "N = e-mails que não são de fornecedor não são alterados.", "S/N", "N"),
    CampoGeral("pular_ja_respondidos", "sn", "caixa.pular_ja_respondidos", False,
               "S = ignora e-mails que o analista já respondeu ou encaminhou.", "S/N", "S"),
    CampoGeral("acao_manual", "lista", "destinatarios.acao_manual", False,
               "CATEGORIZAR = o caso manual fica na Caixa de Entrada com a categoria RPA - Encaminhado.",
               "Ação manual", "CATEGORIZAR"),
    CampoGeral("limite_confianca", "decimal", "classificacao.limite_confianca", False,
               "Abaixo disso, vai para análise manual (0 a 1).", padrao_doc="0,70"),
    CampoGeral("ia_ligada", "sn", "classificacao.tipo", False,
               "Na v0.3.0 a IA fica desligada (S é recusado).", "S/N", "N"),
    CampoGeral("caminho_planilha_escritorios", "caminho", "escritorios.arquivo", True,
               "Planilha de domínios dos escritórios (SharePoint sincronizado no Explorer)."),
    CampoGeral("aba_planilha_escritorios", "texto", "escritorios.aba", False,
               "Aba da planilha de escritórios. Vazio = 1ª aba."),
    CampoGeral("coluna_dominio", "texto", "escritorios.coluna_dominio", True,
               "Nome da coluna com o domínio (ex.: Domínio).", padrao_doc="Domínio"),
    CampoGeral("coluna_escritorio", "texto", "escritorios.coluna_escritorio", True,
               "Nome da coluna com o escritório (ex.: Escritório).", padrao_doc="Escritório"),
    CampoGeral("caminho_arquivo_emails", "caminho", "arquivamento.raiz", True,
               "Pasta onde os e-mails tratados são arquivados em .msg (ex.: arquivo\\).", padrao_doc="arquivo\\"),
    CampoGeral("caminho_planilha_controle", "caminho", "registro.planilha_controle", False,
               "Planilha de controle (pode ficar no SharePoint).", padrao_doc="dados\\registro_controle.xlsx"),
    CampoGeral("nome_analista", "texto", "respostas.contexto.analista", True,
               "Nome usado na assinatura e no aviso de resposta automática."),
    CampoGeral("nivel_log", "lista", "registro.nivel_log", False, "INFO ou DEBUG.", "Nível de log", "INFO"),
]
CAMPOS_GERAL_POR_CHAVE = {c.chave: c for c in CAMPOS_GERAL}

# --------------------------------------------------------------------------- #
# colunas das abas em tabela (linha de cabeçalho; leitura pelo nome)
# --------------------------------------------------------------------------- #
COLUNAS: Dict[str, List[str]] = {
    ABA_GERAL: ["Chave", "Valor", "Descrição"],
    ABA_CATEGORIAS: ["Código", "Nome", "Ação", "Ativa", "Liberada para envio", "Data da liberação", "Código do texto"],
    ABA_PALAVRAS: ["Categoria", "Termo", "Peso", "Ativo", "Origem"],
    ABA_TEXTOS: ["Código", "Assunto (prefixo)", "Corpo"],
    ABA_TUTORIAIS: ["Categoria", "Caminho do arquivo", "Link do formulário", "Limite (MB)"],
    ABA_DESTINATARIOS: ["Tipo", "E-mail"],
    ABA_FILTROS: ["Tipo", "Valor", "Ativo"],
}
# Palavras_chave: parâmetros no topo (linhas 1 e 2) e cabeçalho na linha 4 (decisão da Etapa 1, pergunta 5)
PARAMETROS_PALAVRAS = ["peso_assunto", "saturacao"]
LINHA_CABECALHO_PALAVRAS = 4

NOMES_CATEGORIA: Dict[str, str] = {
    "TUT_CONNECT": "Acesso ao Connect",
    "TUT_UPLOAD_NF": "Upload e consulta de NF",
    "TUT_REEMBOLSO": "Reembolso",
    "TUT_CADASTRO": "Atualização de cadastro",
    "FORMS_PO": "Pedido de compra (Forms)",
    "MANUAL": "Análise manual",
    "MANUAL_SAP": "Depende de consulta no SAP",
    "MANUAL_FORA_ESCOPO": "Fora do escopo",
}
ACAO_PADRAO: Dict[str, str] = {
    **{c: "RESPONDER_TUTORIAL" for c in CODIGOS_TUTORIAL},
    "FORMS_PO": "RESPONDER_FORMS", "MANUAL": "MANUAL", "MANUAL_SAP": "MANUAL", "MANUAL_FORA_ESCOPO": "MANUAL",
}

# Valores aceitos como S/N (seção 4.2)
VERDADEIROS = {"s", "sim"}
FALSOS = {"n", "nao", "não"}


def lista_para_validacao(nome: str) -> Tuple[int, int]:
    """(coluna, quantidade) da lista ``nome`` na aba Listas (1 lista por coluna, a partir da linha 2)."""
    nomes = list(LISTAS)
    return nomes.index(nome) + 1, len(LISTAS[nome])


def valor_padrao_vazio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())
