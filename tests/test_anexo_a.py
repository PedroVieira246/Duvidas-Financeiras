"""Anexo A – o prompt é idêntico à especificação e os 9 exemplos passam por V1–V10 e D1–D7."""
import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml

from conftest import RAIZ
from rpa_duvidas.classificacao.decisao_ia import CategoriasIA, decidir
from rpa_duvidas.classificacao.ia import ModeloPrompt
from rpa_duvidas.classificacao.validacao_ia import validar_resposta
from rpa_duvidas.modelos import Acao, Categoria, MotivoManual

PROMPT = RAIZ / "config" / "prompts" / "classificacao_v1.txt"
ESPECIFICACAO = RAIZ.parent / "especificacao_funcional_classificacao.md"
# SHA-256 do bloco ```text do Anexo A da especificação de 22/10/2026 (v1.0)
HASH_ANEXO_A = "2c6218987da525ebf08973205916b74ea0896ec2293b3f6d4198cef44a232f6f"

# exemplo → (categoria final do RPA, motivo, regra) com a configuração inicial (seção 6.4)
ESPERADO = {
    1: (Categoria.TUT_UPLOAD_NF, None, "RESPONDER"),
    2: (Categoria.MANUAL, MotivoManual.MULTIPLAS_DUVIDAS, "D4"),
    3: (Categoria.MANUAL, MotivoManual.EXCECAO, "D5"),
    4: (Categoria.TUT_CADASTRO, None, "RESPONDER"),
    5: (Categoria.MANUAL, MotivoManual.MULTIPLAS_DUVIDAS, "D4"),
    6: (Categoria.MANUAL, MotivoManual.CATEGORIA_DESABILITADA, "D6"),   # C06 desligada até PA03
    7: (Categoria.MANUAL, MotivoManual.MULTIPLAS_DUVIDAS, "D4"),
    8: (Categoria.MANUAL, MotivoManual.SEM_RESPOSTA_PADRAO, "D2"),
    9: (Categoria.MANUAL, MotivoManual.NAO_IDENTIFICADO, "D2"),
}


def _exemplos():
    texto = PROMPT.read_text(encoding="utf-8")
    saidas = re.findall(r"^Exemplo (\d+).*?^SAÍDA:\n(\{.*?\})$", texto, re.M | re.S)
    return {int(n): s for n, s in saidas}


def _categorias(c06_ligada=False):
    dados = yaml.safe_load((RAIZ / "config" / "categorias_ia.yaml").read_text(encoding="utf-8"))
    if c06_ligada:
        dados["categorias"]["C06"]["resposta_automatica"] = True
    return CategoriasIA.de_dict(dados)


def test_prompt_identico_ao_anexo_a():
    texto = PROMPT.read_bytes()
    assert hashlib.sha256(texto).hexdigest() == HASH_ANEXO_A
    if ESPECIFICACAO.exists():                                    # confere direto na especificação, se estiver ao lado
        spec = ESPECIFICACAO.read_text(encoding="utf-8").split("## 9. Anexo A", 1)[1]
        bloco = spec.split("```text\n", 1)[1].split("\n```", 1)[0] + "\n"
        assert texto.decode("utf-8") == bloco


def test_prompt_tem_os_4_marcadores_e_os_delimitadores():
    assert ModeloPrompt.carregar(PROMPT).problemas() == []


def test_os_9_exemplos_existem():
    assert sorted(_exemplos()) == list(range(1, 10))


@pytest.mark.parametrize("n", range(1, 10))
def test_exemplo_passa_na_validacao_e_na_decisao(n):
    cats = _categorias()
    r = validar_resposta(_exemplos()[n], cats.codigos_validos, cats.tutoriais_validos(), cats.sinais_excecao)
    assert r.valida, r.erros
    assert r.resposta.formato_corrigido is False
    d = decidir(r.resposta, cats, 0.80)
    assert (d.categoria, d.motivo_manual, d.regra) == ESPERADO[n]


@pytest.mark.parametrize("n", range(1, 10))
def test_com_c06_ligada_a_acao_final_e_a_acao_indicada_no_exemplo(n):
    """Com todas as categorias com tutorial habilitadas, o RPA confirma a ação sugerida no exemplo."""
    cats = _categorias(c06_ligada=True)
    saida = _exemplos()[n]
    r = validar_resposta(saida, cats.codigos_validos, cats.tutoriais_validos(), cats.sinais_excecao)
    d = decidir(r.resposta, cats, 0.80)
    esperado = Acao.RESPONDER_TUTORIAL if json.loads(saida)["acao"] == "RESPONDER_TUTORIAL" else Acao.ENCAMINHAR_MANUAL
    assert d.acao == esperado
