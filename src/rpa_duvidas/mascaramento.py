"""Mascaramento de dados sensíveis antes do envio à IA (E3 – RN3.1, RN3.2, RNF-IA04).

Funções puras. O texto mascarado vai SÓ para a IA; o e-mail original que
segue para o analista não é alterado.

Marcadores (os mesmos citados no prompt do Anexo A):

* CNPJ (com ou sem pontuação)              → ``[CNPJ]``
* CPF (com pontuação, ou 11 dígitos válidos) → ``[CPF]``
* agência, conta, banco e chave PIX         → ``[BANCO/AG/CC]``
* telefones (com DDD)                       → ``[TELEFONE]``

Na dúvida, mascara: um número a mais escondido não prejudica a classificação,
um dado bancário exposto sim.
"""
from __future__ import annotations

import re
from typing import Iterable, List

from .extracao import truncar

CNPJ = "[CNPJ]"
CPF = "[CPF]"
BANCO = "[BANCO/AG/CC]"
TELEFONE = "[TELEFONE]"

_SEM_DIGITO_ANTES = r"(?<![\d])"
_SEM_DIGITO_DEPOIS = r"(?![\d])"

# Chave PIX: o rótulo "pix" seguido do valor (e-mail, telefone, CPF/CNPJ ou aleatória)
_RE_PIX = re.compile(
    r"(?P<rotulo>\b(?:chave\s+)?pix\b\s*(?:[:=\-–]|\b(?:e|é)\b)?\s*)(?P<valor>(?=[^\s,;]*[\d@])[^\s,;]+)",
    re.I,
)
# Chave aleatória (UUID) solta no texto
_RE_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)

_RE_CNPJ = re.compile(
    _SEM_DIGITO_ANTES + r"(?:\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})" + _SEM_DIGITO_DEPOIS
)
_RE_CPF_FORMATADO = re.compile(_SEM_DIGITO_ANTES + r"\d{3}\.\d{3}\.\d{3}-\d{2}" + _SEM_DIGITO_DEPOIS)

# Dados bancários: rótulo + número. O rótulo é mantido para dar contexto à IA.
_RE_BANCARIO = re.compile(
    r"(?P<rotulo>\b(?:ag[eê]ncia|ag|conta(?:\s+corrente|\s+poupan[cç]a|\s+banc[aá]ria)?|"
    r"c/c|c\.c|cc|c/p|banco)(?![a-zà-ü])\.?\s*(?:n[º°o]\.?\s*)?[:\-–]?\s*)"
    r"(?P<valor>\d(?:[\d.\-/ ]{0,20}[\dxX])?)",
    re.I,
)

# Telefones: +55, DDD entre parênteses, ou número com separador
_RE_TELEFONE = re.compile(
    _SEM_DIGITO_ANTES
    + r"(?:\+?55[\s.-]?)?(?:\(\s?\d{2}\s?\)|\d{2})[\s.-]?9?\s?\d{4}[\s.-]\d{4}"
    + _SEM_DIGITO_DEPOIS
)
_RE_TELEFONE_PARENTESES = re.compile(r"\(\s?\d{2}\s?\)\s?9?\s?\d{4}-?\d{4}" + _SEM_DIGITO_DEPOIS)
# 10 ou 11 dígitos colados (celular/fixo com DDD ou CPF sem pontuação)
_RE_ONZE_DIGITOS = re.compile(_SEM_DIGITO_ANTES + r"\d{11}" + _SEM_DIGITO_DEPOIS)
_RE_DEZ_DIGITOS = re.compile(_SEM_DIGITO_ANTES + r"[1-9]\d[2-5]\d{7}" + _SEM_DIGITO_DEPOIS)


def cpf_valido(digitos: str) -> bool:
    """Confere os dígitos verificadores de um CPF (só números)."""
    if len(digitos) != 11 or not digitos.isdigit() or digitos == digitos[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(d) * peso for d, peso in zip(digitos[:tamanho], range(tamanho + 1, 1, -1)))
        dv = (soma * 10) % 11 % 10
        if dv != int(digitos[tamanho]):
            return False
    return True


def _onze_digitos(m: re.Match) -> str:
    return CPF if cpf_valido(m.group(0)) else TELEFONE


def mascarar(texto: str) -> str:
    """Aplica o RN3.1 a um texto. A ordem importa: PIX e CNPJ antes de CPF/telefone."""
    if not texto:
        return texto or ""
    t = _RE_PIX.sub(lambda m: m.group("rotulo") + BANCO, texto)
    t = _RE_UUID.sub(BANCO, t)
    t = _RE_CNPJ.sub(CNPJ, t)
    t = _RE_CPF_FORMATADO.sub(CPF, t)
    t = _RE_BANCARIO.sub(lambda m: m.group("rotulo") + BANCO, t)
    t = _RE_TELEFONE_PARENTESES.sub(TELEFONE, t)
    t = _RE_TELEFONE.sub(TELEFONE, t)
    t = _RE_ONZE_DIGITOS.sub(_onze_digitos, t)
    t = _RE_DEZ_DIGITOS.sub(TELEFONE, t)
    return t


def mascarar_lista(itens: Iterable[str]) -> List[str]:
    """Mascara cada item (ex.: nomes de anexos)."""
    return [mascarar(str(i)) for i in itens or []]


def preparar_para_ia(texto: str, limite: int) -> str:
    """Mascara (RN3.1) e depois trunca (RN3.2), marcando o corte com ``[...]``."""
    return truncar(mascarar(texto or ""), limite)
