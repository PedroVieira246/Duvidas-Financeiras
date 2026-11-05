"""Ciclo completo (E1–E8) com a caixa simulada, classificacao.tipo = ia e provedor SIMULADO."""
import json
import logging

from rpa_duvidas.__main__ import main, montar_dependencias
from rpa_duvidas.classificacao.provedores_ia import ProvedorSimulado, TimeoutProvedorIA
from rpa_duvidas.modelos import Acao, Categoria, MotivoManual, Status


def _caixa(projeto):
    return projeto / "dados_teste" / "caixa_simulada"


def _saidas(projeto, tipo="*"):
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((_caixa(projeto) / "saida").glob(f"*_{tipo}.json"))]


def test_ciclo_ia_responde_com_tutorial_e_encaminha_com_resumo(projeto, cfg_ia, novo_email, caplog):
    robo = montar_dependencias(cfg_ia)
    novo_email("Faturamento - [MÊS]", "A NF do faturamento já foi emitida. Precisamos inseri-la no sistema. Como fazemos?")
    novo_email("Faturamento", "Estamos tentando inserir a NF, mas o sistema volta para a tela de login e não consigo "
                              "seguir. CNPJ 12.345.678/0001-95.", anexos=["print_erro.png"])
    with caplog.at_level(logging.INFO):
        resumo = robo.executar_ciclo()
    ev = robo.registro.eventos()
    brutas = robo.registro.respostas_ia()
    robo.registro.fechar()

    assert resumo.contagem() == {"lidos": 2, "respondidos": 1, "encaminhados": 1, "ignorados": 0, "erros": 0, "reconciliados": 0}
    r1, r2 = resumo.resultados
    assert (r1.acao, r1.classificacao.categoria, r1.status) == (Acao.RESPONDER_TUTORIAL, Categoria.TUT_UPLOAD_NF, Status.SIMULADO)
    assert (r2.acao, r2.classificacao.motivo_manual) == (Acao.ENCAMINHAR_MANUAL, MotivoManual.EXCECAO)

    # E6: a resposta ao fornecedor vem do modelo TUT_*, nunca do texto da IA (RN6.1)
    resposta = _saidas(projeto, "RESPOSTA")[0]
    assert resposta["anexos"] == ["PYM (Connect) - Upload e consulta de NFs.pdf"] and resposta["modo"] == "RASCUNHO"
    justificativa_ia = r1.classificacao.detalhes["resposta_ia"]["justificativa"]
    assert justificativa_ia not in resposta["corpo_html"] and "Resposta automática" in resposta["corpo_html"]

    # E7: encaminhamento com motivo no assunto e resumo/categoria/sinais na nota
    enc = _saidas(projeto, "ENCAMINHAMENTO")[0]
    assert enc["assunto"] == "[MANUAL – EXCEÇÃO] Faturamento"
    assert "O fornecedor não consegue concluir o upload da NF" in enc["corpo_html"]
    assert "C03 – Envio / upload de NF" in enc["corpo_html"] and "ERRO_SISTEMA" in enc["corpo_html"]
    assert "12.345.678/0001-95" in enc["corpo_html"]            # o original ao analista NÃO é mascarado (RN3.1)
    assert enc["anexos"] == ["print_erro.png"]

    # E8: registro com as colunas novas e JSON bruto em tabela separada
    assert [e["classificador"] for e in ev] == ["ia", "ia"]
    assert ev[1]["resumo_duvida"].startswith("O fornecedor") and ev[1]["regra_decisao"] == "D5"
    assert ev[0]["versao_prompt"] == "classificacao_v1" and ev[0]["tentativas_ia"] == "1"
    assert len(brutas) == 2

    # RN8.2: o log técnico não grava corpo, prompt nem resumo
    texto_log = caplog.text
    assert "tela de login" not in texto_log and "<<<CORPO>>>" not in texto_log
    assert "O fornecedor não consegue" not in texto_log
    assert "IA | categoria C03" in texto_log


