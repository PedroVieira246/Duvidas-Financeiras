"""v0.3.0 – T13: bloqueio automático da categoria por "Tutorial errado" (seção 6.7)."""
import json
from datetime import date, timedelta

from conftest import AVISO_CAL
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.modelos import Status
from rpa_duvidas.respostas import protocolo

FORNECEDOR = "ana@fornecedor-exemplo.com.br"


def _email(entrada, n):
    (entrada / f"{n:03d}.json").write_text(json.dumps({
        "id_mensagem": f"<{n}@x>", "remetente": FORNECEDOR, "nome_remetente": "Ana", "assunto": "Pedido de compra",
        "corpo_texto": "preciso do pedido de compra", "data_recebimento": f"2026-11-03T09:{n:02d}:00"}),
        encoding="utf-8")


def _avisos(projeto):
    saida = projeto / "dados_teste" / "caixa_simulada" / "saida"
    return [json.loads(p.read_text(encoding="utf-8")) for p in saida.glob("*_AVISO.json")]


def test_tutorial_errado_bloqueia_a_categoria_ate_nova_liberacao(projeto_cal, cfg_cal, entrada):
    cfg_cal.dados["execucao"]["envio_real"] = True
    hoje = date.today().isoformat()
    cfg_cal.dados["categorias"]["FORMS_PO"].update(liberada=True, data_liberacao=hoje)
    robo = montar_dependencias(cfg_cal)
    try:
        _email(entrada, 1)
        [r1] = robo.executar_ciclo().resultados
        assert r1.status == Status.CONCLUIDO                      # liberada: enviou
        robo.registro.gravar_retorno(protocolo(r1.email), {"avaliacao": "Tutorial errado"})

        _email(entrada, 2)
        [r2] = robo.executar_ciclo().resultados
        assert r2.status == Status.SIMULADO and r2.categoria_liberada is False   # bloqueada: só rascunho
        assert robo.bloqueadas == {"FORMS_PO": protocolo(r1.email)}
        _email(entrada, 3)
        [r3] = robo.executar_ciclo().resultados
        assert r3.status == Status.SIMULADO
        avisos = [a for a in _avisos(projeto_cal) if "bloqueada" in a["assunto"]]
        assert len(avisos) == 1 and avisos[0]["para"] == [AVISO_CAL]           # aviso uma única vez

        # o analista apaga e preenche de novo a data (nova liberação)
        robo.categorias["FORMS_PO"]["data_liberacao"] = (date.today() + timedelta(days=1)).isoformat()
        _email(entrada, 4)
        [r4] = robo.executar_ciclo().resultados
        assert r4.status == Status.CONCLUIDO and robo.bloqueadas == {}
    finally:
        robo.registro.fechar()


def test_tutorial_errado_antes_da_liberacao_nao_bloqueia(projeto_cal, cfg_cal, entrada):
    cfg_cal.dados["execucao"]["envio_real"] = True
    robo = montar_dependencias(cfg_cal)
    try:
        _email(entrada, 1)
        [r1] = robo.executar_ciclo().resultados                   # não liberada ainda: rascunho
        robo.registro.gravar_retorno(protocolo(r1.email), {"avaliacao": "Tutorial errado"})
        robo.categorias["FORMS_PO"].update(liberada=True,
                                           data_liberacao=(date.today() + timedelta(days=1)).isoformat())
        _email(entrada, 2)
        [r2] = robo.executar_ciclo().resultados
        assert robo.bloqueadas == {} and r2.categoria_liberada is True
    finally:
        robo.registro.fechar()


def test_outras_avaliacoes_nao_bloqueiam(projeto_cal, cfg_cal, entrada):
    cfg_cal.dados["categorias"]["FORMS_PO"].update(liberada=True, data_liberacao=date.today().isoformat())
    robo = montar_dependencias(cfg_cal)
    try:
        _email(entrada, 1)
        [r1] = robo.executar_ciclo().resultados
        robo.registro.gravar_retorno(protocolo(r1.email), {"avaliacao": "Categoria errada"})
        _email(entrada, 2)
        robo.executar_ciclo()
        assert robo.bloqueadas == {}
    finally:
        robo.registro.fechar()
