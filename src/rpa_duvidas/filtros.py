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
        self.dominios = {str(d).strip().lower().lstrip("@") for d in dominios or [] if d and str(d).strip()}
        self.caixas = {str(c).strip().lower() for c in caixas or [] if c and "@" in str(c)}

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
# --------------------------------------------------------------------------- #
SEM_ESCRITORIO = "_Sem escritorio"
# Domínios de e-mail gratuito: na planilha, liberariam QUALQUER remetente desse provedor
DOMINIOS_PUBLICOS = frozenset({
    "gmail.com", "googlemail.com", "hotmail.com", "hotmail.com.br", "outlook.com", "outlook.com.br", "live.com",
    "msn.com", "yahoo.com", "yahoo.com.br", "icloud.com", "bol.com.br", "uol.com.br", "terra.com.br", "ig.com.br",
})
_RE_SEPARADORES = re.compile(r"[;,\s]+")


class ErroEscritorios(Exception):
    """A planilha de escritórios não pôde ser usada: o ciclo não roda (seção 5.9)."""


def normalizar_dominio(valor: str) -> str:
    """Minúsculas, sem espaços e sem ``@``. Um e-mail completo vira o domínio dele."""
    v = re.sub(r"\s+", "", str(valor or "")).lower()
    if "@" in v.strip("@"):
        v = v.rsplit("@", 1)[-1]
    return v.lstrip("@")


@dataclass
class MapaEscritorios:
    """``domínio → escritório`` lido da planilha."""

    mapa: Dict[str, str]
    origem: str = ""
    avisos: List[str] = field(default_factory=list)

    def escritorio(self, remetente: str) -> str:
        r = (remetente or "").strip().lower()
        dominio = r.rsplit("@", 1)[-1] if "@" in r else ""
        return self.mapa.get(dominio, SEM_ESCRITORIO)

    def lista_fornecedores(self) -> ListaFornecedores:
        return ListaFornecedores.de_listas(dominios=self.mapa.keys())

    def __len__(self) -> int:
        return len(self.mapa)


def _nome_coluna(valor) -> str:
    from .extracao import normalizar

    return normalizar(str(valor or ""))


def ler_planilha_escritorios(
    caminho: Path,
    aba: str = "",
    coluna_dominio: str = "Domínio",
    coluna_escritorio: str = "Escritório",
    somente_na_nuvem: Optional[Callable[[Path], bool]] = None,
) -> MapaEscritorios:
    """Lê a planilha externa (SharePoint sincronizado). Qualquer problema → ``ErroEscritorios``.

    O arquivo é copiado para uma pasta temporária antes de abrir (funciona com
    ele aberto no Excel). O cabeçalho é procurado nas 10 primeiras linhas, pelo
    nome das colunas (sem diferenciar maiúsculas nem acentos).
    """
    from openpyxl import load_workbook

    if somente_na_nuvem is None:
        from .tutoriais import _somente_na_nuvem as somente_na_nuvem
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ErroEscritorios(f"Planilha de escritórios não encontrada: {caminho}")
    if somente_na_nuvem(caminho):
        raise ErroEscritorios(
            f"Planilha de escritórios existe só na nuvem (OneDrive): {caminho}. Marque a pasta como "
            "'Sempre manter neste dispositivo'."
        )
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

    mapa: Dict[str, Tuple[str, int]] = {}
    conflitos: Dict[str, List[Tuple[int, str]]] = {}
    avisos: List[str] = []
    for n, linha in enumerate(linhas[cab:], start=cab + 1):
        linha = linha or ()
        bruto_d = linha[idx_d] if idx_d < len(linha) else None
        bruto_e = linha[idx_e] if idx_e < len(linha) else None
        if bruto_d in (None, "") and bruto_e in (None, ""):
            continue
        escritorio = str(bruto_e or "").strip() or SEM_ESCRITORIO
        if escritorio == SEM_ESCRITORIO:
            avisos.append(f"linha {n}: domínio sem escritório ({bruto_d})")
        for parte in _RE_SEPARADORES.split(str(bruto_d or "")):
            dominio = normalizar_dominio(parte)
            if not dominio:
                continue
            if "." not in dominio:
                avisos.append(f"linha {n}: domínio inválido ignorado ({parte})")
                continue
            if dominio in DOMINIOS_PUBLICOS:
                avisos.append(f"linha {n}: {dominio} é um domínio público – qualquer remetente dele será tratado "
                              "como fornecedor")
            if dominio in mapa and mapa[dominio][0] != escritorio:
                conflitos.setdefault(dominio, [(mapa[dominio][1], mapa[dominio][0])]).append((n, escritorio))
                continue
            mapa.setdefault(dominio, (escritorio, n))
    if conflitos:
        detalhes = "; ".join(
            f"{d}: " + ", ".join(f"linha {n} ({e})" for n, e in ocorr) for d, ocorr in sorted(conflitos.items())
        )
        raise ErroEscritorios(f"Domínio com mais de um escritório na planilha de escritórios – {detalhes}")
    if not mapa:
        raise ErroEscritorios(f"Planilha de escritórios sem nenhum domínio: {caminho}")
    return MapaEscritorios({d: e for d, (e, _) in mapa.items()}, str(caminho), avisos)
