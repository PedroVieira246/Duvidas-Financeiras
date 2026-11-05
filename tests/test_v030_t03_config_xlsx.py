"""v0.3.0 – T03: leitura do configuracao.xlsx, ErroCelula e integração com carregar()."""
import copy

import pytest
from openpyxl import load_workbook

from conftest import AVISO_CAL, CAIXA_CAL, DESTINO_CAL, FORMS_CAL, preencher_calibracao
from rpa_duvidas import config_xlsx_esquema as E
from rpa_duvidas.config import ErroConfiguracao, carregar
from rpa_duvidas.config_xlsx import ErroCelula, ler_configuracao_xlsx
from rpa_duvidas.config_xlsx_modelo import gerar_modelo
from rpa_duvidas.tutoriais import RepositorioTutoriais

METADADOS = ("_inline", "_origem_xlsx", "configuracao_xlsx", "categorias")


def _sem_metadados(dados):
    d = copy.deepcopy(dados)
    for k in METADADOS:
        d.pop(k, None)
    d.get("respostas", {}).pop("textos", None)
    return d


def _editar(caminho, aba, linha, coluna, valor):
    wb = load_workbook(caminho)
    wb[aba].cell(row=linha, column=coluna, value=valor)
    wb.save(caminho)


def _linha_geral(caminho, chave):
    wb = load_workbook(caminho)
    return next(c.row for c in wb[E.ABA_GERAL]["A"] if c.value == chave)


# --------------------------------------------------------------------------- #
# critério da T03: o xlsx gerado na T02 vira um dicionário igual ao dos YAMLs
# --------------------------------------------------------------------------- #
def test_xlsx_do_dev_reproduz_os_yamls(projeto, tmp_path):
    dev = carregar("dev", raiz=projeto)
    arq = gerar_modelo(dev, tmp_path / "dev.xlsx", modelo="perfil")
    via_xlsx = carregar("dev", raiz=projeto, arquivo_xlsx=arq)

    # nas chaves que o xlsx cobre, nada muda em relação ao YAML
    assert _sem_metadados(via_xlsx.dados) == _sem_metadados(dev.dados)
    # termos: idênticos ao palavras_chave.yaml
    assert via_xlsx.yaml_referenciado("classificacao.arquivo_termos") == dev.yaml_referenciado("classificacao.arquivo_termos")
    # tutoriais: o caminho completo aponta para o mesmo arquivo que o glob do YAML escolhe
    resolver = lambda v: dev.caminho(v, eh_valor=True)  # noqa: E731
    antigo = RepositorioTutoriais(dev.yaml_referenciado("tutoriais.arquivo"), resolver)
    novos = via_xlsx.yaml_referenciado("tutoriais.arquivo")["categorias"]
    for cat in E.CODIGOS_TUTORIAL:
        assert resolver(novos[cat]["caminho_arquivo"]).resolve() == antigo.localizar(cat).caminho.resolve()
    # o dev não define os campos novos obrigatórios da calibração: só esses erros aparecem
    assert via_xlsx.erros_xlsx and all("obrigatóri" in e.mensagem for e in via_xlsx.erros_xlsx)


def test_planilha_da_calibracao_preenchida_e_valida(cfg_cal):
    assert cfg_cal.erros_xlsx == []
    assert cfg_cal.validar() == []
    assert cfg_cal.get("caixa.conta") == CAIXA_CAL
    assert cfg_cal.destino_teste == DESTINO_CAL
    assert cfg_cal.get("caixa.recebidos_desde") == "2026-10-01"
    assert cfg_cal.get("caixa.mover_apos_tratar") is False and cfg_cal.get("caixa.marcar_nao_fornecedores") is False
    assert cfg_cal.envio_real is False and cfg_cal.classificador == "palavras_chave"
    assert cfg_cal.get("respostas.link_forms_po") == FORMS_CAL
    assert cfg_cal.get("destinatarios.avisos_erro") == [AVISO_CAL]
    assert cfg_cal.get("filtros.dominios_internos") == ["empresa-exemplo.com.br"]
    # seção 6.2, item 5: permitidos = destino padrão + AVISO_ERRO
    assert cfg_cal.get("seguranca.destinatarios_permitidos") == [DESTINO_CAL, AVISO_CAL]
    assert set(cfg_cal.get("categorias")) == set(E.CODIGOS_CATEGORIA)


