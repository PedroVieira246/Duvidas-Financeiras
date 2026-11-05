"""v0.3.0 – T02: modelo do configuracao.xlsx e migração dos YAMLs."""
import openpyxl
import pytest
import yaml

from rpa_duvidas import config_xlsx_esquema as E
from rpa_duvidas.config import carregar
from rpa_duvidas.config_xlsx_modelo import gerar_modelo


@pytest.fixture()
def modelo_calibracao(projeto, tmp_path):
    return gerar_modelo(carregar("calibracao", raiz=projeto), tmp_path / "cal.xlsx", senha="segredo-teste")


@pytest.fixture()
def modelo_dev(projeto, tmp_path):
    return gerar_modelo(carregar("dev", raiz=projeto), tmp_path / "dev.xlsx", modelo="perfil")


def _geral(wb):
    return {r[0]: r[1] for r in wb[E.ABA_GERAL].iter_rows(min_row=2, values_only=True) if r[0]}


def test_modelo_tem_todas_as_abas_e_chaves(modelo_calibracao):
    wb = openpyxl.load_workbook(modelo_calibracao)
    assert wb.sheetnames == E.ABAS
    assert list(_geral(wb)) == [c.chave for c in E.CAMPOS_GERAL]
    assert wb[E.ABA_LEIAME]["A3"].value == "versao_modelo" and wb[E.ABA_LEIAME]["B3"].value == E.VERSAO_MODELO
    for aba, colunas in E.COLUNAS.items():
        linha = E.LINHA_CABECALHO_PALAVRAS if aba == E.ABA_PALAVRAS else 1
        assert [c.value for c in wb[aba][linha]][: len(colunas)] == colunas


def test_modelo_calibracao_marca_o_que_precisa_ser_preenchido(modelo_calibracao):
    wb = openpyxl.load_workbook(modelo_calibracao)
    g = _geral(wb)
    for chave in ("email_caixa_entrada", "email_destino_padrao", "recebidos_desde", "caminho_planilha_escritorios",
                  "coluna_dominio", "coluna_escritorio", "caminho_arquivo_emails", "nome_analista"):
        assert g[chave] == E.PLACEHOLDER, chave
    assert (g["destino_respostas"], g["modo_execucao"], g["ia_ligada"], g["acao_manual"]) == \
        ("TESTE", "SIMULACAO", "N", "CATEGORIZAR")
    tut = {r[0]: r for r in wb[E.ABA_TUTORIAIS].iter_rows(min_row=2, values_only=True)}
    assert all(tut[c][1] == E.PLACEHOLDER for c in E.CODIGOS_TUTORIAL)
    assert tut["FORMS_PO"][2] == E.PLACEHOLDER
    assert [r for r in wb[E.ABA_DESTINATARIOS].iter_rows(min_row=2, values_only=True)] == [("AVISO_ERRO", E.PLACEHOLDER)]
    assert ("DOMINIO_INTERNO", E.PLACEHOLDER, "S") in list(wb[E.ABA_FILTROS].iter_rows(min_row=2, values_only=True))
    cats = {r[0]: r for r in wb[E.ABA_CATEGORIAS].iter_rows(min_row=2, values_only=True)}
    assert list(cats) == E.CODIGOS_CATEGORIA and all(r[4] == "N" for r in cats.values())   # nada liberado


def test_abas_protegidas_e_area_de_parametros(modelo_calibracao):
    wb = openpyxl.load_workbook(modelo_calibracao)
    for aba in E.ABAS_PROTEGIDAS + [E.ABA_PALAVRAS]:
        assert wb[aba].protection.sheet, aba
    for aba in (E.ABA_CATEGORIAS, E.ABA_TEXTOS, E.ABA_TUTORIAIS, E.ABA_DESTINATARIOS):
        assert not wb[aba].protection.sheet, aba
    ws = wb[E.ABA_PALAVRAS]
    assert (ws["A1"].value, ws["A2"].value) == ("peso_assunto", "saturacao")
    assert ws["A1"].protection.locked and not ws["B5"].protection.locked   # termos editáveis, parâmetros não


def test_migracao_do_dev_copia_os_valores_dos_yamls(projeto, modelo_dev):
    cfg = carregar("dev", raiz=projeto)
    wb = openpyxl.load_workbook(modelo_dev)
    g = _geral(wb)
    assert g["filtro_assunto"] == "[RPA-TESTE]" and g["lote_maximo"] == 20 and g["max_varredura"] == 300
    assert g["mover_apos_tratar"] == "N" and g["nivel_log"] == "DEBUG" and g["modo_execucao"] == "SIMULACAO"
    assert g["recebidos_desde"].date().isoformat() == "2026-10-27"
    termos = yaml.safe_load((projeto / "config" / "palavras_chave.yaml").read_text(encoding="utf-8"))
    linhas = list(wb[E.ABA_PALAVRAS].iter_rows(min_row=E.LINHA_CABECALHO_PALAVRAS + 1, values_only=True))
    assert len([r for r in linhas if r[0]]) == sum(len(c["termos"]) for c in termos["categorias"].values())
    dest = list(wb[E.ABA_DESTINATARIOS].iter_rows(min_row=2, values_only=True))
    assert ("AVISO_ERRO", cfg.get("destinatarios.avisos_erro")[0]) in dest
    tut = {r[0]: r[1] for r in wb[E.ABA_TUTORIAIS].iter_rows(min_row=2, values_only=True)}
    for cod in E.CODIGOS_TUTORIAL:
        assert (projeto / tut[cod]).is_file(), cod                   # glob do YAML → caminho completo
