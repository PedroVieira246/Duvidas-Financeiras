"""Extração e limpeza do conteúdo do e-mail (F04 – RF02, parte do RF03).

Funções puras, independentes do Outlook: recebem texto/HTML e devolvem
texto. Os marcadores de histórico, assinatura e aviso legal vêm da
configuração (``extracao.*``), não do código.
"""
from __future__ import annotations

import re
import unicodedata
from email.parser import HeaderParser
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from bs4 import BeautifulSoup, NavigableString

from .modelos import EmailRecebido

_BLOCOS = (
    "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "ul", "ol", "section", "article", "header", "footer",
)
_RE_PREFIXO_ASSUNTO = re.compile(r"^\s*((re|res|enc|fw|fwd|rv|tr|resp)\s*(\[\d+\])?\s*:\s*)+", re.I)
_RE_ESPACOS = re.compile(r"[ \t ​]+")


# --------------------------------------------------------------------------- #
# normalização
# --------------------------------------------------------------------------- #
def sem_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento, espaços colapsados – base para comparação."""
    t = sem_acentos(texto).lower()
    t = _RE_ESPACOS.sub(" ", t)
    return re.sub(r"\s*\n\s*", "\n", t).strip()


def limpar_assunto(assunto: str) -> str:
    """Remove prefixos de resposta/encaminhamento (RE:, ENC:, FW:...)."""
    return _RE_PREFIXO_ASSUNTO.sub("", assunto or "").strip()


# --------------------------------------------------------------------------- #
# HTML → texto
# --------------------------------------------------------------------------- #
def html_para_texto(html: str, remover_historico: bool = True) -> str:
    """Converte o corpo HTML em texto simples, preservando quebras de linha.

    Por padrão já descarta blocos de histórico que o Outlook/Gmail marcam no
    HTML. ``remover_historico=False`` mantém o histórico (usado para montar o
    ``historico_resumido`` que vai como contexto para a IA).
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head", "title", "meta", "xml"]):
        tag.decompose()

    # Histórico marcado estruturalmente
    if remover_historico:
        marcador = soup.find(id="divRplyFwdMsg")              # Outlook Web/novo
        if marcador is not None:
            for irmao in list(marcador.find_next_siblings()):
                irmao.decompose()
            marcador.decompose()
        for tag in soup.select("div.gmail_quote, blockquote"):
            tag.decompose()

    for br in soup.find_all("br"):
        br.replace_with(NavigableString("\n"))
    for hr in soup.find_all("hr"):
        hr.replace_with(NavigableString("\n" + "_" * 12 + "\n"))
    for tag in soup.find_all(_BLOCOS):
        tag.insert_before(NavigableString("\n"))
        tag.insert_after(NavigableString("\n"))

    texto = soup.get_text()
    return _compactar(texto)


def _compactar(texto: str) -> str:
    linhas = [_RE_ESPACOS.sub(" ", ln).strip() for ln in texto.replace("\r", "").split("\n")]
    saida: List[str] = []
    vazias = 0
    for ln in linhas:
        if ln:
            vazias = 0
            saida.append(ln)
        else:
            vazias += 1
            if vazias == 1 and saida:
                saida.append("")
    return "\n".join(saida).strip()


# --------------------------------------------------------------------------- #
# histórico, assinatura, aviso legal
# --------------------------------------------------------------------------- #
def _compilar(padroes: Iterable[str]) -> List[re.Pattern]:
    return [re.compile(p, re.I) for p in padroes or []]


_RE_SEPARADOR = re.compile(r"^[_\-=*]{5,}$")
_RE_SO_ENDERECO = re.compile(r"^<?(mailto:)?[^\s<>@]+@[^\s<>@]+>?(\s*<mailto:[^\s<>]+>)?$", re.I)


def remover_preambulo(texto: str, banners: Sequence[str] = ()) -> str:
    """Tira do INÍCIO do texto o aviso que o servidor de e-mail coloca antes da mensagem (v0.3.3).

    Ex.: o aviso de "e-mail externo", seguido do endereço do remetente e de uma
    linha horizontal. Sem isso a linha horizontal era lida como início do
    histórico e o corpo inteiro era descartado (2º teste da operação assistida).

    ``banners`` = ``extracao.banners_ignorados`` (regex sobre a linha normalizada).
    Só mexe no começo: para na primeira linha que não é aviso, endereço solto
    logo após o aviso, linha separadora ou linha vazia. Sem aviso reconhecido,
    só as linhas separadoras/vazias do topo saem.
    """
    padroes = _compilar(banners)
    linhas = (texto or "").split("\n")
    i, viu_banner = 0, False
    while i < len(linhas):
        norm = normalizar(linhas[i])
        if not norm or _RE_SEPARADOR.match(norm):
            i += 1
        elif any(p.search(norm) for p in padroes):
            viu_banner = True
            i += 1
        elif viu_banner and _RE_SO_ENDERECO.match(norm):
            i += 1
        else:
            break
    return "\n".join(linhas[i:]) if i < len(linhas) else (texto or "")


