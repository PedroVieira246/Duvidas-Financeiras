"""v0.3.0 – T12: retorno manual na planilha de controle (D08 – seção 6.5).

Critério de aceite 7: o retorno preenchido sobrevive a todas as regenerações da planilha."""
import json
from datetime import datetime

import pytest
from openpyxl import load_workbook

from rpa_duvidas import __version__
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.registro import COLUNAS_REGISTRO, COLUNAS_RETORNO

FORNECEDOR = "ana@fornecedor-exemplo.com.br"
TITULOS_RETORNO = [t for _, t in COLUNAS_RETORNO]


def _email(entrada, n, assunto, corpo):
    (entrada / f"{n:03d}.json").write_text(json.dumps({
        "id_mensagem": f"<{n}@x>", "remetente": FORNECEDOR, "nome_remetente": "Ana", "assunto": assunto,
        "corpo_texto": corpo, "data_recebimento": f"2026-11-03T09:{n:02d}:00"}), encoding="utf-8")


@pytest.fixture()
def robo_cal(cfg_cal):
    r = montar_dependencias(cfg_cal)
    yield r
    r.registro.fechar()


def _planilha(cfg):
    return cfg.caminho("registro.planilha_controle")


def _preencher(arq, por_protocolo):
    wb = load_workbook(arq)
    ws = wb["Registro"]
    cab = [c.value for c in ws[1]]
    for linha in ws.iter_rows(min_row=2):
        prot = linha[cab.index("Protocolo")].value
        for titulo, valor in (por_protocolo.get(prot) or {}).items():
            linha[cab.index(titulo)].value = valor
    wb.save(arq)


def _linhas(arq):
    ws = load_workbook(arq)["Registro"]
    cab = [c.value for c in ws[1]]
    return [dict(zip(cab, [c.value for c in l])) for l in ws.iter_rows(min_row=2)]


def test_ida_e_volta_sem_perder_retorno(projeto_cal, cfg_cal, robo_cal, entrada):
    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra")
    _email(entrada, 2, "Pagamento", "quando vou receber o pagamento?")
    robo_cal.executar_ciclo()
    arq = _planilha(cfg_cal)
    assert robo_cal.registro.exportar_planilha(arq)
    prot = {l["ID da mensagem"]: l["Protocolo"] for l in _linhas(arq)}
    _preencher(arq, {
        prot["<1@x>"]: {"Avaliação": "Correto", "Tempo manual (min)": 7, "Revisado por": "Anelise",
                        "Data da revisão": datetime(2026, 11, 4), "Observação": "ok"},
        prot["<2@x>"]: {"Avaliação": "Deveria responder", "Categoria correta": "TUT_REEMBOLSO"},
    })
    assert robo_cal.registro.exportar_planilha(arq)                  # 1ª regeneração: lê e regrava
    ret = robo_cal.registro.retornos()
    assert ret[prot["<1@x>"]]["avaliacao"] == "Correto" and ret[prot["<1@x>"]]["tempo_manual_min"] == 7
    assert ret[prot["<1@x>"]]["data_revisao"] == "2026-11-04" and ret[prot["<1@x>"]]["lido_em"]
    assert ret[prot["<2@x>"]]["categoria_correta"] == "TUT_REEMBOLSO"

    # o analista apaga uma célula por engano: célula vazia não apaga o valor gravado
    _preencher(arq, {prot["<1@x>"]: {"Revisado por": None}})
    _email(entrada, 3, "Reembolso", "preciso de reembolso")         # e chega um e-mail novo
    robo_cal.executar_ciclo()
    for _ in range(3):                                               # várias regenerações
        assert robo_cal.registro.exportar_planilha(arq)
    linhas = {l["ID da mensagem"]: l for l in _linhas(arq)}
    assert len(linhas) == 3
    assert linhas["<1@x>"]["Avaliação"] == "Correto" and linhas["<1@x>"]["Revisado por"] == "Anelise"
    assert linhas["<1@x>"]["Data da revisão"].date().isoformat() == "2026-11-04"
    assert linhas["<2@x>"]["Categoria correta"] == "TUT_REEMBOLSO"
    assert linhas["<3@x>"]["Avaliação"] is None


