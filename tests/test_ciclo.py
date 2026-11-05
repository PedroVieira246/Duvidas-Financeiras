"""Testes de ponta a ponta do ciclo com a caixa simulada (perfil demo)."""
import json
import shutil

import pytest

from rpa_duvidas.__main__ import montar_dependencias, main
from rpa_duvidas.modelos import Acao, Categoria, Status
from rpa_duvidas.registro import ExecucaoEmAndamento, Registro, trava


@pytest.fixture()
def robo(cfg):
    r = montar_dependencias(cfg)
    yield r
    r.registro.fechar()


def _caixa(projeto):
    return projeto / "dados_teste" / "caixa_simulada"


def _saidas(projeto, tipo="*"):
    return [json.loads(p.read_text(encoding="utf-8")) for p in (_caixa(projeto) / "saida").glob(f"*_{tipo}.json")]


def test_cada_caminho_termina_no_destino_certo(projeto, robo, novo_email):
    novo_email("Acesso ao Connect", "não consigo acessar o portal connect, esqueci a senha")
    novo_email("Pedido de compra", "precisamos do pedido de compra")
    novo_email("Pagamento", "quando vou receber o pagamento?")
    novo_email("Resposta automática: férias", "fora do escritório")
    novo_email("Upload", "como faço upload da nf?", remetente="x@desconhecido.com.br")

    resumo = robo.executar_ciclo()

    assert resumo.contagem() == {"lidos": 5, "respondidos": 2, "encaminhados": 2, "ignorados": 1, "erros": 0, "reconciliados": 0}
    cx = _caixa(projeto)
    assert not list((cx / "entrada").iterdir())                       # nenhum e-mail fica sem destino
    assert len(list((cx / "respondidos").glob("*.json"))) == 2
    assert len(list((cx / "encaminhados").glob("*.json"))) == 2
    assert len(list((cx / "ignorados").glob("*.json"))) == 1

    respostas = _saidas(projeto, "RESPOSTA")
    tutorial = next(r for r in respostas if r["anexos"])
    assert tutorial["anexos"] == ["Tutorial - Acesso ao Connect.pptx"]
    assert tutorial["cc"] == ["analistas.cap@empresa-exemplo.com.br"]
    assert tutorial["modo"] == "RASCUNHO"                             # simulação: nada é enviado
    assert any("forms.office.com" in r["corpo_html"] for r in respostas)

    assuntos = sorted(e["assunto"] for e in _saidas(projeto, "ENCAMINHAMENTO"))
    assert assuntos == ["[MANUAL – FORA DA LISTA] Upload", "[MANUAL – SAP] Pagamento"]


def test_registro_e_planilha(projeto, robo, novo_email, cfg):
    novo_email("Reembolso", "preciso de reembolso")
    robo.executar_ciclo()
    ev = robo.registro.eventos()
    assert len(ev) == 1
    assert (ev[0]["categoria"], ev[0]["acao"], ev[0]["status"]) == (Categoria.TUT_REEMBOLSO, Acao.RESPONDER_TUTORIAL, Status.SIMULADO)
    assert ev[0]["arquivo_enviado"] == "Como abrir um chamado de Reembolso.pptx"

    destino = cfg.caminho("registro.planilha_controle")
    assert robo.registro.exportar_planilha(destino)
    from openpyxl import load_workbook

    wb = load_workbook(destino)
    assert wb.sheetnames == ["Registro", "Ciclos", "Resumo"]
    assert wb["Registro"].max_row == 2


def test_idempotencia_nunca_responde_duas_vezes(projeto, robo, novo_email):
    arq = novo_email("Reembolso", "preciso de reembolso")
    robo.executar_ciclo()
    # alguém arrasta o e-mail de volta para a entrada
    shutil.copy(_caixa(projeto) / "respondidos" / arq.name, arq)
    resumo = robo.executar_ciclo()
    assert resumo.resultados[0].status == Status.RECONCILIADO
    assert len(_saidas(projeto, "RESPOSTA")) == 1                    # nenhuma segunda resposta
    assert not list((_caixa(projeto) / "entrada").iterdir())


def test_falha_ao_mover_depois_de_responder_nao_gera_duplicidade(projeto, robo, novo_email):
    arq = novo_email("Reembolso", "preciso de reembolso", simular_falha="finalizar")
    r1 = robo.executar_ciclo().resultados[0]
    assert r1.status == Status.ERRO and "NÃO movido" in r1.erro
    assert arq.exists()                                                # ficou na entrada
    assert robo.registro.estado(r1.email.chave)["acao_executada"] == 1

    dados = json.loads(arq.read_text(encoding="utf-8"))
    dados.pop("simular_falha")
    arq.write_text(json.dumps(dados), encoding="utf-8")
    r2 = robo.executar_ciclo().resultados[0]
    assert r2.status == Status.RECONCILIADO and r2.destino == "erro"   # analista confere
    assert len(_saidas(projeto, "RESPOSTA")) == 1


def test_erro_vai_para_pasta_erro_avisa_e_nao_para_o_ciclo(projeto, robo, novo_email):
    novo_email("Reembolso", "preciso de reembolso", simular_falha="responder")
    novo_email("Pedido de compra", "precisamos do pedido de compra")
    resumo = robo.executar_ciclo()
    assert [r.status for r in resumo.resultados] == [Status.ERRO, Status.SIMULADO]
    assert len(list((_caixa(projeto) / "erro").glob("*.json"))) == 1
    aviso = _saidas(projeto, "AVISO")[0]
    assert "Erro no tratamento" in aviso["assunto"]


