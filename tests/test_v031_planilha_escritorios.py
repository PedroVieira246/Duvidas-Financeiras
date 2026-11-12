"""v0.3.1 – leitura tolerante da planilha de escritórios (1º teste da operação assistida).

No 1º teste na máquina da área o ciclo não rodou: a planilha real é uma lista de
E-MAILS, com nomes de escritório diferentes para o mesmo domínio, #N/A, "CNPJ não
consta...", gmail compartilhado e texto colado na coluna. Os dados abaixo são
fictícios e reproduzem cada padrão encontrado.
"""
import logging

import pytest

from conftest import criar_planilha_escritorios
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.filtros import (SEM_ESCRITORIO, ErroEscritorios, FiltroInterno, chave_nome_escritorio,
                                 ler_planilha_escritorios, normalizar_email)
from rpa_duvidas.modelos import Categoria, MotivoManual

COLUNAS = ("E-mail", "Diretório", "Escritórios")
LINHAS_REAIS = [                                                                 # linha na planilha
    ("financeiro@alfa-adv.com.br", r"N:\Esc\Alfa", "ALFA ADVOGADOS"),            # 2
    ("adm@alfa-adv.com.br ", r"N:\Esc\Alfa", "ALFA ADVOGADOS"),                  # 3  espaço no fim
    ("Faturamento@Alfa-Adv.com.br", r"N:\Esc\Alfa", "ALFA ADVOGADOS"),           # 4  maiúsculas
    ("ana@beta.com.br", r"N:\Esc\Beta", "BETA ADVOGADOS"),                       # 5
    ("joao@beta.com.br", r"N:\Esc\Beta", "BETA SOCIEDADE DE ADVOGADOS"),         # 6  outro nome, mesmo domínio
    ("rui@beta.com.br", r"N:\Esc\Beta", "#N/A"),                                 # 7  erro do Excel
    ("eac@gama.com.br", r"N:\Esc\Gama", "GAMA MUSSNICH & ARAGAO"),               # 8  truncado / "&"
    ("qlo@gama.com.br", r"N:\Esc\Gama", "GAMA MUSSNICH E ARAGAO ADVOGADOS"),     # 9
    ("idn@delta.com.br", r"N:\Esc\Delta", "CNPJ não consta na base de fornecedores"),  # 10
    ("fat@delta.com.br", r"N:\Esc\Delta", "DELTA SENDACZ E OPICE"),              # 11
    ("pessoa.um@gmail.com", r"N:\Esc\Delta", "DELTA SENDACZ E OPICE"),           # 12 gmail
    ("pessoa.dois@gmail.com", r"N:\Esc\Eps", "EPSILON CONSULTORIA"),             # 13 gmail de outro escritório
    ("pessoa.dois@gmail.com ", r"N:\Esc\Eps", "EPSILON CONSULTORIA"),            # 14 repetido
    ("kazumi nome@gmail.com", r"N:\Esc\Zeta", "ZETA CONTABIL"),                  # 15 espaço no meio
    ("Nos termos, encaminhamos a nota nº 1/2026 para pagamento. Atenciosamente,", r"N:\Esc\Eta", "ETA"),  # 16
    ("fin@sigma.com.br", r"N:\Esc\Sigma", "SIGMA DOCUMENTOS"),                   # 17 mesmo domínio,
    ("ren@sigma.com.br", r"N:\Esc\Sigma", "SIGMA TECNOLOGIA LTDA."),             # 18 empresas diferentes
    ("a.b@br.omega.com", r"N:\Esc\Omega", "OMEGA ASSESSORIA"),                   # 19 subdomínio
    ("\u200bzero@teta.com.br\u00a0", r"N:\Esc\Teta", "TETA  ADVOGADOS"),         # 20 invisíveis, espaço duplo
    (None, None, None),                                                          # 21 vazia
]


@pytest.fixture()
def planilha_real(tmp_path):
    return criar_planilha_escritorios(tmp_path / "E-mail sharepoint.xlsx", LINHAS_REAIS, colunas=COLUNAS,
                                      aba="Planilha1")


def ler(arq):
    return ler_planilha_escritorios(arq, "Planilha1", "E-mail", "Escritórios", somente_na_nuvem=lambda p: False)


