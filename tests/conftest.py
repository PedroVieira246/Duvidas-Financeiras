"""Fixtures comuns: um projeto temporário com o perfil demo (caixa simulada)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from rpa_duvidas.config import carregar

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture()
def projeto(tmp_path: Path) -> Path:
    """Cópia de config/ e dos tutoriais fictícios num diretório temporário."""
    shutil.copytree(RAIZ / "config", tmp_path / "config")
    shutil.copytree(RAIZ / "dados_teste" / "tutoriais", tmp_path / "dados_teste" / "tutoriais")
    (tmp_path / "dados_teste" / "caixa_simulada" / "entrada").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def cfg(projeto):
    return carregar("demo", raiz=projeto)


@pytest.fixture()
def entrada(projeto) -> Path:
    return projeto / "dados_teste" / "caixa_simulada" / "entrada"


@pytest.fixture()
def novo_email(entrada):
    """Cria um e-mail .json na caixa simulada. Devolve o caminho."""
    contador = {"n": 0}

    def _novo(assunto: str, corpo: str = "", remetente: str = "maria@fornecedor-exemplo.com.br", **extra) -> Path:
        contador["n"] += 1
        n = contador["n"]
        dados = {
            "id_mensagem": f"<teste-{n}@local>",
            "remetente": remetente,
            "nome_remetente": "Teste",
            "assunto": assunto,
            "corpo_texto": corpo,
            "data_recebimento": f"2026-10-19T08:{n:02d}:00",
        }
        dados.update(extra)
        caminho = entrada / f"{n:03d}.json"
        caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return caminho

    return _novo


# --------------------------------------------------------------------------- #
# v0.2.0 – classificação por IA (perfil demo_ia, provedor simulado)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def cfg_ia(projeto):
    """Perfil demo_ia: caixa simulada + classificacao.tipo = ia + provedor simulado."""
    return carregar("demo_ia", raiz=projeto)


def json_ia(**sobrescrever):
    """Resposta da IA válida (contrato da seção 5.1), com campos sobrescrevíveis."""
    base = {
        "categoria": "C03", "categorias_secundarias": [], "tutorial": "TUT_UPLOAD_NF", "confianca": 0.92,
        "acao": "RESPONDER_TUTORIAL", "sinais_excecao": [], "resumo_duvida": None,
        "justificativa": "Pergunta como inserir a NF no portal.",
    }
    base.update(sobrescrever)
    return base


# --------------------------------------------------------------------------- #
# v0.3.0 – perfil calibracao configurado pela planilha (configuracao.xlsx)
# --------------------------------------------------------------------------- #
CAIXA_CAL = "maria.laura@empresa-exemplo.com.br"
DESTINO_CAL = "anelise@empresa-exemplo.com.br"
AVISO_CAL = "bt.rpa@empresa-exemplo.com.br"
FORMS_CAL = "https://forms.office.com/r/EXEMPLO-PO"

GERAL_CAL = {
    "email_caixa_entrada": CAIXA_CAL, "email_destino_padrao": DESTINO_CAL, "recebidos_desde": "2026-10-01",
    "caminho_planilha_escritorios": "dados_teste/escritorios.xlsx", "coluna_dominio": "Domínio",
    "coluna_escritorio": "Escritório", "caminho_arquivo_emails": "arquivo", "nome_analista": "Maria Laura",
}
TUTORIAIS_CAL = {
    "TUT_CONNECT": "dados_teste/tutoriais/04. Suporte Connect/Tutorial - Acesso ao Connect.pptx",
    "TUT_UPLOAD_NF": "dados_teste/tutoriais/Upload de NF/PYM (Connect) - Upload e consulta de NFs.pdf",
    "TUT_REEMBOLSO": "dados_teste/tutoriais/Reembolso/Como abrir um chamado de Reembolso.pptx",
    "TUT_CADASTRO": "dados_teste/tutoriais/03. Tutorial de acessos/Tutorial - Atualizacao de cadastro.pptx",
}
ESCRITORIOS_CAL = [("fornecedor-exemplo.com.br", "Escritório Exemplo"), ("outro-fornecedor.com.br", "Outro Escritório")]


def criar_planilha_escritorios(caminho: Path, linhas=ESCRITORIOS_CAL, colunas=("Domínio", "Escritório"),
                               aba="Escritórios") -> Path:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = aba
    ws.append(list(colunas))
    for linha in linhas:
        ws.append(list(linha))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho


def preencher_calibracao(projeto: Path, geral=None, categorias=None, tutoriais=None, link_forms=FORMS_CAL,
                         destinatarios=None, dominios=("empresa-exemplo.com.br",), textos=None,
                         destino: Path = None) -> Path:
    """Gera o modelo da calibração e troca os A_PREENCHER por valores de teste.

    ``categorias``: {CODIGO: {"Ativa": "S", "Liberada para envio": "S", ...}} (por nome de coluna).
    ``textos``: {CODIGO: corpo} acrescentados/substituídos na aba Textos.
    """
    from openpyxl import load_workbook

    from rpa_duvidas import config_xlsx_esquema as E
    from rpa_duvidas.config_xlsx_modelo import gerar_modelo

    destino = destino or projeto / "config" / "configuracao.xlsx"
    gerar_modelo(carregar("calibracao", raiz=projeto, usar_xlsx=False), destino)
    wb = load_workbook(destino)
    valores = {**GERAL_CAL, **(geral or {})}
    for linha in wb[E.ABA_GERAL].iter_rows(min_row=2):
        if linha[0].value in valores:
            linha[1].value = valores[linha[0].value]
    cats = wb[E.ABA_CATEGORIAS]
    cab = [c.value for c in cats[1]]
    for linha in cats.iter_rows(min_row=2):
        conf = (categorias or {}).get(linha[0].value) or {}
        for coluna, v in conf.items():
            linha[cab.index(coluna)].value = v
    tut = {**TUTORIAIS_CAL, **(tutoriais or {})}
    for linha in wb[E.ABA_TUTORIAIS].iter_rows(min_row=2):
        if linha[0].value in tut:
            linha[1].value = tut[linha[0].value]
        if linha[0].value == "FORMS_PO":
            linha[2].value = link_forms
    wd = wb[E.ABA_DESTINATARIOS]
    wd.delete_rows(2, wd.max_row)
    for tipo, end in (destinatarios or [("AVISO_ERRO", AVISO_CAL)]):
        wd.append([tipo, end])
    wf = wb[E.ABA_FILTROS]
    for linha in wf.iter_rows(min_row=2):
        if linha[0].value == "DOMINIO_INTERNO":
            linha[1].value = dominios[0] if dominios else None
    for d in list(dominios)[1:]:
        wf.append(["DOMINIO_INTERNO", d, "S"])
    if textos:
        wt = wb[E.ABA_TEXTOS]
        existentes = {linha[0].value: linha for linha in wt.iter_rows(min_row=2)}
        for cod, corpo in textos.items():
            if cod in existentes:
                existentes[cod][2].value = corpo
            else:
                wt.append([cod, None, corpo])
    wb.save(destino)
    if not (projeto / "dados_teste" / "escritorios.xlsx").exists():
        criar_planilha_escritorios(projeto / "dados_teste" / "escritorios.xlsx")
    return destino


@pytest.fixture()
def projeto_cal(projeto) -> Path:
    """Projeto temporário com config/configuracao.xlsx preenchido para a calibração."""
    preencher_calibracao(projeto)
    return projeto


def usar_caixa_simulada(cfg):
    """Troca a caixa do perfil calibracao (Outlook) pela caixa simulada em disco."""
    cfg.dados["caixa"].update({
        "tipo": "arquivo", "pasta_entrada": "entrada", "criar_pastas_ausentes": True,
        "pastas_destino": {"respondidos": "respondidos", "encaminhados": "encaminhados", "erro": "erro",
                           "ignorados": "ignorados"},
        "arquivo": {"raiz": "dados_teste/caixa_simulada"},
    })
    return cfg


@pytest.fixture()
def cfg_cal(projeto_cal):
    return usar_caixa_simulada(carregar("calibracao", raiz=projeto_cal))
