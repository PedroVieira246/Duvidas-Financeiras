"""v0.3.0 – T05: planilha de escritórios (D06, seção 5.9)."""
import json

import pytest

from conftest import AVISO_CAL, criar_planilha_escritorios
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.filtros import (SEM_ESCRITORIO, ErroEscritorios, ler_planilha_escritorios, normalizar_dominio)
from rpa_duvidas.modelos import Categoria, MotivoManual


def test_mapa_de_dominios_normalizado(tmp_path):
    arq = criar_planilha_escritorios(tmp_path / "esc.xlsx", [
        (" @Fornecedor-Exemplo.com.BR ", "Escritório Exemplo"),
        ("contato@outro.com.br; terceiro.adv.br", "Outro"),
        ("fornecedor-exemplo.com.br", "Escritório Exemplo"),      # repetido com o mesmo escritório: ok
        ("gmail.com", "Pessoa física"),
        (None, None),
    ])
    mapa = ler_planilha_escritorios(arq)
    assert mapa.mapa == {"fornecedor-exemplo.com.br": "Escritório Exemplo", "outro.com.br": "Outro",
                         "terceiro.adv.br": "Outro", "gmail.com": "Pessoa física"}
    assert mapa.escritorio("Ana@Outro.com.br") == "Outro"
    assert mapa.escritorio("x@desconhecido.com") == SEM_ESCRITORIO
    assert mapa.lista_fornecedores().conhecido("joao@terceiro.adv.br")
    assert any("gmail.com" in a and "público" in a for a in mapa.avisos)


def test_normalizar_dominio():
    assert normalizar_dominio(" @Exemplo.COM ") == "exemplo.com"
    assert normalizar_dominio("fulano@exemplo.com") == "exemplo.com"


def test_dominio_duplicado_com_dois_escritorios_mostra_as_linhas(tmp_path):
    arq = criar_planilha_escritorios(tmp_path / "esc.xlsx", [("a.com.br", "A"), ("b.com.br", "B"), ("A.com.br", "C")])
    with pytest.raises(ErroEscritorios, match=r"a\.com\.br: linha 2 \(A\), linha 4 \(C\)"):
        ler_planilha_escritorios(arq)


def test_coluna_ausente_e_aba_e_colunas_configuraveis(tmp_path):
    arq = criar_planilha_escritorios(tmp_path / "esc.xlsx", [("a.com.br", "A")], colunas=("Dominio do e-mail", "Nome"),
                                     aba="Lista")
    with pytest.raises(ErroEscritorios, match="não encontrada"):
        ler_planilha_escritorios(arq)
    with pytest.raises(ErroEscritorios, match="Aba 'Outra' não existe"):
        ler_planilha_escritorios(arq, aba="Outra", coluna_dominio="Dominio do e-mail", coluna_escritorio="Nome")
    mapa = ler_planilha_escritorios(arq, aba="Lista", coluna_dominio="DOMÍNIO DO E-MAIL", coluna_escritorio="nome")
    assert mapa.mapa == {"a.com.br": "A"}


def test_arquivo_ausente_bloqueado_ou_so_na_nuvem(tmp_path, monkeypatch):
    with pytest.raises(ErroEscritorios, match="não encontrada"):
        ler_planilha_escritorios(tmp_path / "nao_existe.xlsx")
    arq = criar_planilha_escritorios(tmp_path / "esc.xlsx")
    with pytest.raises(ErroEscritorios, match="só na nuvem"):
        ler_planilha_escritorios(arq, somente_na_nuvem=lambda p: True)

    def bloqueado(*a, **k):
        raise PermissionError("arquivo em uso por outro processo")

    monkeypatch.setattr("rpa_duvidas.filtros.shutil.copy2", bloqueado)
    with pytest.raises(ErroEscritorios, match="bloqueada"):
        ler_planilha_escritorios(arq)


def test_ciclo_usa_a_planilha_como_lista_de_fornecedores(projeto, cfg, novo_email):
    criar_planilha_escritorios(projeto / "dados_teste" / "escritorios.xlsx", [("fornecedor-exemplo.com.br", "Escritório X")])
    cfg.dados["escritorios"]["arquivo"] = "dados_teste/escritorios.xlsx"
    novo_email("Reembolso", "preciso de reembolso")                                   # domínio na planilha
    novo_email("Reembolso", "preciso de reembolso", remetente="contato@outro-fornecedor.com.br")  # só no YAML antigo
    robo = montar_dependencias(cfg)
    try:
        resumo = robo.executar_ciclo()
        por_rem = {r.email.remetente: r for r in resumo.resultados}
        assert por_rem["maria@fornecedor-exemplo.com.br"].classificacao.categoria == Categoria.TUT_REEMBOLSO
        assert por_rem["maria@fornecedor-exemplo.com.br"].email.escritorio == "Escritório X"
        assert por_rem["contato@outro-fornecedor.com.br"].classificacao.motivo_manual == MotivoManual.FORA_DA_LISTA
        ev = {e["remetente"]: e for e in robo.registro.eventos()}
        assert ev["maria@fornecedor-exemplo.com.br"]["escritorio"] == "Escritório X"
    finally:
        robo.registro.fechar()


def test_planilha_indisponivel_o_ciclo_nao_roda_e_avisa_uma_vez_por_dia(projeto, cfg, novo_email):
    cfg.dados["escritorios"]["arquivo"] = "dados_teste/nao_existe.xlsx"
    cfg.dados["destinatarios"]["avisos_erro"] = [AVISO_CAL]
    cfg.dados["seguranca"]["destinatarios_permitidos"].append(AVISO_CAL)
    caminho = novo_email("Reembolso", "preciso de reembolso")
    robo = montar_dependencias(cfg)
    try:
        r1 = robo.executar_ciclo()
        r2 = robo.executar_ciclo()
    finally:
        robo.registro.fechar()
    assert "não encontrada" in r1.falha and r1.resultados == [] and r2.falha
    assert caminho.exists()                                           # nenhum e-mail lido nem movido
    saida = projeto / "dados_teste" / "caixa_simulada" / "saida"
    avisos = [json.loads(p.read_text(encoding="utf-8")) for p in saida.glob("*_AVISO.json")]
    assert len(avisos) == 1 and avisos[0]["assunto"] == "[RPA Dúvidas Financeiras] Ciclo não executado"