def test_sem_planilha_o_perfil_calibracao_para_com_erro_claro(projeto):
    with pytest.raises(ErroConfiguracao, match="Planilha de configuração não encontrada"):
        carregar("calibracao", raiz=projeto)


def test_dev_e_demo_ignoram_a_planilha(projeto):
    preencher_calibracao(projeto)                      # existe em config/, mas dev/demo não leem
    assert carregar("demo", raiz=projeto).validar() == []
    assert "_inline" not in carregar("dev", raiz=projeto).dados


def test_modelo_com_a_preencher_aponta_aba_linha_e_coluna(projeto):
    arq = gerar_modelo(carregar("calibracao", raiz=projeto, usar_xlsx=False), projeto / "config" / "configuracao.xlsx")
    _, erros = ler_configuracao_xlsx(arq)
    textos = [str(e) for e in erros]
    linha = _linha_geral(arq, "email_caixa_entrada")
    assert f'Aba Geral, linha {linha}, coluna "Valor": email_caixa_entrada: valor ainda não preenchido (A_PREENCHER)' in textos
    assert any(t.startswith('Aba Tutoriais, linha 2, coluna "Caminho do arquivo"') for t in textos)
    assert any(t.startswith('Aba Tutoriais, linha 6, coluna "Link do formulário"') for t in textos)
    assert any(t.startswith('Aba Destinatarios, linha 2, coluna "E-mail"') for t in textos)
    assert any(t.startswith("Aba Filtros, linha 2") for t in textos)
    cfg = carregar("calibracao", raiz=projeto)
    assert cfg.validar()[: len(erros)] == textos     # entra no validar(): impede a execução


@pytest.mark.parametrize("chave, valor, trecho", [
    ("ia_ligada", "S", "IA desligada nesta etapa"),
    ("destino_respostas", "FORNECEDOR", "reservado para a próxima etapa"),
    ("modo_execucao", "ENVIAR", "use SIMULACAO ou REAL"),
    ("email_destino_padrao", "sem-arroba", "e-mail inválido"),
    ("email_destino_padrao", CAIXA_CAL, "diferente do e-mail da caixa"),
    ("recebidos_desde", "01/11/2026", "data inválida"),
    ("lote_maximo", "vinte", "número inteiro inválido"),
    ("limite_confianca", "1,5", "entre 0 e 1"),
    ("mover_apos_tratar", "talvez", "use S ou N"),
])
def test_valores_invalidos_na_aba_geral(projeto, chave, valor, trecho):
    arq = preencher_calibracao(projeto, geral={chave: valor})
    _, erros = ler_configuracao_xlsx(arq)
    assert any(e.aba == "Geral" and e.coluna == "Valor" and trecho in e.mensagem for e in erros), erros


def test_sim_nao_e_datas_aceitam_as_variacoes(projeto):
    from datetime import datetime

    arq = preencher_calibracao(projeto, geral={"pular_ja_respondidos": "Não", "mover_apos_tratar": "sim",
                                               "recebidos_desde": datetime(2026, 11, 3), "limite_confianca": "0,75"})
    dados, erros = ler_configuracao_xlsx(arq)
    assert erros == []
    assert dados["caixa"]["pular_ja_respondidos"] is False and dados["caixa"]["mover_apos_tratar"] is True
    assert dados["caixa"]["recebidos_desde"] == "2026-11-03"
    assert dados["classificacao"]["limite_confianca"] == 0.75


def test_vazio_na_geral_assume_o_padrao(projeto):
    arq = preencher_calibracao(projeto, geral={"lote_maximo": None, "nivel_log": None})
    cfg = carregar("calibracao", raiz=projeto)
    assert cfg.erros_xlsx == []
    assert cfg.get("caixa.lote_maximo") == 20 and cfg.get("registro.nivel_log") == "INFO"
    assert arq.exists()


def test_versao_do_modelo_incompativel(projeto):
    arq = preencher_calibracao(projeto)
    _editar(arq, E.ABA_LEIAME, 3, 2, "0.2.0")
    _, erros = ler_configuracao_xlsx(arq)
    assert any("modelo incompatível" in e.mensagem for e in erros)


def test_categoria_textos_e_palavras_chave_validados(projeto):
    arq = preencher_calibracao(
        projeto,
        categorias={"TUT_REEMBOLSO": {"Liberada para envio": "S", "Código do texto": "RESP_NAO_EXISTE"},
                    "MANUAL": {"Ação": "RESPONDER_TUTORIAL"},
                    "TUT_CADASTRO": {"Ação": "RESPONDER_TEXTO"}},
        textos={"RESP_TUT_CONNECT": "Olá {nome_fornecedor}, veja {campo_errado}"},
    )
    wb = load_workbook(arq)
    wb[E.ABA_PALAVRAS].append(["MANUAL", "qualquer", 1, "S", "teste"])
    wb[E.ABA_PALAVRAS].append(["TUT_CONNECT", "connect", 1, "S", "repetido"])
    wb.save(arq)
    _, erros = ler_configuracao_xlsx(arq)
    msgs = [(e.aba, e.coluna, e.mensagem) for e in erros]
    assert any(a == "Categorias" and c == "Data da liberação" for a, c, _ in msgs)
    assert any(a == "Categorias" and c == "Código do texto" and "não existe" in m for a, c, m in msgs)
    assert any(a == "Categorias" and c == "Código do texto" and "RESPONDER_TEXTO" in m for a, c, m in msgs)
    assert any(a == "Categorias" and c == "Ação" and "não vale para MANUAL" in m for a, c, m in msgs)
    assert any(a == "Textos" and "{campo_errado}" in m for a, _, m in msgs)
    assert any(a == "Palavras_chave" and c == "Categoria" for a, c, _ in msgs)
    assert any(a == "Palavras_chave" and c == "Termo" and "repetido" in m for a, c, m in msgs)


def test_termos_inativos_e_parametros_do_topo(projeto):
    arq = preencher_calibracao(projeto)
    wb = load_workbook(arq)
    ws = wb[E.ABA_PALAVRAS]
    ws["B1"] = 3
    linha = next(r for r in ws.iter_rows(min_row=5) if r[1].value == "reembolso")
    linha[3].value = "N"
    ws.append(["TUT_REEMBOLSO", "nota de débito", 4, "S", "calibração 18/11"])
    wb.save(arq)
    cfg = carregar("calibracao", raiz=projeto)
    termos = cfg.yaml_referenciado("classificacao.arquivo_termos")
    assert termos["peso_assunto"] == 3
    assert "reembolso" not in termos["categorias"]["TUT_REEMBOLSO"]["termos"]
    assert termos["categorias"]["TUT_REEMBOLSO"]["termos"]["nota de débito"] == 4


def test_coluna_renomeada_e_aba_ausente(projeto):
    arq = preencher_calibracao(projeto)
    wb = load_workbook(arq)
    wb[E.ABA_TUTORIAIS]["B1"] = "Caminho"
    del wb[E.ABA_TEXTOS]
    wb.save(arq)
    _, erros = ler_configuracao_xlsx(arq)
    assert ErroCelula("Tutoriais", 1, "Caminho do arquivo", "coluna ausente no cabeçalho") in erros
    assert ErroCelula("Textos", 0, "", "aba ausente no arquivo") in erros


def test_leitura_nao_altera_nem_trava_o_arquivo(projeto):
    arq = preencher_calibracao(projeto)
    antes = arq.read_bytes()
    ler_configuracao_xlsx(arq)
    assert arq.read_bytes() == antes
