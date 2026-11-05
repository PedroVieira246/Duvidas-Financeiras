"""E4 – validação da resposta da IA (regras V1 a V10)."""
import json

import pytest

from conftest import json_ia
from rpa_duvidas.classificacao.validacao_ia import extrair_json, validar_resposta

CODIGOS = ["C03", "C05", "C06", "C07", "C99"]
TUTORIAIS = ["TUT_UPLOAD_NF", "TUT_CADASTRO", "TUT_REEMBOLSO"]
SINAIS = ["ERRO_SISTEMA", "PEDIDO_PO", "STATUS_OU_PRAZO", "DOCUMENTACAO_REEMBOLSO"]


def _validar(texto):
    return validar_resposta(texto, CODIGOS, TUTORIAIS, SINAIS)


def test_resposta_valida():
    r = _validar(json.dumps(json_ia()))
    assert r.valida and not r.erros
    assert r.resposta.categoria == "C03" and r.resposta.formato_corrigido is False


@pytest.mark.parametrize("texto", [
    "```json\n" + json.dumps(json_ia()) + "\n```",
    "```\n" + json.dumps(json_ia()) + "\n```",
    "Segue a classificação:\n" + json.dumps(json_ia()) + "\nQualquer dúvida, estou à disposição.",
])
def test_v1_cerca_markdown_e_texto_extra_sao_aceitos_e_marcados(texto):
    r = _validar(texto)
    assert r.valida and r.resposta.formato_corrigido is True


@pytest.mark.parametrize("texto", ["", "não sei classificar", "{categoria: C03}", "[1, 2, 3]"])
def test_v1_sem_json_valido(texto):
    r = _validar(texto)
    assert not r.valida and r.erros[0].startswith("V1")


def test_extrair_json_pula_chaves_que_nao_sao_json():
    obj, corrigido, _ = extrair_json("texto {não é json} e depois " + json.dumps(json_ia()))
    assert obj["categoria"] == "C03" and corrigido


@pytest.mark.parametrize("mudanca, regra", [
    ({"categoria": None}, "V2"),
    ({"confianca": "alta"}, "V2"),
    ({"confianca": True}, "V2"),
    ({"categorias_secundarias": "C05"}, "V2"),
    ({"categoria": "C10"}, "V3"),
    ({"categorias_secundarias": ["C01"]}, "V4"),
    ({"categorias_secundarias": ["C03"]}, "V4"),
    ({"categorias_secundarias": ["C05", "C06", "C07", "C99"]}, "V4"),
    ({"tutorial": "upload_nf.pdf"}, "V5"),
    ({"confianca": 1.2}, "V6"),
    ({"confianca": -0.1}, "V6"),
    ({"acao": "RESPONDER"}, "V7"),
    ({"sinais_excecao": ["URGENTE"]}, "V8"),
    ({"acao": "ENCAMINHAR_MANUAL", "tutorial": None, "resumo_duvida": "x" * 401}, "V9"),
])
def test_regras_v2_a_v9_rejeitam(mudanca, regra):
    r = _validar(json.dumps(json_ia(**mudanca)))
    assert not r.valida
    assert any(e.startswith(regra) for e in r.erros), r.erros


def test_v2_campo_ausente():
    obj = json_ia()
    del obj["justificativa"]
    r = _validar(json.dumps(obj))
    assert not r.valida and "justificativa" in r.erros[0]


def test_v9_resumo_vazio_em_caso_manual_e_aceito_com_aviso():
    r = _validar(json.dumps(json_ia(acao="ENCAMINHAR_MANUAL", tutorial=None, resumo_duvida="")))
    assert r.valida and r.resposta.resumo_duvida is None
    assert any("resumo padrão" in a for a in r.resposta.ajustes)


def test_v10_justificativa_longa_e_truncada_sem_rejeitar():
    r = _validar(json.dumps(json_ia(justificativa="j" * 500)))
    assert r.valida and len(r.resposta.justificativa) == 300
    assert any(a.startswith("V10") for a in r.resposta.ajustes)


def test_tutorial_incoerente_passa_na_validacao_e_fica_para_d7():
    """Seção 6.5: tutorial válido, mas de outra categoria → não é rejeitado aqui (D7 decide)."""
    assert _validar(json.dumps(json_ia(tutorial="TUT_CADASTRO"))).valida


def test_resumo_duvida_pode_faltar_quando_responde():
    obj = json_ia()
    del obj["resumo_duvida"]
    assert _validar(json.dumps(obj)).valida
