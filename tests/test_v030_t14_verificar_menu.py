"""v0.3.0 – T14: verificar ampliado e menu do console (seção 7.2).

Também os testes dedicados aos critérios de aceite 2 (planilha com erro não lê nenhum e-mail)
e 9 (IA nunca chamada no perfil calibracao)."""
import json
import sys

import pytest

from conftest import CAIXA_CAL, preencher_calibracao, usar_caixa_simulada
from rpa_duvidas import config, verificacao
from rpa_duvidas.__main__ import main
from rpa_duvidas.config_xlsx_modelo import gerar_modelo

FORNECEDOR = "ana@fornecedor-exemplo.com.br"


class CaixaFalsa:
    """Caixa do Outlook simulada para o verificar (conta Microsoft Exchange)."""

    lidos = 0

    def avisos(self):
        return ["pasta de entrada: Caixa de Entrada | mover após tratar: NÃO"]

    def tipo_conta(self):
        return 0

    def verificar(self):
        return []

    def ler_pendentes(self, *a, **k):
        CaixaFalsa.lidos += 1
        return []

    def fechar(self):
        pass


@pytest.fixture()
def cli_cal(projeto_cal, monkeypatch):
    monkeypatch.setattr("rpa_duvidas.__main__.carregar", lambda p=None: config.carregar(p, raiz=projeto_cal))
    monkeypatch.setattr("rpa_duvidas.__main__.criar_caixa", lambda cfg: CaixaFalsa())
    monkeypatch.setattr(verificacao, "novo_outlook_ativo", lambda: False)
    return projeto_cal


def test_verificar_mostra_todos_os_itens_da_secao_7_2(cli_cal, capsys):
    assert main(["verificar", "--perfil", "calibracao"]) == 0
    saida = capsys.readouterr().out
    for trecho in (
        "[Planilha de configuração]", "planilha válida",                                  # configuracao.xlsx
        "Outlook clássico (Novo Outlook desligado)",                                       # Novo Outlook
        f"respostas de teste vão para anelise@empresa-exemplo.com.br (caixa: {CAIXA_CAL})",  # destino ≠ caixa
        "tipo da conta no Outlook: Microsoft Exchange",                                    # tipo da conta
        "planilha de escritórios: 2 domínio(s)",                                           # escritórios
        "TUT_REEMBOLSO", "Como abrir um chamado de Reembolso.pptx",                        # tutoriais
        "link do formulário de PO: https://forms.office.com/r/EXEMPLO-PO",                 # Forms
        "pasta de arquivamento aceita gravação",                                           # arquivamento
        "nenhuma categoria liberada para envio",                                           # categorias
        "IA: desligada nesta etapa",                                                       # D04
        "Tudo certo para executar.",
    ):
        assert trecho in saida, trecho
    [evidencia] = list((cli_cal / "logs").glob("verificar_*.txt"))
    assert "IA: desligada nesta etapa" in evidencia.read_text(encoding="utf-8")


def test_verificar_acusa_novo_outlook_e_categoria_liberada_em_simulacao(cli_cal, capsys, monkeypatch):
    monkeypatch.setattr(verificacao, "novo_outlook_ativo", lambda: True)
    preencher_calibracao(cli_cal, categorias={"FORMS_PO": {"Liberada para envio": "S", "Data da liberação": "2026-12-07"}})
    assert main(["verificar", "--perfil", "calibracao"]) == 1
    saida = capsys.readouterr().out
    assert "Novo Outlook está ligado" in saida
    assert "categorias liberadas para envio (FORMS_PO) com modo_execucao = SIMULACAO" in saida


def test_verificar_acusa_planilha_de_escritorios_e_tutorial_com_linha(cli_cal, capsys):
    preencher_calibracao(cli_cal, geral={"caminho_planilha_escritorios": "nao/existe.xlsx"},
                         tutoriais={"TUT_CADASTRO": "nao/existe.pptx"})
    assert main(["verificar", "--perfil", "calibracao"]) == 1
    saida = capsys.readouterr().out
    assert "Planilha de escritórios não encontrada" in saida
    assert 'TUT_CADASTRO   Aba Tutoriais, linha 5, coluna "Caminho do arquivo": Arquivo do tutorial não encontrado' in saida


# --------------------------------------------------------------------------- #
# critério de aceite 2
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("comando", ["executar", "previa"])
def test_criterio_2_planilha_com_erro_nao_le_nenhum_email(projeto, monkeypatch, capsys, comando):
    gerar_modelo(config.carregar("calibracao", raiz=projeto, usar_xlsx=False),
                 projeto / "config" / "configuracao.xlsx")                            # cheio de A_PREENCHER
    criadas = []
    monkeypatch.setattr("rpa_duvidas.__main__.carregar", lambda p=None: config.carregar(p, raiz=projeto))
    monkeypatch.setattr("rpa_duvidas.__main__.criar_caixa", lambda cfg: criadas.append(1) or CaixaFalsa())
    CaixaFalsa.lidos = 0
    assert main([comando, "--perfil", "calibracao"]) == 1
    err = capsys.readouterr().err
    assert 'Aba Geral, linha 2, coluna "Valor": email_caixa_entrada: valor ainda não preenchido (A_PREENCHER)' in err
    assert criadas == [] and CaixaFalsa.lidos == 0                                     # nem abriu a caixa


