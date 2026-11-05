"""Gera o ``configuracao.xlsx`` a partir da configuração YAML (v0.3.0 – tarefa T02).

Dois usos:

* ``modelo="calibracao"``: o modelo entregue com o .exe. Os valores que só se
  conhecem na instalação ficam com ``A_PREENCHER`` (o ``verificar`` acusa erro
  até alguém preencher).
* ``modelo="perfil"``: migra o perfil carregado (ex.: ``dev``) para o xlsx,
  célula por célula. Serve para conferir que a planilha reproduz o YAML (T02/T03).

O layout vem de ``config_xlsx_esquema``.
"""
from __future__ import annotations

import glob
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config_xlsx_esquema as E
from .config import Config

COR_CABECALHO = "1F3864"
COR_PARAMETRO = "FFF2CC"


def _sn(valor: Any) -> str:
    return "S" if bool(valor) else "N"


def _data(valor: Any) -> Any:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str) and valor.strip():
        try:
            return datetime.strptime(valor.strip(), "%Y-%m-%d").date()
        except ValueError:
            return valor
    return None


# --------------------------------------------------------------------------- #
# valores de cada aba
# --------------------------------------------------------------------------- #
def _valores_geral(cfg: Config, modelo: str) -> Dict[str, Any]:
    if modelo == "calibracao":
        P = E.PLACEHOLDER
        return {
            "email_caixa_entrada": P, "email_destino_padrao": P, "destino_respostas": "TESTE",
            "modo_execucao": "SIMULACAO", "pasta_entrada": "@inbox", "recebidos_desde": P,
            "filtro_assunto": None, "lote_maximo": 20, "max_varredura": 300, "intervalo_minutos": 15,
            "mover_apos_tratar": "N", "marcar_nao_fornecedores": "N", "pular_ja_respondidos": "S",
            "acao_manual": "CATEGORIZAR", "limite_confianca": 0.70, "ia_ligada": "N",
            "caminho_planilha_escritorios": P, "aba_planilha_escritorios": None,
            "coluna_dominio": P, "coluna_escritorio": P, "caminho_arquivo_emails": P,
            "caminho_planilha_controle": "dados\\registro_controle.xlsx", "nome_analista": P, "nivel_log": "INFO",
        }
    valores: Dict[str, Any] = {}
    for campo in E.CAMPOS_GERAL:
        v = cfg.get(campo.destino)
        if campo.chave == "modo_execucao":
            v = "REAL" if cfg.envio_real else "SIMULACAO"
        elif campo.chave == "ia_ligada":
            v = "S" if cfg.classificador == "ia" else "N"
        elif campo.chave == "destino_respostas":
            v = v if v in E.DESTINO_RESPOSTAS else None       # FORNECEDOR não existe no xlsx: célula vazia
        elif campo.tipo == "sn":
            v = None if v is None else _sn(v)
        elif campo.tipo == "data":
            v = _data(v)
        elif campo.tipo == "lista" and v is not None and campo.lista and v not in E.LISTAS[campo.lista]:
            v = None
        if isinstance(v, str) and not v.strip():
            v = None
        valores[campo.chave] = v
    return valores


def _linhas_categorias(cfg: Config) -> List[List[Any]]:
    conf = cfg.get("categorias", {}) or {}
    linhas = []
    for cod in E.CODIGOS_CATEGORIA:
        c = conf.get(cod, {}) or {}
        linhas.append([
            cod, c.get("nome") or E.NOMES_CATEGORIA[cod], c.get("acao") or E.ACAO_PADRAO[cod],
            _sn(c.get("ativa", True)), _sn(c.get("liberada", False)), _data(c.get("data_liberacao")),
            c.get("codigo_texto") or None,
        ])
    return linhas


def _linhas_palavras(cfg: Config) -> (Dict[str, Any], List[List[Any]]):
    dados = cfg.yaml_referenciado("classificacao.arquivo_termos")
    params = {"peso_assunto": dados.get("peso_assunto", 2.0), "saturacao": dados.get("saturacao", 5.0)}
    linhas = []
    for cat, conf in (dados.get("categorias") or {}).items():
        for termo, peso in ((conf or {}).get("termos") or {}).items():
            linhas.append([cat, str(termo), peso, "S", "palavras_chave.yaml (v0.2.1)"])
    return params, linhas


