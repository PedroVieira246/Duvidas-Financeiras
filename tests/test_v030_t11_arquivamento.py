"""v0.3.0 – T11: arquivamento .msg e comando arquivar-pendentes (D05 – seção 6.4)."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from fakes_outlook import Caixa
from rpa_duvidas import config
from rpa_duvidas.__main__ import main, montar_dependencias
from rpa_duvidas.arquivamento import LIMITE_CAMINHO, Arquivador, caminho_msg, limpar
from rpa_duvidas.caixa.outlook_com import CaixaOutlookCOM
from rpa_duvidas.modelos import Status

FORNECEDOR = "ana@fornecedor-exemplo.com.br"


def _email(entrada, n, assunto, corpo, **extra):
    (entrada / f"{n:03d}.json").write_text(json.dumps({
        "id_mensagem": f"<{n}@x>", "remetente": FORNECEDOR, "nome_remetente": "Ana", "assunto": assunto,
        "corpo_texto": corpo, "data_recebimento": f"2026-11-03T09:{n:02d}:00", **extra}), encoding="utf-8")


def test_nome_do_arquivo_e_caracteres_invalidos(tmp_path):
    p = caminho_msg(tmp_path, "Escritório: A/B", datetime(2026, 11, 3, 9, 5), "ABCD1234", 'RE: NF 123/2026 "urgente"?*')
    assert p.parent == tmp_path / "Escritório AB" / "2026-11"
    assert p.name == "2026-11-03_0905_ABCD1234_RE NF 1232026 urgente.msg"
    assert limpar("x" * 100, 60) == "x" * 60
    assert limpar("termina com ponto. ") == "termina com ponto"


def test_caminho_longo_corta_o_assunto(tmp_path):
    raiz = tmp_path / ("p" * (LIMITE_CAMINHO - len(str(tmp_path)) - 60))
    p = caminho_msg(raiz, "Escritório", datetime(2026, 11, 3, 9, 5), "ABCD1234", "assunto bem comprido " * 5)
    assert len(str(p)) <= LIMITE_CAMINHO and p.name.startswith("2026-11-03_0905_ABCD1234")


def test_ciclo_arquiva_por_escritorio(projeto_cal, cfg_cal, entrada):
    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra")       # respondido (rascunho)
    _email(entrada, 2, "Pagamento", "quando vou receber o pagamento?")           # categorizado (manual)
    _email(entrada, 3, "Reembolso", "preciso de reembolso", ultimo_verbo=104)    # já encaminhado pelo analista
    robo = montar_dependencias(cfg_cal)
    try:
        resumo = robo.executar_ciclo()
        eventos = {e["id_mensagem"]: e for e in robo.registro.eventos()}
    finally:
        robo.registro.fechar()
    pasta = projeto_cal / "arquivo" / "Escritório Exemplo" / "2026-11"
    arquivos = sorted(p.name for p in pasta.glob("*.msg"))
    assert len(arquivos) == 3                                                    # critério 6
    for r in resumo.resultados:
        assert Path(r.arquivado_em).exists()
        assert eventos[r.email.id_mensagem]["arquivado_em"] == r.arquivado_em


def test_falha_no_arquivamento_nao_desfaz_a_resposta(projeto_cal, cfg_cal, entrada, monkeypatch):
    """Pasta sem permissão: a resposta fica, o e-mail não vai para Erro e o registro mostra FALHA."""
    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra")

    class PastaSemPermissao:
        def mkdir(self, *a, **k):
            raise PermissionError("Acesso negado")

    class CaminhoBloqueado:
        parent = PastaSemPermissao()

    monkeypatch.setattr("rpa_duvidas.arquivamento.caminho_msg", lambda *a, **k: CaminhoBloqueado())
    robo = montar_dependencias(cfg_cal)
    try:
        [r] = robo.executar_ciclo().resultados
        [ev] = robo.registro.eventos()
    finally:
        robo.registro.fechar()
    assert r.status == Status.SIMULADO                                           # a resposta ficou
    assert r.arquivado_em == "FALHA: PermissionError: Acesso negado"
    assert ev["arquivado_em"] == r.arquivado_em


def test_arquivar_pendentes_refaz_o_que_falhou(projeto_cal, cfg_cal, entrada, monkeypatch, capsys):
    from conftest import usar_caixa_simulada

    _email(entrada, 1, "Pedido de compra", "preciso do pedido de compra", simular_falha="arquivar")
    robo = montar_dependencias(cfg_cal)
    try:
        [r] = robo.executar_ciclo().resultados
    finally:
        robo.registro.fechar()
    assert r.arquivado_em.startswith("FALHA")
    dados = json.loads((entrada / "001.json").read_text(encoding="utf-8"))
    dados.pop("simular_falha")
    (entrada / "001.json").write_text(json.dumps(dados), encoding="utf-8")

    monkeypatch.setattr("rpa_duvidas.__main__.carregar",
                        lambda p=None: usar_caixa_simulada(config.carregar(p, raiz=projeto_cal)))
    assert main(["arquivar-pendentes", "--perfil", "calibracao"]) == 0
    assert "1 e-mail(s) com arquivamento pendente" in capsys.readouterr().out
    assert len(list((projeto_cal / "arquivo").rglob("*.msg"))) == 1
    assert main(["arquivar-pendentes", "--perfil", "calibracao"]) == 0           # nada mais pendente
    assert "0 e-mail(s)" in capsys.readouterr().out


def test_outlook_salva_o_original_como_msg(projeto_cal, tmp_path):
    fake = Caixa()
    original = fake.receber(de=FORNECEDOR, assunto="Reembolso", id_msg="<o@x>")
    cx = CaixaOutlookCOM("", "@inbox", {}, mover_apos_tratar=False, namespace=fake, aplicativo=fake)
    [e] = cx.ler_pendentes(5)
    e.escritorio = "Escritório Exemplo"
    destino = Arquivador(tmp_path / "arq").arquivar(cx, e)
    assert fake.salvos_como == [(destino, 3)] and original.salvo_como == destino   # SaveAs(caminho, olMSG)
    assert cx.localizar("<o@x>").id_mensagem == "<o@x>"


def test_pasta_de_arquivamento_so_na_nuvem(tmp_path):
    (tmp_path / "arq").mkdir()
    arq = Arquivador(tmp_path / "arq", somente_na_nuvem=lambda p: True)
    from rpa_duvidas.modelos import EmailRecebido

    assert arq.arquivar(object(), EmailRecebido("<1@x>", FORNECEDOR, "A", "x", "", "", None)).startswith(
        "FALHA: ErroArquivamento: pasta de arquivamento só na nuvem")
