"""RN3.1 / RN3.2 – mascaramento e truncamento antes do envio à IA (dados fictícios)."""
import pytest

from rpa_duvidas.extracao import truncar
from rpa_duvidas.mascaramento import BANCO, CNPJ, CPF, TELEFONE, cpf_valido, mascarar, mascarar_lista, preparar_para_ia


@pytest.mark.parametrize("texto", ["CNPJ 12.345.678/0001-95.", "CNPJ 12345678000195.", "CNPJ 12.345.678/000195."])
def test_cnpj_com_e_sem_pontuacao(texto):
    assert mascarar(texto) == f"CNPJ {CNPJ}."


def test_cpf_formatado_e_cpf_valido_sem_pontuacao():
    assert mascarar("CPF 123.456.789-09") == f"CPF {CPF}"
    assert cpf_valido("52998224725") and mascarar("CPF 52998224725") == f"CPF {CPF}"


@pytest.mark.parametrize("texto, esperado", [
    ("Banco 341, agência 1234-5, conta corrente 12345-6.", f"Banco {BANCO}, agência {BANCO}, conta corrente {BANCO}."),
    ("Ag. 0001 c/c 98765-4", f"Ag. {BANCO} c/c {BANCO}"),
    ("conta: 000123456-X", f"conta: {BANCO}"),
])
def test_dados_bancarios(texto, esperado):
    assert mascarar(texto) == esperado


@pytest.mark.parametrize("texto", [
    "chave PIX: financeiro@fornecedor-ficticio.com.br",
    "pix é 11987654321",
    "Chave Pix 12.345.678/0001-95",
    "PIX: 123e4567-e89b-12d3-a456-426614174000",
])
def test_chave_pix(texto):
    assert mascarar(texto).endswith(BANCO)
    assert "@" not in mascarar(texto) and "1198" not in mascarar(texto)


def test_pix_sem_valor_nao_some_com_o_texto():
    assert mascarar("podemos pagar via PIX para agilizar?") == "podemos pagar via PIX para agilizar?"


@pytest.mark.parametrize("texto", ["(11) 98765-4321", "+55 11 3456-7890", "11 98765-4321", "11987654321", "1134567890"])
def test_telefones(texto):
    assert mascarar(f"Tel {texto} ok") == f"Tel {TELEFONE} ok"


def test_nao_mascara_numeros_de_negocio():
    texto = "NF 123456, pedido 4500012345, vencida em 22/10/2026, R$ 1.234,56, CEP 01310-100"
    assert mascarar(texto) == texto


def test_mascarar_lista_de_anexos():
    assert mascarar_lista(["NF_12345678000195.pdf", "print.png"]) == ["NF_[CNPJ].pdf", "print.png"]


def test_truncamento_marca_o_corte():
    assert truncar("abc", 10) == "abc"
    t = truncar("x" * 7000, 6000)
    assert len(t) <= 6000 and t.endswith("[...]")
    assert preparar_para_ia("CNPJ 12345678000195 " + "y" * 3000, 2000).startswith("CNPJ [CNPJ]")
    assert len(preparar_para_ia("y" * 3000, 2000)) <= 2000