def test_criterio_2_verificar_tambem_mostra_aba_linha_e_coluna(projeto, monkeypatch, capsys):
    gerar_modelo(config.carregar("calibracao", raiz=projeto, usar_xlsx=False), projeto / "config" / "configuracao.xlsx")
    monkeypatch.setattr("rpa_duvidas.__main__.carregar", lambda p=None: config.carregar(p, raiz=projeto))
    monkeypatch.setattr("rpa_duvidas.__main__.criar_caixa", lambda cfg: CaixaFalsa())
    assert main(["verificar", "--perfil", "calibracao"]) == 1
    assert 'Aba Tutoriais, linha 2, coluna "Caminho do arquivo"' in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# critério de aceite 9
# --------------------------------------------------------------------------- #
@pytest.fixture()
def ia_proibida(monkeypatch):
    chamadas = []

    def proibido(nome):
        def _f(*a, **k):
            chamadas.append(nome)
            raise AssertionError(f"IA chamada no perfil calibracao: {nome}")
        return _f

    import rpa_duvidas.classificacao.ia as ia
    import rpa_duvidas.classificacao.provedores_ia as prov

    monkeypatch.setattr(ia, "criar_classificador_ia", proibido("criar_classificador_ia"))
    monkeypatch.setattr(ia, "verificar_ia", proibido("verificar_ia"))
    monkeypatch.setattr(ia.ClassificadorIA, "classificar", proibido("ClassificadorIA.classificar"))
    for nome in dir(prov):
        alvo = getattr(prov, nome)
        if isinstance(alvo, type) and nome.startswith("Provedor"):
            monkeypatch.setattr(alvo, "__init__", proibido(f"{nome}.__init__"))
    return chamadas


def test_criterio_9_ia_nunca_e_chamada_no_perfil_calibracao(projeto_cal, monkeypatch, ia_proibida, capsys):
    entrada = projeto_cal / "dados_teste" / "caixa_simulada" / "entrada"
    for n, (assunto, corpo) in enumerate([("Reembolso", "preciso de reembolso"), ("Dúvida", "texto sem termo"),
                                          ("Pagamento", "quando vou receber?")], start=1):
        (entrada / f"{n:03d}.json").write_text(json.dumps({
            "id_mensagem": f"<{n}@x>", "remetente": FORNECEDOR, "nome_remetente": "Ana", "assunto": assunto,
            "corpo_texto": corpo, "data_recebimento": f"2026-11-03T09:{n:02d}:00"}), encoding="utf-8")
    monkeypatch.setattr("rpa_duvidas.__main__.carregar",
                        lambda p=None: usar_caixa_simulada(config.carregar(p, raiz=projeto_cal)))
    monkeypatch.setattr(verificacao, "novo_outlook_ativo", lambda: False)
    assert main(["previa", "--perfil", "calibracao"]) == 0
    assert main(["executar", "--perfil", "calibracao"]) == 0
    assert main(["verificar", "--perfil", "calibracao"]) == 0
    assert main(["exportar", "--perfil", "calibracao"]) == 0
    assert ia_proibida == []
    assert "IA: desligada nesta etapa" in capsys.readouterr().out


def test_criterio_9_tipo_ia_e_recusado_mesmo_forcado(projeto_cal, monkeypatch, ia_proibida, capsys):
    def forcar_ia(p=None):
        cfg = usar_caixa_simulada(config.carregar(p, raiz=projeto_cal))
        cfg.dados["classificacao"]["tipo"] = "ia"         # alguém troca o tipo depois da planilha
        return cfg

    monkeypatch.setattr("rpa_duvidas.__main__.carregar", forcar_ia)
    assert main(["executar", "--perfil", "calibracao"]) == 1
    assert main(["previa", "--perfil", "calibracao"]) == 1
    assert "IA desligada nesta etapa" in capsys.readouterr().err
    assert ia_proibida == []


# --------------------------------------------------------------------------- #
# menu do console
# --------------------------------------------------------------------------- #
def test_menu_do_console(cli_cal, capsys):
    from rpa_duvidas.__main__ import cmd_menu
    import argparse

    respostas = iter(["1", "", "5", "", "9", "0"])
    assert cmd_menu(argparse.Namespace(perfil="calibracao"), entrada=lambda _: next(respostas)) == 0
    saida = capsys.readouterr().out
    assert f"RPA Dúvidas Financeiras v0.3.0 – {CAIXA_CAL}" in saida
    assert "4) Executar continuamente (a cada 15 min)" in saida
    assert "Tudo certo para executar." in saida
    assert "Planilha de controle ainda não existe" in saida and "Opção inválida." in saida


def test_duplo_clique_no_exe_abre_o_menu(monkeypatch):
    chamado = []
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr("rpa_duvidas.__main__.cmd_menu", lambda args: chamado.append(args.perfil) or 0)
    assert main([]) == 0 and chamado == [None]