def test_erro_sem_acao_executada_pode_ser_reprocessado(projeto, robo, novo_email):
    novo_email("Reembolso", "preciso de reembolso", simular_falha="responder")
    r1 = robo.executar_ciclo().resultados[0]
    erro = _caixa(projeto) / "erro"
    arq = next(erro.glob("*.json"))
    dados = json.loads(arq.read_text(encoding="utf-8"))
    dados.pop("simular_falha")
    (_caixa(projeto) / "entrada" / arq.name).write_text(json.dumps(dados), encoding="utf-8")
    r2 = robo.executar_ciclo().resultados[0]
    assert (r1.status, r2.status) == (Status.ERRO, Status.SIMULADO)


def test_tutorial_ausente_manda_para_erro(projeto, robo, novo_email):
    shutil.rmtree(projeto / "dados_teste" / "tutoriais" / "Reembolso")
    novo_email("Reembolso", "preciso de reembolso")
    r = robo.executar_ciclo().resultados[0]
    assert r.status == Status.ERRO and "TutorialIndisponivel" in r.erro
    assert not _saidas(projeto, "RESPOSTA")


def test_trava_de_destinatarios_bloqueia_envio_externo(projeto, cfg, novo_email):
    cfg.dados["filtros"]["validar_fornecedor"] = False
    robo = montar_dependencias(cfg)
    novo_email("Reembolso", "preciso de reembolso", remetente="alguem@gmail.com")
    r = robo.executar_ciclo().resultados[0]
    robo.registro.fechar()
    assert r.status == Status.ERRO and "ErroSeguranca" in r.erro
    assert not _saidas(projeto, "RESPOSTA")


def test_baixa_confianca_vai_para_manual(projeto, cfg, novo_email):
    robo = montar_dependencias(cfg)
    novo_email("Dúvida", "problema com o login")   # um termo fraco: confiança 0.4 < 0.70
    r = robo.executar_ciclo().resultados[0]
    robo.registro.fechar()
    assert r.classificacao.categoria == Categoria.MANUAL
    assert r.classificacao.detalhes["categoria_sugerida"] == Categoria.TUT_CONNECT
    assert _saidas(projeto, "ENCAMINHAMENTO")[0]["assunto"].startswith("[MANUAL – BAIXA CONFIANÇA]")


def test_envio_real_marca_concluido(projeto, cfg, novo_email):
    cfg.dados["execucao"]["envio_real"] = True
    robo = montar_dependencias(cfg)
    novo_email("Pedido de compra", "precisamos do pedido de compra")
    r = robo.executar_ciclo().resultados[0]
    robo.registro.fechar()
    assert r.status == Status.CONCLUIDO
    assert _saidas(projeto, "RESPOSTA")[0]["modo"] == "ENVIADO"


def test_reprocessar_libera_somente_simulado_ou_erro(projeto, cfg):
    reg = Registro(cfg.caminho("registro.banco_estado"), "demo")
    reg.marcar_em_andamento("a", "AAAA0001", Acao.RESPONDER_FORMS)
    reg.con.execute("UPDATE estado SET status = ? WHERE chave = 'a'", (Status.CONCLUIDO,))
    reg.marcar_em_andamento("b", "BBBB0002", Acao.RESPONDER_FORMS)
    reg.con.execute("UPDATE estado SET status = ? WHERE chave = 'b'", (Status.SIMULADO,))
    reg.con.commit()
    assert reg.esquecer("aaaa0001") == 0
    assert reg.esquecer("bbbb0002") == 1
    reg.fechar()


def test_trava_impede_dois_ciclos(tmp_path):
    lock = tmp_path / "x.lock"
    with trava(lock):
        with pytest.raises(ExecucaoEmAndamento):
            with trava(lock):
                pass
    assert not lock.exists()


def test_cli_executar_e_verificar(projeto, monkeypatch, novo_email):
    import rpa_duvidas.config as config

    monkeypatch.setattr(config, "RAIZ_PROJETO", projeto)
    monkeypatch.setattr("rpa_duvidas.__main__.carregar", lambda p=None: config.carregar(p, raiz=projeto))
    novo_email("Pedido de compra", "precisamos do pedido de compra")
    assert main(["executar", "--perfil", "demo"]) == 0
    assert (projeto / "dados" / "demo" / "registro_controle.xlsx").exists()
    assert main(["verificar", "--perfil", "demo"]) == 0


def test_cli_previa_nao_altera_nada(projeto, monkeypatch, novo_email):
    import rpa_duvidas.config as config

    monkeypatch.setattr("rpa_duvidas.__main__.carregar", lambda p=None: config.carregar(p, raiz=projeto))
    novo_email("Pedido de compra", "precisamos do pedido de compra")
    assert main(["previa", "--perfil", "demo"]) == 0
    assert len(list((_caixa(projeto) / "entrada").iterdir())) == 1
    assert not (_caixa(projeto) / "saida").exists() or not list((_caixa(projeto) / "saida").iterdir())