def limpar_corpo(
    texto: str,
    marcadores_historico: Sequence[str] = (),
    marcadores_assinatura: Sequence[str] = (),
    marcadores_aviso_legal: Sequence[str] = (),
    minimo_caracteres: int = 15,
) -> str:
    """Corta o texto no início do histórico, da assinatura ou do aviso legal.

    Se a limpeza deixar menos de ``minimo_caracteres``, devolve o texto
    original (melhor classificar com ruído do que com nada).
    """
    historico = _compilar(marcadores_historico)
    assinatura = _compilar(marcadores_assinatura)
    aviso = _compilar(marcadores_aviso_legal)

    linhas = (texto or "").split("\n")
    mantidas: List[str] = []
    for ln in linhas:
        norm = normalizar(ln)
        if any(p.search(norm) for p in historico):
            break
        if any(p.search(norm) for p in aviso):
            break
        if norm and any(p.match(norm) for p in assinatura) and any(m.strip() for m in mantidas):
            break
        mantidas.append(ln)

    limpo = _compactar("\n".join(mantidas))
    return limpo if len(limpo) >= minimo_caracteres else _compactar(texto or "")


def truncar(texto: str, limite: int, marca: str = "[...]") -> str:
    """Corta ``texto`` em até ``limite`` caracteres, marcando o corte (RN3.2)."""
    texto = texto or ""
    if limite <= 0 or len(texto) <= limite:
        return texto
    corte = max(0, limite - len(marca) - 1)
    return texto[:corte].rstrip() + " " + marca


def extrair_historico(
    texto_completo: str,
    marcadores_historico: Sequence[str] = (),
    limite: int = 2000,
    texto_sem_historico: str = "",
) -> str:
    """Trecho do histórico citado, do 1º marcador em diante, até ``limite`` caracteres.

    Serve só de contexto para a IA (RN1.1): a classificação usa a última
    mensagem. Se nenhum marcador aparecer, mas o HTML tinha histórico marcado
    estruturalmente, usa o que sobra depois de ``texto_sem_historico``.
    """
    historico = _compilar(marcadores_historico)
    linhas = (texto_completo or "").split("\n")
    for i, ln in enumerate(linhas):
        if any(p.search(normalizar(ln)) for p in historico):
            return truncar(_compactar("\n".join(linhas[i:])), limite)
    base = (texto_sem_historico or "").strip()
    completo = (texto_completo or "").strip()
    if base and len(completo) > len(base) and completo.startswith(base):
        return truncar(_compactar(completo[len(base):]), limite)
    return ""


# --------------------------------------------------------------------------- #
# cabeçalhos e respostas automáticas (RF03)
# --------------------------------------------------------------------------- #
def parse_cabecalhos(bruto: str) -> Dict[str, str]:
    """Cabeçalhos de transporte (texto) → dict com chaves minúsculas."""
    if not bruto:
        return {}
    msg = HeaderParser().parsestr(bruto)
    return {k.lower(): str(v) for k, v in msg.items()}


def detectar_resposta_automatica(
    email: EmailRecebido, assuntos: Sequence[str] = ()
) -> Tuple[bool, str]:
    classe = (email.classe_mensagem or "").upper()
    if classe.startswith("REPORT."):
        return True, f"classe {email.classe_mensagem} (relatório de entrega)"
    if "OOFTEMPLATE" in classe or "RULES.REPLYTEMPLATE" in classe:
        return True, f"classe {email.classe_mensagem} (resposta automática)"

    cab = {k.lower(): (v or "").lower() for k, v in (email.cabecalhos or {}).items()}
    auto = cab.get("auto-submitted", "")
    if auto and auto != "no":
        return True, f"cabeçalho Auto-Submitted: {auto}"
    for chave in ("x-autoreply", "x-autorespond", "x-auto-response"):
        if chave in cab:
            return True, f"cabeçalho {chave}"
    if cab.get("precedence", "") in ("bulk", "junk", "auto_reply"):
        return True, f"cabeçalho Precedence: {cab['precedence']}"

    assunto = normalizar(email.assunto)
    for termo in assuntos or ():
        if normalizar(termo) in assunto:
            return True, f"assunto contém '{termo}'"
    return False, ""


