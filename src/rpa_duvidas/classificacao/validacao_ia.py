"""Validação da resposta da IA (E4 – regras V1 a V10, seção 5 da especificação funcional).

Funções puras: recebem o texto bruto devolvido pela IA e as listas fechadas
(de ``config/categorias_ia.yaml``) e devolvem a resposta validada ou a lista
de erros. Nada aqui chama a IA nem decide a ação (isso é o ``decisao_ia``).

Resumo das regras:

* V1  JSON válido; cerca Markdown e texto antes/depois são removidos
      (``formato_corrigido = True``, seção 6.5);
* V2  campos obrigatórios presentes e com o tipo correto;
* V3  ``categoria`` na lista fechada;
* V4  ``categorias_secundarias`` na lista, sem repetir a principal, no máximo 3;
* V5  ``tutorial`` é um código de tutorial conhecido ou ``null`` (a coerência
      com a categoria é conferida pela regra D7 – seção 6.5);
* V6  ``confianca`` numérica entre 0 e 1;
* V7  ``acao`` = RESPONDER_TUTORIAL ou ENCAMINHAR_MANUAL;
* V8  ``sinais_excecao`` na lista fechada;
* V9  ``resumo_duvida`` com até 400 caracteres (vazio num caso manual é
      aceito e trocado pelo resumo padrão – seção 6.5);
* V10 ``justificativa`` com até 300 caracteres – excedente é truncado, sem rejeitar.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Collection, Dict, List, Optional, Tuple

RESPONDER_TUTORIAL = "RESPONDER_TUTORIAL"
ENCAMINHAR_MANUAL = "ENCAMINHAR_MANUAL"
ACOES_IA = (RESPONDER_TUTORIAL, ENCAMINHAR_MANUAL)

LIMITE_RESUMO = 400
LIMITE_JUSTIFICATIVA = 300
MAX_SECUNDARIAS = 3

_RE_CERCA = re.compile(r"^\s*```[a-zA-Z]*\s*\n?(?P<conteudo>.*?)\n?\s*```\s*$", re.S)


@dataclass
class RespostaIAValidada:
    """Resposta da IA que passou por V1–V10."""

    categoria: str
    categorias_secundarias: List[str]
    tutorial: Optional[str]
    confianca: float
    acao: str
    sinais_excecao: List[str]
    resumo_duvida: Optional[str]
    justificativa: str
    formato_corrigido: bool = False
    ajustes: List[str] = field(default_factory=list)

    def como_dict(self) -> Dict[str, Any]:
        """Os 8 campos do contrato (seção 5.1), sem os metadados de validação."""
        d = asdict(self)
        d.pop("formato_corrigido")
        d.pop("ajustes")
        return d


@dataclass
class ResultadoValidacao:
    valida: bool
    resposta: Optional[RespostaIAValidada] = None
    erros: List[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# V1 – extração do objeto JSON
# --------------------------------------------------------------------------- #
def extrair_json(texto: str) -> Tuple[Optional[Dict[str, Any]], bool, str]:
    """Devolve ``(objeto, formato_corrigido, erro)``.

    Aceita o JSON puro; dentro de cerca Markdown; ou com texto antes/depois
    (usa o primeiro objeto ``{...}`` que for um JSON válido).
    """
    bruto = (texto or "").strip()
    if not bruto:
        return None, False, "V1: resposta vazia"
    corrigido = False
    m = _RE_CERCA.match(bruto)
    if m:
        bruto, corrigido = m.group("conteudo").strip(), True
    try:
        obj = json.loads(bruto)
        if isinstance(obj, dict):
            return obj, corrigido, ""
    except json.JSONDecodeError:
        pass
    decodificador = json.JSONDecoder()
    pos = bruto.find("{")
    while pos != -1:
        try:
            obj, _ = decodificador.raw_decode(bruto, pos)
            if isinstance(obj, dict):
                return obj, True, ""
        except json.JSONDecodeError:
            pass
        pos = bruto.find("{", pos + 1)
    return None, corrigido, "V1: a resposta não contém um objeto JSON válido"


# --------------------------------------------------------------------------- #
# V2 a V10
# --------------------------------------------------------------------------- #
def _eh_lista_de_texto(valor: Any) -> bool:
    return isinstance(valor, list) and all(isinstance(x, str) for x in valor)


def _eh_numero(valor: Any) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and not math.isnan(float(valor))


def validar_objeto(
    obj: Dict[str, Any],
    codigos_validos: Collection[str],
    tutoriais_validos: Collection[str],
    sinais_validos: Collection[str],
    *,
    formato_corrigido: bool = False,
    limite_resumo: int = LIMITE_RESUMO,
    limite_justificativa: int = LIMITE_JUSTIFICATIVA,
) -> ResultadoValidacao:
    """Aplica V2–V10 a um objeto já decodificado."""
    erros: List[str] = []
    ajustes: List[str] = []

    # V2 – presença e tipo
    tipos = {
        "categoria": (lambda v: isinstance(v, str), "texto"),
        "categorias_secundarias": (_eh_lista_de_texto, "lista de textos"),
        "tutorial": (lambda v: v is None or isinstance(v, str), "texto ou null"),
        "confianca": (_eh_numero, "número"),
        "acao": (lambda v: isinstance(v, str), "texto"),
        "sinais_excecao": (_eh_lista_de_texto, "lista de textos"),
        "justificativa": (lambda v: isinstance(v, str), "texto"),
    }
    for campo, (teste, descricao) in tipos.items():
        if campo not in obj:
            erros.append(f"V2: campo obrigatório ausente: {campo}")
        elif not teste(obj[campo]):
            erros.append(f"V2: {campo} deve ser {descricao}")
    resumo = obj.get("resumo_duvida")
    if resumo is not None and not isinstance(resumo, str):
        erros.append("V2: resumo_duvida deve ser texto ou null")
    if erros:
        return ResultadoValidacao(False, None, erros)

    categoria = obj["categoria"].strip()
    secundarias = [s.strip() for s in obj["categorias_secundarias"]]
    tutorial = obj["tutorial"].strip() if isinstance(obj["tutorial"], str) else None
    confianca = float(obj["confianca"])
    acao = obj["acao"].strip()
    sinais = [s.strip() for s in obj["sinais_excecao"]]
    justificativa = obj["justificativa"].strip()
    resumo = (resumo or "").strip() or None

    # V3
    if categoria not in codigos_validos:
        erros.append(f"V3: categoria '{categoria}' fora da lista {sorted(codigos_validos)}")
    # V4
    fora = [s for s in secundarias if s not in codigos_validos]
    if fora:
        erros.append(f"V4: categorias_secundarias fora da lista: {fora}")
    if categoria in secundarias:
        erros.append("V4: categorias_secundarias repete a categoria principal")
    if len(secundarias) > MAX_SECUNDARIAS:
        erros.append(f"V4: categorias_secundarias com mais de {MAX_SECUNDARIAS} itens")
    secundarias = list(dict.fromkeys(secundarias))
    # V5
    if tutorial is not None and tutorial not in tutoriais_validos:
        erros.append(f"V5: tutorial '{tutorial}' desconhecido")
    # V6
    if not 0.0 <= confianca <= 1.0:
        erros.append(f"V6: confianca {confianca} fora do intervalo 0–1")
    # V7
    if acao not in ACOES_IA:
        erros.append(f"V7: acao '{acao}' inválida")
    # V8
    sinais_fora = [s for s in sinais if s not in sinais_validos]
    if sinais_fora:
        erros.append(f"V8: sinais_excecao fora da lista: {sinais_fora}")
    sinais = list(dict.fromkeys(sinais))
    # V9
    if resumo is not None and len(resumo) > limite_resumo:
        erros.append(f"V9: resumo_duvida com {len(resumo)} caracteres (máximo {limite_resumo})")
    if acao == ENCAMINHAR_MANUAL and not resumo:
        ajustes.append("resumo_duvida vazio num caso manual: será usado o resumo padrão")
    # V10 – não rejeita, só trunca
    if len(justificativa) > limite_justificativa:
        justificativa = justificativa[: limite_justificativa - 3].rstrip() + "..."
        ajustes.append(f"V10: justificativa truncada em {limite_justificativa} caracteres")

    if erros:
        return ResultadoValidacao(False, None, erros)
    if formato_corrigido:
        ajustes.insert(0, "V1: cerca Markdown ou texto extra removido")
    return ResultadoValidacao(
        True,
        RespostaIAValidada(
            categoria=categoria,
            categorias_secundarias=secundarias,
            tutorial=tutorial,
            confianca=confianca,
            acao=acao,
            sinais_excecao=sinais,
            resumo_duvida=resumo,
            justificativa=justificativa,
            formato_corrigido=formato_corrigido,
            ajustes=ajustes,
        ),
        [],
    )


def validar_resposta(
    texto: str,
    codigos_validos: Collection[str],
    tutoriais_validos: Collection[str],
    sinais_validos: Collection[str],
    *,
    limite_resumo: int = LIMITE_RESUMO,
    limite_justificativa: int = LIMITE_JUSTIFICATIVA,
) -> ResultadoValidacao:
    """V1 a V10 sobre o texto bruto devolvido pela IA."""
    obj, corrigido, erro = extrair_json(texto)
    if obj is None:
        return ResultadoValidacao(False, None, [erro])
    return validar_objeto(
        obj, codigos_validos, tutoriais_validos, sinais_validos,
        formato_corrigido=corrigido, limite_resumo=limite_resumo, limite_justificativa=limite_justificativa,
    )