def _linhas_textos(cfg: Config, modelo: str) -> List[List[Any]]:
    textos = cfg.get("respostas.textos", {}) or {}
    if textos:
        return [[cod, t.get("assunto_prefixo") or None, t.get("corpo", "")] for cod, t in textos.items()]
    if modelo == "calibracao":
        return [["AVISO_AUTOMATICO", None, E.TEXTO_AVISO_AUTOMATICO],
                ["ASSINATURA", None, E.TEXTO_ASSINATURA]]
    # migração de um perfil: reproduz o texto atual do _base.html.j2 e a assinatura do YAML
    return [["AVISO_AUTOMATICO", None, TEXTO_AVISO_V021],
            ["ASSINATURA", None, str(cfg.get("respostas.assinatura", "") or "")]]


TEXTO_AVISO_V021 = ("Se a sua dúvida não foi resolvida, basta responder a este e-mail que a nossa equipe "
                    "dará continuidade ao atendimento.")


def _linhas_tutoriais(cfg: Config, modelo: str) -> List[List[Any]]:
    dados = cfg.yaml_referenciado("tutoriais.arquivo")
    limite = dados.get("limite_anexo_mb", 20)
    cats = dados.get("categorias") or {}
    linhas = []
    for cod in E.CODIGOS_TUTORIAL:
        conf = cats.get(cod) or {}
        if modelo == "calibracao":
            caminho = E.PLACEHOLDER
        elif conf.get("caminho_arquivo"):
            caminho = conf["caminho_arquivo"]
        else:
            caminho = _resolver_glob(cfg, dados, conf)
        linhas.append([cod, caminho, None, conf.get("limite_mb", limite)])
    link = E.PLACEHOLDER if modelo == "calibracao" else cfg.get("respostas.link_forms_po", "")
    linhas.append(["FORMS_PO", None, link or None, None])
    return linhas


def _resolver_glob(cfg: Config, dados: Dict, conf: Dict) -> Optional[str]:
    """Modo antigo (raiz + pasta + padrão) → caminho completo do arquivo escolhido hoje."""
    if not conf:
        return None
    raiz_bruta = str(dados.get("raiz", ""))
    pasta = cfg.caminho(raiz_bruta, eh_valor=True) / str(conf.get("pasta", ""))
    candidatos = [Path(p) for p in glob.glob(str(pasta / str(conf.get("padrao", "*"))))
                  if Path(p).is_file() and not Path(p).name.startswith("~$")]
    if not candidatos:
        return None
    escolhido = max(candidatos, key=lambda p: p.stat().st_mtime)
    try:  # mantém relativo à raiz do projeto quando der (portável entre máquinas)
        return str(Path(raiz_bruta) / str(conf.get("pasta", "")) / escolhido.name).replace("\\", "/")
    except Exception:
        return str(escolhido)


def _linhas_destinatarios(cfg: Config, modelo: str) -> List[List[Any]]:
    if modelo == "calibracao":
        return [["AVISO_ERRO", E.PLACEHOLDER]]
    linhas = [["AVISO_ERRO", e] for e in cfg.get("destinatarios.avisos_erro", []) or []]
    linhas += [["CC", e] for e in cfg.get("destinatarios.analistas_cc", []) or []]
    linhas += [["MANUAL_PADRAO", e] for e in cfg.get("destinatarios.analise_manual.padrao", []) or []]
    por_motivo = cfg.get("destinatarios.analise_manual.por_motivo", {}) or {}
    linhas += [["MANUAL_SAP", e] for e in por_motivo.get("SAP", []) or []]
    linhas += [["MANUAL_NAO_IDENTIFICADO", e] for e in por_motivo.get("NAO_IDENTIFICADO", []) or []]
    return linhas


def _linhas_filtros(cfg: Config, modelo: str) -> List[List[Any]]:
    dominios = list(cfg.get("filtros.dominios_internos", []) or [])
    linhas = [["DOMINIO_INTERNO", d, "S"] for d in dominios]
    if modelo == "calibracao" and not dominios:
        linhas = [["DOMINIO_INTERNO", E.PLACEHOLDER, "S"]]
    linhas += [["ASSUNTO_RESPOSTA_AUTOMATICA", a, "S"] for a in cfg.get("filtros.assuntos_resposta_automatica", []) or []]
    marcas = cfg.get("filtros.mensagens_do_rpa", {}) or {}
    linhas += [["MARCADOR_ASSUNTO_RPA", a, "S"] for a in marcas.get("assuntos", []) or []]
    linhas += [["MARCADOR_TEXTO_RPA", t, "S"] for t in marcas.get("textos", []) or []]
    return linhas


