"""v0.3.0 – T08: envio liberado por categoria e status por e-mail (D10 – seção 6.7).

Critério de aceite 8: categoria não liberada → sempre rascunho, mesmo com modo_execucao = REAL."""
import json

import pytest

from conftest import DESTINO_CAL
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.modelos import Acao, Categoria, MotivoManual, Status

FORNECEDOR = "ana@fornecedor-exemplo.com.br"


def _email(entrada, n, assunto, corpo):
    (entrada / f"{n:03d}.json").write_text(json.dumps({
        "id_mensagem": f"<{n}@x>", "remetente": FORNECEDOR, "nome_remetente": "Ana", "assunto": assunto,
        "corpo_texto": corpo, "data_recebimento": f"2026-11-03T09:{n:02d}:00"}), encoding="utf-8")


def _rodar(cfg):
    robo = montar_dependencias(cfg)
    try:
        resumo = robo.executar_ciclo()
        eventos = {e["id_mensagem"]: e for e in robo.registro.eventos()}
    finally:
        robo.registro.fechar()
    return {r.email.id_mensagem: r for r in resumo.resultados}, eventos


def _saidas(projeto, tipo):
    pasta = projeto / "dados_teste" / "caixa_simulada" / "saida"
    return [json.loads(p.read_text(encoding="utf-8")) for p in pasta.glob(f"*_{tipo}.json")]


def _liberar(cfg, *codigos):
    for cod in codigos:
        cfg.dados["categorias"][cod].update(liberada=True, data_liberacao="2026-11-01")


def test_uma_categoria_liberada_e_outra_nao_no_mesmo_ciclo(projeto_cal, cfg_cal, entrada):
    cfg_cal.dados["execucao"]["envio_real"] = True
    cfg_cal.dados["destinatarios"]["acao_manual"] = "ENCAMINHAR"
    _liberar(cfg_cal, "FORMS_PO")                                  # FORMS liberado; MANUAL_SAP não
    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra")
    _email(entrada, 2, "Pagamento", "quando vou receber o pagamento?")
    res, ev = _rodar(cfg_cal)

    forms, sap = res["<1@x>"], res["<2@x>"]
    assert (forms.status, forms.enviado, forms.categoria_liberada) == (Status.CONCLUIDO, True, True)
    assert (sap.status, sap.enviado, sap.categoria_liberada) == (Status.SIMULADO, False, False)
    assert (ev["<1@x>"]["enviado"], ev["<1@x>"]["categoria_liberada"], ev["<1@x>"]["status"]) == ("S", "S", "CONCLUIDO")
    assert (ev["<2@x>"]["enviado"], ev["<2@x>"]["categoria_liberada"], ev["<2@x>"]["status"]) == ("N", "N", "SIMULADO")
    [resp] = _saidas(projeto_cal, "RESPOSTA")
    [enc] = _saidas(projeto_cal, "ENCAMINHAMENTO")
    assert resp["modo"] == "ENVIADO" and enc["modo"] == "RASCUNHO"
    assert resp["para"] == [DESTINO_CAL] and enc["para"] == [DESTINO_CAL]
    # categoria do Outlook acompanha o status de cada e-mail
    cats = {json.loads(p.read_text(encoding="utf-8"))["id_mensagem"]: json.loads(p.read_text(encoding="utf-8"))["categorias_outlook"]
            for p in entrada.glob("*.json")}
    assert cats == {"<1@x>": ["RPA - Respondido"], "<2@x>": ["RPA - Simulado"]}


@pytest.mark.parametrize("envio_real, liberada, esperado", [
    (True, False, Status.SIMULADO),    # critério 8
    (False, True, Status.SIMULADO),    # liberada, mas modo SIMULACAO
    (False, False, Status.SIMULADO),
    (True, True, Status.CONCLUIDO),    # só as duas condições juntas enviam
])
def test_tres_condicoes_para_enviar(projeto_cal, cfg_cal, entrada, envio_real, liberada, esperado):
    cfg_cal.dados["execucao"]["envio_real"] = envio_real
    if liberada:
        _liberar(cfg_cal, "FORMS_PO")
    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra")
    res, _ = _rodar(cfg_cal)
    assert res["<1@x>"].status == esperado
    [resp] = _saidas(projeto_cal, "RESPOSTA")
    assert resp["modo"] == ("ENVIADO" if esperado == Status.CONCLUIDO else "RASCUNHO")


def test_manual_categorizado_fica_na_caixa_sem_mensagem(projeto_cal, cfg_cal, entrada):
    _email(entrada, 1, "Pagamento", "quando vou receber o pagamento?")
    res, ev = _rodar(cfg_cal)
    r = res["<1@x>"]
    assert (r.acao, r.status, r.enviado) == (Acao.ENCAMINHAR_MANUAL, Status.CONCLUIDO, False)
    assert r.classificacao.motivo_manual == MotivoManual.SAP
    assert _saidas(projeto_cal, "ENCAMINHAMENTO") == [] and _saidas(projeto_cal, "RESPOSTA") == []
    dados = json.loads((entrada / "001.json").read_text(encoding="utf-8"))
    assert dados["categorias_outlook"] == ["RPA - Encaminhado"]
    assert ev["<1@x>"]["enviado"] == "N"


def test_categoria_desativada_ou_configurada_como_manual(projeto_cal, cfg_cal, entrada):
    cfg_cal.dados["categorias"]["FORMS_PO"]["ativa"] = False
    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra")
    res, _ = _rodar(cfg_cal)
    c = res["<1@x>"].classificacao
    assert (c.categoria, c.motivo_manual) == (Categoria.MANUAL, MotivoManual.CATEGORIA_DESABILITADA)
    assert c.detalhes["categoria_sugerida"] == Categoria.FORMS_PO


def test_sem_aba_categorias_o_envio_segue_a_v021(cfg, novo_email):
    cfg.dados["execucao"]["envio_real"] = True
    novo_email("Pedido de compra", "preciso do pedido de compra")
    robo = montar_dependencias(cfg)
    try:
        [r] = robo.executar_ciclo().resultados
    finally:
        robo.registro.fechar()
    assert r.status == Status.CONCLUIDO and r.enviado is True