def ultima_mensagem(texto: str, marcadores_historico: Sequence[str] = ()) -> str:
    """Texto até o 1º marcador de histórico, SEM cortar assinatura nem rodapé."""
    historico = _compilar(marcadores_historico)
    mantidas: List[str] = []
    for ln in (texto or "").split("\n"):
        if any(p.search(normalizar(ln)) for p in historico):
            break
        mantidas.append(ln)
    return "\n".join(mantidas)


def detectar_mensagem_do_rpa(
    email: EmailRecebido, texto_ultima: str, marcas: Optional[Dict] = None
) -> Tuple[bool, str]:
    """Reconhece mensagens geradas pelo próprio RPA que voltaram para a caixa (v0.2.1).

    Acontece quando a caixa que o robô lê também recebe as respostas dele
    (teste em que você é o "fornecedor") ou cópias dos encaminhamentos e
    avisos. Sem isso, o robô responderia a si mesmo em laço.

    ``marcas`` = ``filtros.mensagens_do_rpa``: ``assuntos`` (regex sobre o
    assunto sem RE:/ENC:, normalizado) e ``textos`` (regex sobre a ÚLTIMA
    mensagem, antes do histórico citado). Assim a resposta de um fornecedor
    que cita o e-mail do robô no histórico NÃO é ignorada.
    """
    marcas = marcas or {}
    if not marcas.get("ativo", True):
        return False, ""
    assunto = normalizar(limpar_assunto(email.assunto))
    for padrao in marcas.get("assuntos", []) or []:
        if re.search(padrao, assunto, re.I):
            return True, f"assunto do próprio RPA ('{padrao}')"
    texto = normalizar(texto_ultima)
    for padrao in marcas.get("textos", []) or []:
        if re.search(padrao, texto, re.I):
            return True, f"texto do próprio RPA ('{padrao}')"
    return False, ""


def processar(
    email: EmailRecebido,
    cfg_extracao: Dict,
    assuntos_auto: Sequence[str] = (),
    marcas_rpa: Optional[Dict] = None,
) -> EmailRecebido:
    """Preenche ``corpo_limpo``, ``resposta_automatica``, ``gerada_pelo_rpa`` e ``historico_resumido``."""
    banners = cfg_extracao.get("banners_ignorados", [])
    base = html_para_texto(email.corpo_html) if email.corpo_html else _compactar(email.corpo_texto_bruto)
    base = remover_preambulo(base, banners)          # v0.3.3: aviso de e-mail externo no topo
    email.corpo_limpo = limpar_corpo(
        base,
        cfg_extracao.get("marcadores_historico", []),
        cfg_extracao.get("marcadores_assinatura", []),
        cfg_extracao.get("marcadores_aviso_legal", []),
    )
    email.resposta_automatica, email.motivo_resposta_automatica = detectar_resposta_automatica(
        email, assuntos_auto
    )
    email.gerada_pelo_rpa, email.motivo_gerada_pelo_rpa = detectar_mensagem_do_rpa(
        email, ultima_mensagem(base, cfg_extracao.get("marcadores_historico", [])), marcas_rpa
    )
    completo = remover_preambulo(
        html_para_texto(email.corpo_html, remover_historico=False), banners
    ) if email.corpo_html else base
    email.historico_resumido = extrair_historico(
        completo,
        cfg_extracao.get("marcadores_historico", []),
        int(cfg_extracao.get("limite_historico", 2000)),
        texto_sem_historico=base,
    )
    return email


def dominio(endereco: str) -> str:
    return endereco.rsplit("@", 1)[-1].lower() if "@" in (endereco or "") else ""


def endereco_permitido(endereco: str, permitidos: Optional[Sequence[str]]) -> bool:
    """``permitidos`` aceita e-mails completos ou domínios iniciados por '@'."""
    if not permitidos:
        return True
    e = (endereco or "").strip().lower()
    for p in permitidos:
        p = (p or "").strip().lower()
        if not p:
            continue
        if p.startswith("@") and e.endswith(p):
            return True
        if e == p:
            return True
    return False