# --------------------------------------------------------------------------- #
# montagem do arquivo
# --------------------------------------------------------------------------- #
def gerar_modelo(cfg: Config, destino: Path, *, modelo: str = "calibracao", senha: Optional[str] = None) -> Path:
    """Grava o xlsx em ``destino``. ``modelo``: ``calibracao`` (com A_PREENCHER) ou ``perfil``."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Protection
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    if modelo not in ("calibracao", "perfil"):
        raise ValueError("modelo deve ser 'calibracao' ou 'perfil'")
    wb = Workbook()
    wb.remove(wb.active)
    cab_fill, cab_font = PatternFill("solid", fgColor=COR_CABECALHO), Font(bold=True, color="FFFFFF")
    desbloq = Protection(locked=False)

    def faixa_lista(nome: str) -> str:
        col, n = E.lista_para_validacao(nome)
        letra = get_column_letter(col)
        return f"={E.ABA_LISTAS}!${letra}$2:${letra}${n + 1}"

    def validacao(ws, nome_lista: str, faixa: str) -> None:
        dv = DataValidation(type="list", formula1=faixa_lista(nome_lista), allow_blank=True,
                            showErrorMessage=True, errorTitle="Valor inválido",
                            error=f"Escolha um valor da lista '{nome_lista}'.")
        ws.add_data_validation(dv)
        dv.add(faixa)

    def cabecalho(ws, colunas: List[str], linha: int = 1, larguras: Optional[List[int]] = None) -> None:
        for i, nome in enumerate(colunas, start=1):
            cel = ws.cell(row=linha, column=i, value=nome)
            cel.fill, cel.font = cab_fill, cab_font
            cel.alignment = Alignment(vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = (larguras or [])[i - 1] if larguras else 22
        ws.freeze_panes = ws.cell(row=linha + 1, column=1)

    def proteger(ws) -> None:
        ws.protection.sheet = True
        if senha:
            ws.protection.password = senha

    # ---- LEIA-ME ---------------------------------------------------------- #
    ws = wb.create_sheet(E.ABA_LEIAME)
    ws["A1"] = "RPA Dúvidas Financeiras – planilha de configuração"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A3"], ws["B3"] = "versao_modelo", E.VERSAO_MODELO
    ws["A3"].font = Font(bold=True)
    instrucoes = [
        "Como preencher:",
        "1. Troque todos os valores A_PREENCHER. Enquanto houver algum, o robô não roda e o 'verificar' mostra a aba, a linha e a coluna.",
        "2. As abas Geral, Filtros e Listas são protegidas (BT). As demais podem ser editadas pelo financeiro.",
        "3. Não renomeie abas nem colunas: a leitura é feita pelo nome do cabeçalho.",
        "4. Campos S/N aceitam S, N, Sim e Não. Datas aceitam data do Excel ou AAAA-MM-DD.",
        "5. Nenhuma senha ou credencial vai nesta planilha.",
        "6. Depois de qualquer alteração, rode a opção 1 (Verificar configuração) do robô.",
        "7. Registre a alteração no histórico abaixo.",
    ]
    for i, txt in enumerate(instrucoes, start=5):
        ws.cell(row=i, column=1, value=txt)
    linha_hist = 5 + len(instrucoes) + 1
    for i, nome in enumerate(["Data", "Quem alterou", "O que mudou"], start=1):
        c = ws.cell(row=linha_hist, column=i, value=nome)
        c.fill, c.font = cab_fill, cab_font
    ws.cell(row=linha_hist + 1, column=1, value=date.today())
    ws.cell(row=linha_hist + 1, column=1).number_format = "DD/MM/YYYY"
    ws.cell(row=linha_hist + 1, column=2, value="BT")
    ws.cell(row=linha_hist + 1, column=3, value=f"Modelo gerado ({modelo}) – versão {E.VERSAO_MODELO}")
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width, ws.column_dimensions["C"].width = 18, 18, 90

    # ---- Geral ------------------------------------------------------------ #
    ws = wb.create_sheet(E.ABA_GERAL)
    cabecalho(ws, E.COLUNAS[E.ABA_GERAL], larguras=[30, 45, 90])
    valores = _valores_geral(cfg, modelo)
    for n, campo in enumerate(E.CAMPOS_GERAL, start=2):
        ws.cell(row=n, column=1, value=campo.chave)
        v = valores.get(campo.chave)
        cel = ws.cell(row=n, column=2, value=v)
        if campo.tipo == "data" and isinstance(v, date):
            cel.number_format = "DD/MM/YYYY"
        if campo.tipo == "decimal" and isinstance(v, float):
            cel.number_format = "0.00"
        desc = campo.descricao + (" Obrigatória." if campo.obrigatoria else "")
        if campo.padrao_doc:
            desc += f" Padrão: {campo.padrao_doc}."
        ws.cell(row=n, column=3, value=desc)
        if campo.lista:
            validacao(ws, campo.lista, f"B{n}")
    proteger(ws)

    # ---- Categorias ------------------------------------------------------- #
    ws = wb.create_sheet(E.ABA_CATEGORIAS)
    cabecalho(ws, E.COLUNAS[E.ABA_CATEGORIAS], larguras=[22, 30, 22, 8, 18, 18, 24])
    for n, linha in enumerate(_linhas_categorias(cfg), start=2):
        for i, v in enumerate(linha, start=1):
            cel = ws.cell(row=n, column=i, value=v)
            if i == 6:
                cel.number_format = "DD/MM/YYYY"
    validacao(ws, "Códigos de categoria", "A2:A50")
    validacao(ws, "Ações", "C2:C50")
    validacao(ws, "S/N", "D2:E50")

    # ---- Palavras_chave --------------------------------------------------- #
    ws = wb.create_sheet(E.ABA_PALAVRAS)
    params, linhas = _linhas_palavras(cfg)
    for n, nome in enumerate(E.PARAMETROS_PALAVRAS, start=1):
        for col, v in ((1, nome), (2, params[nome])):
            c = ws.cell(row=n, column=col, value=v)
            c.fill = PatternFill("solid", fgColor=COR_PARAMETRO)
    ws.cell(row=1, column=3, value="Parâmetros do classificador (área protegida – BT)")
    cabecalho(ws, E.COLUNAS[E.ABA_PALAVRAS], linha=E.LINHA_CABECALHO_PALAVRAS, larguras=[22, 36, 8, 8, 30])
    inicio = E.LINHA_CABECALHO_PALAVRAS + 1
    for n, linha in enumerate(linhas, start=inicio):
        for i, v in enumerate(linha, start=1):
            ws.cell(row=n, column=i, value=v)
    fim = inicio + len(linhas) + 500
    for r in range(inicio, fim):
        for col in range(1, 6):
            ws.cell(row=r, column=col).protection = desbloq
    validacao(ws, "Códigos de categoria", f"A{inicio}:A{fim}")
    validacao(ws, "S/N", f"D{inicio}:D{fim}")
    proteger(ws)
    ws.protection.autoFilter = False
    ws.protection.sort = False

    # ---- Textos ----------------------------------------------------------- #
    ws = wb.create_sheet(E.ABA_TEXTOS)
    cabecalho(ws, E.COLUNAS[E.ABA_TEXTOS], larguras=[24, 24, 100])
    for n, linha in enumerate(_linhas_textos(cfg, modelo), start=2):
        for i, v in enumerate(linha, start=1):
            c = ws.cell(row=n, column=i, value=v)
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.cell(row=1, column=5, value="Campos disponíveis: " + ", ".join("{" + c + "}" for c in E.CAMPOS_TEXTO))

    # ---- Tutoriais -------------------------------------------------------- #
    ws = wb.create_sheet(E.ABA_TUTORIAIS)
    cabecalho(ws, E.COLUNAS[E.ABA_TUTORIAIS], larguras=[18, 90, 50, 12])
    for n, linha in enumerate(_linhas_tutoriais(cfg, modelo), start=2):
        for i, v in enumerate(linha, start=1):
            ws.cell(row=n, column=i, value=v)

    # ---- Destinatarios ---------------------------------------------------- #
    ws = wb.create_sheet(E.ABA_DESTINATARIOS)
    cabecalho(ws, E.COLUNAS[E.ABA_DESTINATARIOS], larguras=[26, 45])
    for n, linha in enumerate(_linhas_destinatarios(cfg, modelo), start=2):
        for i, v in enumerate(linha, start=1):
            ws.cell(row=n, column=i, value=v)
    validacao(ws, "Tipos de destinatário", "A2:A100")

    # ---- Filtros ---------------------------------------------------------- #
    ws = wb.create_sheet(E.ABA_FILTROS)
    cabecalho(ws, E.COLUNAS[E.ABA_FILTROS], larguras=[30, 70, 8])
    for n, linha in enumerate(_linhas_filtros(cfg, modelo), start=2):
        for i, v in enumerate(linha, start=1):
            ws.cell(row=n, column=i, value=v)
    validacao(ws, "Tipos de filtro", "A2:A300")
    validacao(ws, "S/N", "C2:C300")
    proteger(ws)

    # ---- Listas ----------------------------------------------------------- #
    ws = wb.create_sheet(E.ABA_LISTAS)
    for col, (nome, itens) in enumerate(E.LISTAS.items(), start=1):
        c = ws.cell(row=1, column=col, value=nome)
        c.fill, c.font = cab_fill, cab_font
        ws.column_dimensions[get_column_letter(col)].width = 24
        for r, item in enumerate(itens, start=2):
            ws.cell(row=r, column=col, value=item)
    proteger(ws)

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino
