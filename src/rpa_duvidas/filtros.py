"""Filtros de entrada (F05 parcial – RF03; etapa E2 da especificação funcional).

* respostas automáticas são detectadas na extração (extracao.py);
* e-mails já processados são barrados pelo registro (registro.py, RNF01);
* aqui: remetente está ou não na lista de fornecedores;
* v0.2.0: remetente interno (RN2.2) e spam pelo cabeçalho SCL (RN2.3).

A lista oficial ainda não chegou (S06); em dev/demo usam-se listas de teste.
v0.3.0: planilha de domínios dos escritórios (D06, seção 5.9) – substitui o
``fornecedores.yaml`` e define o escritório de cada e-mail.

Domínios internos, caixas da automação e o limite de spam vêm da configuração
(``filtros.dominios_internos``, ``caixa.conta``/``caixa.enviar_em_nome_de`` e
``filtros.spam``). Com as listas vazias e o spam desligado (padrão), nada muda
em relação à v0.1.0.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple


class ListaFornecedores:
    def __init__(self, dados: Dict):
        self.emails = {str(e).strip().lower() for e in (dados.get("emails") or []) if e}
        self.dominios = {str(d).strip().lower().lstrip("@") for d in (dados.get("dominios") or []) if d}

    @classmethod
    def de_listas(cls, emails: Iterable[str] = (), dominios: Iterable[str] = ()) -> "ListaFornecedores":
        return cls({"emails": list(emails), "dominios": list(dominios)})

    def conhecido(self, remetente: str) -> bool:
        r = (remetente or "").strip().lower()
        if not r:
            return False
        if r in self.emails:
            return True
        dominio = r.rsplit("@", 1)[-1]
        return dominio in self.dominios

    def __len__(self) -> int:
        return len(self.emails) + len(self.dominios)


class FiltroInterno:
    """RN2.2: e-mail escrito pela própria Companhia não é dúvida de fornecedor."""

    def __init__(self, dominios: Iterable[str] = (), caixas: Iterable[str] = ()):
        itens = [str(d).strip().lower() for d in dominios or [] if d and str(d).strip()]
        # v0.3.1: um e-mail completo na lista de domínios internos vale como caixa (não como domínio)
        self.dominios = {d.lstrip("@") for d in itens if "@" not in d.lstrip("@")}
        self.caixas = {str(c).strip().lower() for c in caixas or [] if c and "@" in str(c)}
        self.caixas |= {d for d in itens if "@" in d.lstrip("@")}

    def interno(self, remetente: str) -> Tuple[bool, str]:
        r = (remetente or "").strip().lower()
        if not r:
            return False, ""
        if r in self.caixas:
            return True, "remetente é a própria caixa da automação"
        dominio = r.rsplit("@", 1)[-1] if "@" in r else ""
        if dominio and any(dominio == d or dominio.endswith("." + d) for d in self.dominios):
            return True, f"remetente de domínio interno (@{dominio})"
        return False, ""

    def __len__(self) -> int:
        return len(self.dominios) + len(self.caixas)


class FiltroSpam:
    """RN2.3 (opcional): nível de confiança de spam do Exchange (SCL) no cabeçalho."""

    def __init__(self, ativo: bool = False, cabecalho: str = "x-ms-exchange-organization-scl", limite: int = 5):
        self.ativo = bool(ativo)
        self.cabecalho = (cabecalho or "").strip().lower()
        self.limite = int(limite)

    @classmethod
    def de_config(cls, conf: Optional[Mapping]) -> "FiltroSpam":
        conf = conf or {}
        return cls(
            bool(conf.get("ativo", False)),
            str(conf.get("cabecalho", "x-ms-exchange-organization-scl")),
            int(conf.get("limite_scl", 5)),
        )

    def spam(self, cabecalhos: Mapping[str, str]) -> Tuple[bool, str]:
        if not self.ativo:
            return False, ""
        bruto = {str(k).lower(): str(v) for k, v in (cabecalhos or {}).items()}.get(self.cabecalho, "").strip()
        try:
            scl = int(bruto)
        except ValueError:
            return False, ""
        if scl >= self.limite:
            return True, f"cabeçalho {self.cabecalho} = {scl} (limite {self.limite})"
        return False, ""


# --------------------------------------------------------------------------- #
# v0.3.0 – planilha de escritórios (D06, seção 5.9)
# v0.3.1 – leitura tolerante: a planilha real é uma lista de E-MAILS, com nomes
#          de escritório variando para o mesmo domínio. Problemas de linha viram
#          avisos no log; o ciclo só deixa de rodar se a planilha for inutilizável.
# --------------------------------------------------------------------------- #
SEM_ESCRITORIO = "_Sem escritorio"
# Domínios de e-mail gratuito: na planilha, liberariam QUALQUER remetente desse provedor
DOMINIOS_PUBLICOS = frozenset({
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br", "live.com",
    "msn.com", "yahoo.com", "yahoo.com.br", "icloud.com", "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br",
})
# Textos que o Excel/PROCV deixa na coluna do escritório quando não achou o nome
ERROS_EXCEL = frozenset({"#n/a", "#n/d", "#na", "#ref!", "#value!", "#valor!", "#name?", "#nome?", "#div/0!",
                         "#null!", "#nulo!", "#num!", "#spill!", "#calc!", "#field!", "#getting_data"})
# v0.3.1 – valores da coluna do escritório que significam "sem escritório" (configurável:
# escritorios.valores_sem_escritorio). Comparação sem acento e sem diferenciar maiúsculas.
VALORES_SEM_ESCRITORIO_PADRAO = ("CNPJ não consta na base de fornecedores",)
_RE_SEPARADORES = re.compile(r"[;,\s]+")
_RE_SEPARADOR_EXPLICITO = re.compile(r"[;,]")
_RE_INVISIVEIS = re.compile(r"[​‌‍⁠﻿­]")
_RE_DOMINIO = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")
_RE_LOCAL = re.compile(r"^[a-z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}$")


class ErroEscritorios(Exception):
    """A planilha de escritórios não pôde ser usada: o ciclo não roda (seção 5.9)."""


def valores_sem_escritorio(cfg) -> Tuple[str, ...]:
    """``escritorios.valores_sem_escritorio`` da configuração (ausente = padrão da v0.3.1)."""
    valores = cfg.get("escritorios.valores_sem_escritorio", None)
    if valores is None:
        return VALORES_SEM_ESCRITORIO_PADRAO
    return tuple(str(v) for v in (valores if isinstance(valores, (list, tuple)) else [valores]) if v)


def _limpar_celula(valor) -> str:
    """NFKC, sem caracteres invisíveis e com espaço comum no lugar do não separável."""
    t = unicodedata.normalize("NFKC", str(valor if valor is not None else ""))
    return _RE_INVISIVEIS.sub("", t).replace(" ", " ").strip()


def normalizar_dominio(valor: str) -> str:
    """Minúsculas, sem espaços e sem ``@``. Um e-mail completo vira o domínio dele."""
    v = re.sub(r"\s+", "", _limpar_celula(valor)).lower()
    if "@" in v.strip("@"):
        v = v.rsplit("@", 1)[-1]
    return v.lstrip("@")


def normalizar_email(valor: str) -> str:
    """``e-mail`` em minúsculas, sem espaços nem invisíveis; vazio se não for um e-mail válido."""
    v = re.sub(r"\s+", "", _limpar_celula(valor)).lower().strip(".")
    if v.count("@") != 1:
        return ""
    local, dominio = v.split("@")
    return v if local and _RE_LOCAL.match(local) and _RE_DOMINIO.match(dominio) else ""


def dominio_valido(dominio: str) -> bool:
    return bool(_RE_DOMINIO.match(dominio or ""))


def chave_nome_escritorio(nome: str) -> str:
    """Base para comparar nomes: sem acento/pontuação, ``&`` = ``E``, espaços colapsados."""
    from .extracao import normalizar

    t = normalizar(str(nome or "")).replace("&", " e ")
    t = re.sub(r"[^0-9a-z ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _resolver_escritorio(candidatos: List[Tuple[str, int]]) -> Tuple[str, bool]:
    """Escolhe o escritório de um domínio/e-mail com várias linhas: ``(nome, ambíguo)``.

    * linhas sem escritório (vazio, #N/A, "CNPJ não consta...") não contam se houver nome válido;
    * nomes iguais depois de normalizar, ou um prefixo do outro (nome truncado em 35
      caracteres no cadastro, "& / E"), são o mesmo escritório → vale o mais frequente;
    * nomes realmente diferentes → ambíguo (``SEM_ESCRITORIO``), sem derrubar o ciclo.
    """
    validos = [(e, n) for e, n in candidatos if e != SEM_ESCRITORIO]
    if not validos:
        return SEM_ESCRITORIO, False
    chaves = sorted({chave_nome_escritorio(e) for e, _ in validos}, key=len)
    grupos: List[str] = []
    for k in chaves:
        if not any(k == g or k.startswith(g + " ") for g in grupos):
            grupos.append(k)
    if len(grupos) > 1:
        return SEM_ESCRITORIO, True
    contagem: Dict[str, int] = {}
    primeira: Dict[str, int] = {}
    for e, n in validos:
        contagem[e] = contagem.get(e, 0) + 1
        primeira.setdefault(e, n)
    return sorted(contagem, key=lambda e: (-contagem[e], primeira[e]))[0], False


@dataclass
class MapaEscritorios:
    """``domínio → escritório`` (e, desde a v0.3.1, ``e-mail → escritório``) lido da planilha.

    O e-mail exato tem prioridade; o domínio é o retorno para endereços que não estão
    na planilha. E-mails de domínio público (gmail etc.) valem só pelo endereço exato.
    """

    mapa: Dict[str, str]
    origem: str = ""
    avisos: List[str] = field(default_factory=list)
    emails: Dict[str, str] = field(default_factory=dict)
    linhas_invalidas: List[str] = field(default_factory=list)
    dominios_ambiguos: Dict[str, List[str]] = field(default_factory=dict)
    linhas_lidas: int = 0

    def escritorio(self, remetente: str) -> str:
        r = (remetente or "").strip().lower()
        if r in self.emails:
            return self.emails[r]
        dominio = r.rsplit("@", 1)[-1] if "@" in r else ""
        return self.mapa.get(dominio, SEM_ESCRITORIO)

    def lista_fornecedores(self) -> ListaFornecedores:
        return ListaFornecedores.de_listas(emails=self.emails.keys(), dominios=self.mapa.keys())

    def resumo(self) -> str:
        escritorios = (set(self.mapa.values()) | set(self.emails.values())) - {SEM_ESCRITORIO}
        return (f"{len(self.mapa)} domínio(s), {len(self.emails)} e-mail(s), {len(escritorios)} escritório(s) | "
                f"{self.linhas_lidas} linha(s) lida(s), {len(self.linhas_invalidas)} ignorada(s), "
                f"{len(self.dominios_ambiguos)} domínio(s) ambíguo(s)")

    def __len__(self) -> int:
        return len(self.mapa) + len(self.emails)


def _nome_coluna(valor) -> str:
    from .extracao import normalizar

    return normalizar(str(valor or ""))


def _escritorio_da_celula(bruto, sem_escritorio: frozenset) -> Tuple[str, str]:
    """``(escritório, motivo)``: motivo preenchido quando a célula não traz um nome utilizável."""
    texto = re.sub(r"[ \t]+", " ", _limpar_celula(bruto))
    if not texto:
        return SEM_ESCRITORIO, "sem escritório"
    if texto.lower() in ERROS_EXCEL or (texto.startswith("#") and texto.endswith(("!", "?", "A", "a"))
                                        and len(texto) <= 8):
        return SEM_ESCRITORIO, f"escritório com erro do Excel ({texto})"
    if chave_nome_escritorio(texto) in sem_escritorio:
        return SEM_ESCRITORIO, f"escritório marcado como '{texto}'"
    return texto, ""


def ler_planilha_escritorios(
    caminho: Path,
    aba: str = "",
    coluna_dominio: str = "Domínio",
    coluna_escritorio: str = "Escritório",
    somente_na_nuvem: Optional[Callable[[Path], bool]] = None,
    valores_sem_escritorio: Iterable[str] = VALORES_SEM_ESCRITORIO_PADRAO,
) -> MapaEscritorios:
    """Lê a planilha externa (SharePoint sincronizado).

    Arquivo/aba/colunas inacessíveis ou nenhuma linha válida → ``ErroEscritorios``
    (o ciclo não roda). Problemas de linha (texto que não é e-mail nem domínio,
    escritório #N/A, mesmo domínio com escritórios diferentes, duplicidades) viram
    avisos com o número da linha e NÃO interrompem a execução (v0.3.1).

    O arquivo é copiado para uma pasta temporária antes de abrir (funciona com
    ele aberto no Excel). O cabeçalho é procurado nas 10 primeiras linhas, pelo
    nome das colunas (sem diferenciar maiúsculas nem acentos).
    """
    from openpyxl import load_workbook

    from . import nuvem

    if somente_na_nuvem is None:
        from .tutoriais import _somente_na_nuvem as somente_na_nuvem
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ErroEscritorios(f"Planilha de escritórios não encontrada: {caminho}")
    try:                                   # v0.3.2: só na nuvem → baixa antes de abrir
        nuvem.garantir_local(caminho, somente_na_nuvem=somente_na_nuvem)
    except nuvem.ErroNuvem as e:
        raise ErroEscritorios(f"Planilha de escritórios: {e}") from e
    pasta_tmp = Path(tempfile.mkdtemp(prefix="rpa_esc_"))
    try:
        try:
            copia = pasta_tmp / "escritorios.xlsx"
            shutil.copy2(caminho, copia)
        except OSError as e:
            raise ErroEscritorios(f"Planilha de escritórios bloqueada ou sem permissão de leitura: {caminho} ({e})") from e
        try:
            wb = load_workbook(copia, read_only=True, data_only=True)
        except Exception as e:
            raise ErroEscritorios(f"Não foi possível abrir a planilha de escritórios {caminho}: {e}") from e
        try:
            if aba:
                if aba not in wb.sheetnames:
                    raise ErroEscritorios(f"Aba '{aba}' não existe na planilha de escritórios "
                                          f"(abas: {', '.join(wb.sheetnames)})")
                ws = wb[aba]
            else:
                ws = wb[wb.sheetnames[0]]
            linhas = list(ws.iter_rows(values_only=True))
        finally:
            wb.close()
    finally:
        shutil.rmtree(pasta_tmp, ignore_errors=True)

    alvo_d, alvo_e = _nome_coluna(coluna_dominio), _nome_coluna(coluna_escritorio)
    cab, idx_d, idx_e = 0, None, None
    for n, linha in enumerate(linhas[:10], start=1):
        nomes = [_nome_coluna(c) for c in (linha or ())]
        if alvo_d in nomes and alvo_e in nomes:
            cab, idx_d, idx_e = n, nomes.index(alvo_d), nomes.index(alvo_e)
            break
    if not cab:
        cab_vista = [str(c) for c in (linhas[0] if linhas else ()) if c not in (None, "")]
        faltam = [c for c, a in ((coluna_dominio, alvo_d), (coluna_escritorio, alvo_e))
                  if not any(a in [_nome_coluna(x) for x in (l or ())] for l in linhas[:10])]
        raise ErroEscritorios(
            f"Coluna(s) {', '.join(repr(c) for c in faltam) or repr(coluna_dominio)} não encontrada(s) na planilha de "
            f"escritórios {caminho.name} (cabeçalho: {', '.join(cab_vista) or 'vazio'})"
        )

    sem_esc = frozenset(chave_nome_escritorio(v) for v in (valores_sem_escritorio or ()) if str(v or "").strip())
    por_email: Dict[str, List[Tuple[str, int]]] = {}
    por_dominio: Dict[str, List[Tuple[str, int]]] = {}
    avisos: List[str] = []
    invalidas: List[str] = []
    lidas = 0
    for n, linha in enumerate(linhas[cab:], start=cab + 1):
        linha = linha or ()
        bruto_d = linha[idx_d] if idx_d < len(linha) else None
        bruto_e = linha[idx_e] if idx_e < len(linha) else None
        celula = _limpar_celula(bruto_d)
        if not celula and not _limpar_celula(bruto_e):
            continue
        lidas += 1
        resumo_celula = celula if len(celula) <= 60 else celula[:57] + "..."
        if not celula:
            invalidas.append(f"linha {n}: sem e-mail/domínio (escritório '{_limpar_celula(bruto_e)}') – ignorada")
            continue
        escritorio, motivo = _escritorio_da_celula(bruto_e, sem_esc)
        partes = [p for p in _RE_SEPARADORES.split(celula) if p.strip("@")]
        validas: List[Tuple[str, str]] = []          # (tipo, valor)
        ruins: List[str] = []
        for parte in partes:
            if "@" in parte.strip("@"):
                email = normalizar_email(parte)
                (validas.append(("email", email)) if email else ruins.append(parte))
            else:
                dominio = normalizar_dominio(parte).strip(".")
                (validas.append(("dominio", dominio)) if dominio_valido(dominio) else ruins.append(parte))
        if ruins and (not validas or not _RE_SEPARADOR_EXPLICITO.search(celula)):
            # sem ";"/"," entre os itens não dá para saber o que é e-mail (ex.: nome e sobrenome separados por espaço antes do arroba)
            invalidas.append(f"linha {n}: '{resumo_celula}' não é e-mail nem domínio válido – ignorada")
            continue
        if ruins:
            avisos.append(f"linha {n}: parte(s) inválida(s) ignorada(s): {', '.join(ruins)}")
        if motivo:
            avisos.append(f"linha {n}: {motivo} – {resumo_celula} vale como fornecedor, sem escritório")
        for tipo, valor in validas:
            if tipo == "email":
                por_email.setdefault(valor, []).append((escritorio, n))
                dominio = valor.rsplit("@", 1)[-1]
                if dominio in DOMINIOS_PUBLICOS:      # gmail etc.: só o endereço exato
                    avisos.append(f"linha {n}: {valor} é de domínio público ({dominio}) – só este endereço é "
                                  "reconhecido como fornecedor")
                    continue
                por_dominio.setdefault(dominio, []).append((escritorio, n))
            else:
                if valor in DOMINIOS_PUBLICOS:
                    avisos.append(f"linha {n}: {valor} é um domínio público – qualquer remetente dele será tratado "
                                  "como fornecedor")
                por_dominio.setdefault(valor, []).append((escritorio, n))

    emails: Dict[str, str] = {}
    for email, ocorr in por_email.items():
        nome, ambiguo = _resolver_escritorio(ocorr)
        emails[email] = nome
        if ambiguo:
            avisos.append(f"{email} com mais de um escritório – " + ", ".join(f"linha {n} ({e})" for e, n in ocorr)
                          + f": fica como {SEM_ESCRITORIO}")
        elif len(ocorr) > 1:
            avisos.append(f"{email} repetido nas linhas {', '.join(str(n) for _, n in ocorr)} – considerado uma vez")
    mapa: Dict[str, str] = {}
    ambiguos: Dict[str, List[str]] = {}
    for dominio, ocorr in por_dominio.items():
        nome, ambiguo = _resolver_escritorio(ocorr)
        mapa[dominio] = nome
        if ambiguo:
            ambiguos[dominio] = [f"linha {n} ({e})" for e, n in ocorr]
            avisos.append(f"domínio {dominio} com mais de um escritório – {', '.join(ambiguos[dominio])}: "
                          f"e-mails da planilha usam o escritório da própria linha; outros endereços desse "
                          f"domínio ficam como {SEM_ESCRITORIO}")
    if not mapa and not emails:
        raise ErroEscritorios(f"Planilha de escritórios sem nenhum e-mail/domínio válido: {caminho}"
                              + (f" ({len(invalidas)} linha(s) inválida(s))" if invalidas else ""))
    return MapaEscritorios(mapa, str(caminho), avisos + invalidas, emails, invalidas, ambiguos, lidas)