def test_planilha_aberta_nao_quebra_o_ciclo(projeto_cal, cfg_cal, robo_cal, entrada, monkeypatch, caplog):
    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra")
    robo_cal.executar_ciclo()
    arq = _planilha(cfg_cal)
    assert robo_cal.registro.exportar_planilha(arq)
    antes = arq.read_bytes()

    def aberta(*a, **k):
        raise PermissionError("arquivo em uso")

    monkeypatch.setattr("openpyxl.load_workbook", aberta)
    assert robo_cal.registro.exportar_planilha(arq) is False
    assert "em uso" in caplog.text and arq.read_bytes() == antes     # nem leu nem regravou
    monkeypatch.undo()
    _email(entrada, 2, "Pagamento", "quando vou receber o pagamento?")
    assert len(robo_cal.executar_ciclo().resultados) == 1           # o ciclo segue normalmente


def test_valores_invalidos_sao_ignorados(projeto_cal, cfg_cal, robo_cal, entrada, caplog):
    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra")
    robo_cal.executar_ciclo()
    arq = _planilha(cfg_cal)
    robo_cal.registro.exportar_planilha(arq)
    [linha] = _linhas(arq)
    _preencher(arq, {linha["Protocolo"]: {"Avaliação": "Mais ou menos", "Tempo manual (min)": 300,
                                          "Categoria correta": "XYZ", "Data da revisão": "04/11/2026"}})
    robo_cal.registro.exportar_planilha(arq)
    ret = robo_cal.registro.retornos()[linha["Protocolo"]]
    assert ret["avaliacao"] is None and ret["tempo_manual_min"] is None and ret["categoria_correta"] is None
    assert ret["data_revisao"] == "2026-11-04"
    assert "avaliação fora da lista" in caplog.text and "tempo deve ser inteiro" in caplog.text


def test_colunas_novas_protecao_e_validacoes(projeto_cal, cfg_cal, robo_cal, entrada):
    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra")
    robo_cal.executar_ciclo()
    arq = _planilha(cfg_cal)
    robo_cal.registro.exportar_planilha(arq)
    wb = load_workbook(arq)
    ws = wb["Registro"]
    cab = [c.value for c in ws[1]]
    assert cab[-len(COLUNAS_RETORNO):] == TITULOS_RETORNO                      # retorno no fim
    for titulo in ("Escritório", "Destinatário original", "Arquivado em", "Máquina", "Usuário", "Versão"):
        assert titulo in cab
    [l] = _linhas(arq)
    assert l["Escritório"] == "Escritório Exemplo" and l["Versão"] == __version__ and l["Máquina"]
    assert ws.protection.sheet and ws.freeze_panes == "A2" and ws.auto_filter.ref
    col = {t: i + 1 for i, t in enumerate(cab)}
    assert not ws.cell(row=2, column=col["Avaliação"]).protection.locked
    assert ws.cell(row=2, column=col["Assunto"]).protection.locked
    assert ws.cell(row=1, column=col["Avaliação"]).fill.fgColor.rgb != ws.cell(row=1, column=1).fill.fgColor.rgb
    tipos = {dv.type for dv in ws.data_validations.dataValidation}
    assert {"list", "whole", "date"} <= tipos
    assert len(cab) == len(COLUNAS_REGISTRO) + len(COLUNAS_RETORNO)


def test_resumo_por_categoria(projeto_cal, cfg_cal, robo_cal, entrada):
    robo_cal.registro.criterio = (0.5, 2)
    for n in (1, 2, 3):
        _email(entrada, n, "Pedido de compra", "preciso do pedido de compra")
    robo_cal.executar_ciclo()
    arq = _planilha(cfg_cal)
    robo_cal.registro.exportar_planilha(arq)
    prot = {l["ID da mensagem"]: l["Protocolo"] for l in _linhas(arq)}
    _preencher(arq, {prot["<1@x>"]: {"Avaliação": "Correto", "Tempo manual (min)": 5},
                     prot["<2@x>"]: {"Avaliação": "Correto", "Tempo manual (min)": 10},
                     prot["<3@x>"]: {"Avaliação": "Deveria encaminhar", "Tempo manual (min)": 4}})
    robo_cal.registro.exportar_planilha(arq)
    [d] = robo_cal.registro.resumo_calibracao()
    assert (d["categoria"], d["avaliados"], d["corretos"], d["graves"], d["tempo"]) == ("FORMS_PO", 3, 2, 1, 15)
    assert d["atinge"] is True
    linhas = [r for r in load_workbook(arq)["Resumo"].iter_rows(values_only=True)]
    assert ("FORMS_PO", 3, 2, 66.7, 1, 15, "SIM") in linhas