def test_planilha_com_variacoes_carrega_sem_erro(planilha_real):
    mapa = ler(planilha_real)
    assert mapa.linhas_lidas == 19
    assert len(mapa.linhas_invalidas) == 2
    assert any(a.startswith("linha 15:") and "não é e-mail" in a for a in mapa.linhas_invalidas)
    assert any(a.startswith("linha 16:") for a in mapa.linhas_invalidas)
    assert set(mapa.dominios_ambiguos) == {"beta.com.br", "sigma.com.br"}


def test_email_exato_vale_antes_do_dominio(planilha_real):
    mapa = ler(planilha_real)
    assert mapa.escritorio("ana@beta.com.br") == "BETA ADVOGADOS"
    assert mapa.escritorio("JOAO@beta.com.br") == "BETA SOCIEDADE DE ADVOGADOS"
    assert mapa.escritorio("rui@beta.com.br") == SEM_ESCRITORIO                 # #N/A
    assert mapa.escritorio("novo@beta.com.br") == SEM_ESCRITORIO                # domínio ambíguo
    assert mapa.escritorio("ren@sigma.com.br") == "SIGMA TECNOLOGIA LTDA."
    assert mapa.escritorio("novo@sigma.com.br") == SEM_ESCRITORIO
    assert mapa.lista_fornecedores().conhecido("novo@beta.com.br")              # continua fornecedor


def test_nomes_equivalentes_e_marcadores_sem_escritorio(planilha_real):
    mapa = ler(planilha_real)
    assert mapa.escritorio("novo@gama.com.br") == "GAMA MUSSNICH & ARAGAO" or \
        mapa.escritorio("novo@gama.com.br") == "GAMA MUSSNICH E ARAGAO ADVOGADOS"
    assert "gama.com.br" not in mapa.dominios_ambiguos
    assert mapa.escritorio("idn@delta.com.br") == SEM_ESCRITORIO
    assert mapa.escritorio("novo@delta.com.br") == "DELTA SENDACZ E OPICE"      # "CNPJ não consta" não conta
    assert any("linha 7:" in a and "#N/A" in a for a in mapa.avisos)
    assert any("linha 10:" in a and "CNPJ" in a for a in mapa.avisos)


def test_normalizacao_de_espacos_maiusculas_e_invisiveis(planilha_real):
    mapa = ler(planilha_real)
    assert mapa.escritorio("adm@alfa-adv.com.br") == "ALFA ADVOGADOS"
    assert mapa.escritorio("faturamento@alfa-adv.com.br") == "ALFA ADVOGADOS"
    assert mapa.escritorio("zero@teta.com.br") == "TETA ADVOGADOS"
    assert mapa.escritorio("x@br.omega.com") == "OMEGA ASSESSORIA"
    assert any("pessoa.dois@gmail.com repetido nas linhas 13, 14" in a for a in mapa.avisos)


def test_gmail_vale_so_pelo_endereco_exato(planilha_real):
    mapa = ler(planilha_real)
    forn = mapa.lista_fornecedores()
    assert "gmail.com" not in mapa.mapa
    assert forn.conhecido("pessoa.um@gmail.com") and mapa.escritorio("pessoa.um@gmail.com") == "DELTA SENDACZ E OPICE"
    assert mapa.escritorio("pessoa.dois@gmail.com") == "EPSILON CONSULTORIA"
    assert not forn.conhecido("qualquer@gmail.com")


def test_valores_sem_escritorio_configuraveis(planilha_real):
    mapa = ler_planilha_escritorios(planilha_real, "Planilha1", "E-mail", "Escritórios",
                                    somente_na_nuvem=lambda p: False, valores_sem_escritorio=())
    assert mapa.escritorio("idn@delta.com.br") == "CNPJ não consta na base de fornecedores"
    assert mapa.escritorio("novo@delta.com.br") == SEM_ESCRITORIO               # dois nomes → ambíguo


@pytest.mark.parametrize("celula,esperado", [
    ("a@x.com.br; b@y.com.br", {"x.com.br", "y.com.br"}),
    ("a@x.com.br,b@y.com.br", {"x.com.br", "y.com.br"}),
    ("x.com.br y.com.br", {"x.com.br", "y.com.br"}),
    ("@x.com.br", {"x.com.br"}),
    ("a@x.com.br; lixo", {"x.com.br"}),                       # separador explícito: aproveita o válido
])
def test_varios_itens_na_celula(tmp_path, celula, esperado):
    arq = criar_planilha_escritorios(tmp_path / "e.xlsx", [(celula, "X")])
    assert set(ler_planilha_escritorios(arq, somente_na_nuvem=lambda p: False).mapa) == esperado


@pytest.mark.parametrize("celula", ["fulano", "a@@b.com", "a@b", "pagamento.", "nome sobrenome@x.com", 12345])
def test_celulas_invalidas_sao_ignoradas_com_aviso(tmp_path, celula):
    arq = criar_planilha_escritorios(tmp_path / "e.xlsx", [(celula, "X"), ("ok@valido.com.br", "Y")])
    mapa = ler_planilha_escritorios(arq, somente_na_nuvem=lambda p: False)
    assert mapa.mapa == {"valido.com.br": "Y"} and len(mapa.linhas_invalidas) == 1


def test_planilha_so_com_linhas_invalidas_impede_o_ciclo(tmp_path):
    arq = criar_planilha_escritorios(tmp_path / "e.xlsx", [("texto qualquer", "X"), (None, "Y")])
    with pytest.raises(ErroEscritorios, match="sem nenhum e-mail/domínio válido"):
        ler_planilha_escritorios(arq, somente_na_nuvem=lambda p: False)


def test_planilha_grande_com_muitos_conflitos(tmp_path):
    linhas = [(f"u{i}@dom{i % 50}.com.br", f"ESCRITORIO {i % 7}") for i in range(5000)]
    arq = criar_planilha_escritorios(tmp_path / "e.xlsx", linhas)
    mapa = ler_planilha_escritorios(arq, somente_na_nuvem=lambda p: False)
    assert len(mapa.emails) == 5000 and len(mapa.dominios_ambiguos) == 50


def test_auxiliares():
    assert normalizar_email(" Ana.Silva@Exemplo.COM.br\u200b ") == "ana.silva@exemplo.com.br"
    assert normalizar_email("ana silva@x.com") == "anasilva@x.com"     # usado só depois da separação
    assert normalizar_email("sem-arroba.com") == ""
    assert chave_nome_escritorio("Barbosa Mussnich & Aragão") == chave_nome_escritorio("BARBOSA MUSSNICH E ARAGAO")


def test_email_completo_nos_dominios_internos_vale_como_caixa():
    f = FiltroInterno(["analista@empresa.com.br", "@interno.com.br"])
    assert f.interno("analista@empresa.com.br")[0]
    assert not f.interno("outra.pessoa@empresa.com.br")[0]
    assert f.interno("x@interno.com.br")[0]


def test_ciclo_com_a_planilha_real_passa_da_carga_e_processa(projeto, cfg, novo_email, caplog):
    destino = projeto / "dados_teste" / "escritorios.xlsx"
    criar_planilha_escritorios(destino, LINHAS_REAIS, colunas=COLUNAS, aba="Planilha1")
    cfg.dados["escritorios"].update({"arquivo": "dados_teste/escritorios.xlsx", "aba": "Planilha1",
                                     "coluna_dominio": "E-mail", "coluna_escritorio": "Escritórios"})
    novo_email("Reembolso", "preciso de reembolso", remetente="joao@beta.com.br")
    novo_email("Reembolso", "preciso de reembolso", remetente="novo@sigma.com.br")
    novo_email("Reembolso", "preciso de reembolso", remetente="qualquer@gmail.com")
    robo = montar_dependencias(cfg)
    try:
        with caplog.at_level(logging.INFO, logger="rpa_duvidas"):
            resumo = robo.executar_ciclo()
    finally:
        robo.registro.fechar()
    assert not resumo.falha
    por_rem = {r.email.remetente: r for r in resumo.resultados}
    assert por_rem["joao@beta.com.br"].classificacao.categoria == Categoria.TUT_REEMBOLSO
    assert por_rem["joao@beta.com.br"].email.escritorio == "BETA SOCIEDADE DE ADVOGADOS"
    assert por_rem["novo@sigma.com.br"].email.escritorio == SEM_ESCRITORIO
    assert por_rem["qualquer@gmail.com"].classificacao.motivo_manual == MotivoManual.FORA_DA_LISTA
    texto = caplog.text
    assert "Planilha de escritórios carregada" in texto and "linha 15:" in texto and "linha 16:" in texto