def test_ia_indisponivel_vai_para_manual_e_nao_para_erro(projeto, cfg_ia, novo_email):
    robo = montar_dependencias(cfg_ia)
    robo.classificador._dormir = lambda s: None
    novo_email("Faturamento", "Como inserimos a NF? [[simular_timeout]]")
    r = robo.executar_ciclo().resultados[0]
    robo.registro.fechar()
    assert r.status == Status.SIMULADO and r.acao == Acao.ENCAMINHAR_MANUAL
    assert r.classificacao.motivo_manual == MotivoManual.IA_INDISPONIVEL and r.classificacao.detalhes["tentativas"] == 3
    enc = _saidas(projeto, "ENCAMINHAMENTO")[0]
    assert enc["assunto"].startswith("[MANUAL – IA INDISPONÍVEL]")
    assert "Resumo indisponível – ver e-mail original" in enc["corpo_html"]
    assert not list((_caixa(projeto) / "erro").glob("*.json"))


def test_5_falhas_seguidas_avisam_uma_vez_e_o_resto_do_ciclo_vai_para_manual(projeto, cfg_ia, novo_email):
    robo = montar_dependencias(cfg_ia)
    robo.classificador.provedor = ProvedorSimulado(roteiro=[TimeoutProvedorIA("t")] * 15)
    robo.classificador._dormir = lambda s: None
    for i in range(7):
        novo_email(f"Faturamento {i}", "Como inserimos a NF?")
    resumo = robo.executar_ciclo()
    robo.registro.fechar()
    assert all(r.classificacao.motivo_manual == MotivoManual.IA_INDISPONIVEL for r in resumo.resultados)
    assert [r.classificacao.detalhes["tentativas"] for r in resumo.resultados] == [3, 3, 3, 3, 3, 0, 0]
    avisos = _saidas(projeto, "AVISO")
    assert len(avisos) == 1 and "IA indisponível" in avisos[0]["assunto"]
    assert "5 vezes seguidas" in avisos[0]["corpo_html"]


def test_json_invalido_persistente_no_ciclo(projeto, cfg_ia, novo_email):
    robo = montar_dependencias(cfg_ia)
    novo_email("Faturamento", "Como inserimos a NF? [[simular_json_invalido]]")
    r = robo.executar_ciclo().resultados[0]
    brutas = robo.registro.respostas_ia()
    robo.registro.fechar()
    assert r.classificacao.motivo_manual == MotivoManual.RESPOSTA_IA_INVALIDA
    assert len(brutas) == 2 and not any(b["valida"] for b in brutas)


def test_cli_executar_previa_e_verificar_com_ia(projeto, monkeypatch, novo_email, capsys):
    import rpa_duvidas.config as config

    monkeypatch.setattr("rpa_duvidas.__main__.carregar", lambda p=None: config.carregar(p, raiz=projeto))
    novo_email("Cadastro", "Houve alteração societária e precisamos atualizar o cadastro. Qual o procedimento?")
    assert main(["previa", "--perfil", "demo_ia"]) == 0
    assert "TUT_CADASTRO 0.94 · IA C05 · regra RESPONDER" in capsys.readouterr().out
    assert main(["executar", "--perfil", "demo_ia"]) == 0
    assert (projeto / "dados" / "demo_ia" / "registro_controle.xlsx").exists()
    assert main(["verificar", "--perfil", "demo_ia"]) == 0
    saida = capsys.readouterr().out
    assert "tipo: ia | limite de confiança efetivo: 0.80" in saida and "Tudo certo para executar." in saida


def test_reversibilidade_tipo_palavras_chave_volta_ao_classificador_antigo(cfg_ia):
    """RNF-IA08: trocar classificacao.tipo volta ao F06 e ao limite 0,70 sem mexer no código."""
    from rpa_duvidas.classificacao import criar_classificador
    from rpa_duvidas.classificacao.palavras_chave import ClassificadorPalavrasChave

    cfg_ia.dados["classificacao"]["tipo"] = "palavras_chave"
    assert isinstance(criar_classificador(cfg_ia), ClassificadorPalavrasChave)
    assert cfg_ia.limite_confianca == 0.70
