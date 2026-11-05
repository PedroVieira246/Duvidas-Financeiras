"""Leitura do ``configuracao.xlsx`` (v0.3.0 – seção 4.2, tarefa T03).

``ler_configuracao_xlsx(caminho) -> (dados, erros)``

* ``dados``: pedaço do dicionário de configuração no MESMO formato que o
  ``Config`` já usa (``caixa.*``, ``execucao.*`` …). Os YAMLs referenciados
  por caminho (termos e tutoriais) vêm em ``dados["_inline"][chave]``.
* ``erros``: lista de ``ErroCelula`` (aba, linha, coluna, mensagem). Qualquer
  erro impede a execução (critério de aceite 2).

O arquivo é copiado para uma pasta temporária antes de abrir: a leitura
funciona mesmo com a planilha aberta no Excel.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import config_xlsx_esquema as E

_RE_EMAIL = re.compile(r"^[^@\s;,<>]+@[^@\s;,<>]+\.[^@\s;,<>]+$")
_RE_CAMPO = re.compile(r"\{([^{}]*)\}")
_RE_CODIGO_RESP = re.compile(r"^RESP_[A-Z0-9_]+$")


@dataclass(frozen=True)
class ErroCelula:
    aba: str
    linha: int
    coluna: str
    mensagem: str

    def __str__(self) -> str:
        if self.linha and self.coluna:
            return f'Aba {self.aba}, linha {self.linha}, coluna "{self.coluna}": {self.mensagem}'
        if self.linha:
            return f"Aba {self.aba}, linha {self.linha}: {self.mensagem}"
        return f"Aba {self.aba}: {self.mensagem}"


class _Aviso(Exception):
    """Valor inválido numa célula (vira ErroCelula)."""


# --------------------------------------------------------------------------- #
# conversões de célula
# --------------------------------------------------------------------------- #
def eh_placeholder(valor: Any) -> bool:
    return isinstance(valor, str) and E.PLACEHOLDER in valor.upper()


def texto(valor: Any) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    if isinstance(valor, (datetime, date)):
        return valor.strftime("%Y-%m-%d")
    return str(valor).strip()


def sim_nao(valor: Any) -> bool:
    if isinstance(valor, bool):
        return valor
    t = texto(valor).lower()
    if t in E.VERDADEIROS:
        return True
    if t in E.FALSOS:
        return False
    raise _Aviso(f"use S ou N (recebido: {texto(valor)!r})")


def data_iso(valor: Any) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    t = texto(valor)
    try:
        return datetime.strptime(t, "%Y-%m-%d").date().isoformat()
    except ValueError:
        raise _Aviso(f"data inválida (use data do Excel ou AAAA-MM-DD; recebido: {t!r})") from None


def inteiro(valor: Any, minimo: int = 1) -> int:
    try:
        if isinstance(valor, bool):
            raise ValueError
        n = float(str(valor).replace(",", ".")) if not isinstance(valor, (int, float)) else float(valor)
        if not n.is_integer():
            raise ValueError
        n = int(n)
    except (TypeError, ValueError):
        raise _Aviso(f"número inteiro inválido: {texto(valor)!r}") from None
    if n < minimo:
        raise _Aviso(f"deve ser maior ou igual a {minimo}")
    return n


def decimal(valor: Any, minimo: float = 0.0, maximo: Optional[float] = None, *, excluir_minimo: bool = False) -> float:
    try:
        if isinstance(valor, bool):
            raise ValueError
        n = float(valor) if isinstance(valor, (int, float)) else float(texto(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise _Aviso(f"número inválido: {texto(valor)!r}") from None
    if n < minimo or (excluir_minimo and n == minimo) or (maximo is not None and n > maximo):
        faixa = f"maior que {minimo:g}" if excluir_minimo else f"entre {minimo:g} e {maximo:g}" if maximo is not None \
            else f"maior ou igual a {minimo:g}"
        raise _Aviso(f"deve ser {faixa}")
    return int(n) if n.is_integer() and not isinstance(valor, float) else n


def email(valor: Any) -> str:
    t = texto(valor).lower()
    if not _RE_EMAIL.match(t):
        raise _Aviso(f"e-mail inválido: {texto(valor)!r}")
    return t


def normalizar_dominio(valor: str) -> str:
    return re.sub(r"\s+", "", str(valor or "")).lower().lstrip("@")


def _definir(dados: Dict[str, Any], caminho: str, valor: Any) -> None:
    partes = caminho.split(".")
    atual = dados
    for p in partes[:-1]:
        atual = atual.setdefault(p, {})
    atual[partes[-1]] = valor


# --------------------------------------------------------------------------- #
# leitura de uma aba em tabela
# --------------------------------------------------------------------------- #
class _Tabela:
    def __init__(self, aba: str, linhas: List[Tuple], erros: List[ErroCelula], linha_cabecalho: int = 1):
        self.aba, self.erros = aba, erros
        self.linha_cabecalho = linha_cabecalho
        cab = [texto(c) for c in (linhas[linha_cabecalho - 1] if len(linhas) >= linha_cabecalho else ())]
        self.indice = {nome: i for i, nome in enumerate(cab) if nome}
        self.ok = True
        for nome in E.COLUNAS[aba]:
            if nome not in self.indice:
                erros.append(ErroCelula(aba, linha_cabecalho, nome, "coluna ausente no cabeçalho"))
                self.ok = False
        self.linhas = linhas[linha_cabecalho:]

    def registros(self):
        """(número da linha no Excel, função de acesso por coluna) para cada linha não vazia."""
        for n, linha in enumerate(self.linhas, start=self.linha_cabecalho + 1):
            if all(texto(c) == "" for c in linha):
                continue

            def celula(nome: str, _linha=linha):
                i = self.indice[nome]
                return _linha[i] if i < len(_linha) else None

            yield n, celula

    def erro(self, linha: int, coluna: str, mensagem: str) -> None:
        self.erros.append(ErroCelula(self.aba, linha, coluna, mensagem))


def _valor(tab: _Tabela, n: int, coluna: str, bruto: Any, conversor, *, obrigatorio: bool = False, **kw):
    """Converte uma célula registrando o erro; devolve None se vazia/ inválida."""
    if eh_placeholder(bruto):
        tab.erro(n, coluna, f"valor ainda não preenchido ({E.PLACEHOLDER})")
        return None
    if E.valor_padrao_vazio(bruto):
        if obrigatorio:
            tab.erro(n, coluna, "preenchimento obrigatório")
        return None
    try:
        return conversor(bruto, **kw)
    except _Aviso as e:
        tab.erro(n, coluna, str(e))
        return None


# --------------------------------------------------------------------------- #
def ler_configuracao_xlsx(caminho: Path) -> Tuple[Dict[str, Any], List[ErroCelula]]:
    from openpyxl import load_workbook

    caminho = Path(caminho)
    erros: List[ErroCelula] = []
    pasta_tmp = Path(tempfile.mkdtemp(prefix="rpa_cfg_"))
    try:
        copia = pasta_tmp / "configuracao.xlsx"
        shutil.copy2(caminho, copia)
        wb = load_workbook(copia, read_only=True, data_only=True)
        try:
            abas = {nome: list(wb[nome].iter_rows(values_only=True)) for nome in wb.sheetnames}
        finally:
            wb.close()
    finally:
        shutil.rmtree(pasta_tmp, ignore_errors=True)
    return converter(abas, erros, origem=str(caminho))


def converter(abas: Dict[str, List[Tuple]], erros: Optional[List[ErroCelula]] = None,
              origem: str = "") -> Tuple[Dict[str, Any], List[ErroCelula]]:
    """Converte o conteúdo das abas (listas de linhas) no dicionário de configuração."""
    erros = [] if erros is None else erros
    for aba in E.ABAS:
        if aba not in abas:
            erros.append(ErroCelula(aba, 0, "", "aba ausente no arquivo"))
    dados: Dict[str, Any] = {"_inline": {}, "_origem_xlsx": {}, "configuracao_xlsx": {"lido_de": origem}}
    if E.ABA_LEIAME in abas:
        _leiame(abas[E.ABA_LEIAME], dados, erros)
    if E.ABA_GERAL in abas:
        _geral(abas[E.ABA_GERAL], dados, erros)
    categorias: Dict[str, Dict[str, Any]] = {}
    if E.ABA_CATEGORIAS in abas:
        categorias = _categorias(abas[E.ABA_CATEGORIAS], dados, erros)
    if E.ABA_PALAVRAS in abas:
        _palavras(abas[E.ABA_PALAVRAS], dados, erros)
    textos: Dict[str, Dict[str, str]] = {}
    if E.ABA_TEXTOS in abas:
        textos = _textos(abas[E.ABA_TEXTOS], dados, erros)
    if E.ABA_TUTORIAIS in abas:
        _tutoriais(abas[E.ABA_TUTORIAIS], dados, erros, categorias)
    if E.ABA_DESTINATARIOS in abas:
        _destinatarios(abas[E.ABA_DESTINATARIOS], dados, erros)
    if E.ABA_FILTROS in abas:
        _filtros(abas[E.ABA_FILTROS], dados, erros)
    # referências cruzadas Categorias → Textos
    for cod, c in categorias.items():
        n = c.pop("_linha", 0)
        if c.get("codigo_texto") and c["codigo_texto"] not in textos:
            erros.append(ErroCelula(E.ABA_CATEGORIAS, n, "Código do texto",
                                    f"código {c['codigo_texto']} não existe na aba Textos"))
        if c.get("acao") == "RESPONDER_TEXTO" and not c.get("codigo_texto"):
            erros.append(ErroCelula(E.ABA_CATEGORIAS, n, "Código do texto",
                                    "obrigatório com a ação RESPONDER_TEXTO"))
    return dados, erros


# --------------------------------------------------------------------------- #
# abas
# --------------------------------------------------------------------------- #
def _leiame(linhas: List[Tuple], dados: Dict, erros: List[ErroCelula]) -> None:
    for n, linha in enumerate(linhas, start=1):
        if linha and texto(linha[0]) == "versao_modelo":
            versao = texto(linha[1] if len(linha) > 1 else "")
            dados["configuracao_xlsx"]["versao_modelo"] = versao
            if versao.split(".")[:2] != E.VERSAO_MODELO.split(".")[:2]:
                erros.append(ErroCelula(E.ABA_LEIAME, n, "B",
                                        f"modelo incompatível: versão {versao or '(vazia)'}; este robô aceita "
                                        f"{E.VERSAO_MODELO}. Use o modelo que acompanha o executável."))
            return
    erros.append(ErroCelula(E.ABA_LEIAME, 0, "", "versao_modelo não encontrada (modelo incompatível)"))


def _geral(linhas: List[Tuple], dados: Dict, erros: List[ErroCelula]) -> None:
    tab = _Tabela(E.ABA_GERAL, linhas, erros)
    if not tab.ok:
        return
    vistos: Dict[str, int] = {}
    valores: Dict[str, Any] = {}
    for n, cel in tab.registros():
        chave = texto(cel("Chave"))
        campo = E.CAMPOS_GERAL_POR_CHAVE.get(chave)
        if campo is None:
            tab.erro(n, "Chave", f"chave desconhecida: {chave!r}")
            continue
        if chave in vistos:
            tab.erro(n, "Chave", f"chave repetida (já na linha {vistos[chave]})")
            continue
        vistos[chave] = n
        dados["_origem_xlsx"][f"Geral:{chave}"] = n
        bruto = cel("Valor")
        v = _geral_valor(tab, n, campo, bruto)
        if v is None:
            continue
        valores[chave] = v
        _definir(dados, campo.destino, v)
    for campo in E.CAMPOS_GERAL:
        if campo.chave not in vistos:
            erros.append(ErroCelula(E.ABA_GERAL, 0, "", f"linha da chave {campo.chave} ausente"))
    # D03: o destino padrão não pode ser a própria caixa
    if valores.get("email_destino_padrao") and valores.get("email_destino_padrao") == valores.get("email_caixa_entrada"):
        tab.erro(vistos["email_destino_padrao"], "Valor", "o e-mail destino padrão precisa ser diferente do e-mail da caixa")


def _geral_valor(tab: _Tabela, n: int, campo: E.CampoGeral, bruto: Any) -> Any:
    if eh_placeholder(bruto):
        tab.erro(n, "Valor", f"{campo.chave}: valor ainda não preenchido ({E.PLACEHOLDER})")
        return None
    if E.valor_padrao_vazio(bruto):
        # vazio = padrão do settings/perfil; obrigatória sem padrão é erro
        if campo.obrigatoria and not campo.padrao_doc:
            tab.erro(n, "Valor", f"{campo.chave}: preenchimento obrigatório")
        return None
    try:
        if campo.chave == "modo_execucao":
            t = texto(bruto).upper()
            if t not in E.MODOS_EXECUCAO:
                raise _Aviso(f"use {' ou '.join(E.MODOS_EXECUCAO)}")
            return t == "REAL"
        if campo.chave == "destino_respostas":
            t = texto(bruto).upper()
            if t in E.DESTINO_RESERVADO:
                raise _Aviso(f"{t} fica reservado para a próxima etapa; na v0.3.0 use TESTE")
            if t not in E.DESTINO_RESPOSTAS:
                raise _Aviso("use TESTE")
            return t
        if campo.chave == "ia_ligada":
            if sim_nao(bruto):
                raise _Aviso("IA desligada nesta etapa (use N)")
            return "palavras_chave"
        if campo.tipo == "email":
            return email(bruto)
        if campo.tipo == "sn":
            return sim_nao(bruto)
        if campo.tipo == "data":
            return data_iso(bruto)
        if campo.tipo == "inteiro":
            return inteiro(bruto, 1)
        if campo.tipo == "decimal":
            return float(decimal(bruto, 0.0, 1.0))
        if campo.tipo == "lista":
            t = texto(bruto).upper()
            if t not in E.LISTAS[campo.lista]:
                raise _Aviso(f"valor fora da lista ({', '.join(E.LISTAS[campo.lista])})")
            return t
        return texto(bruto)
    except _Aviso as e:
        tab.erro(n, "Valor", f"{campo.chave}: {e}")
        return None


def _categorias(linhas: List[Tuple], dados: Dict, erros: List[ErroCelula]) -> Dict[str, Dict[str, Any]]:
    tab = _Tabela(E.ABA_CATEGORIAS, linhas, erros)
    saida: Dict[str, Dict[str, Any]] = {}
    if not tab.ok:
        return saida
    for n, cel in tab.registros():
        cod = texto(cel("Código")).upper()
        if cod not in E.CODIGOS_CATEGORIA:
            tab.erro(n, "Código", f"código fora da lista fechada: {cod!r} (uma categoria nova exige uma versão nova)")
            continue
        if cod in saida:
            tab.erro(n, "Código", "código repetido")
            continue
        acao = (_valor(tab, n, "Ação", cel("Ação"), texto, obrigatorio=True) or "").upper()
        if acao and acao not in E.ACOES_POR_CODIGO[cod]:
            tab.erro(n, "Ação", f"ação {acao} não vale para {cod} (use {', '.join(E.ACOES_POR_CODIGO[cod])})")
            acao = ""
        ativa = _valor(tab, n, "Ativa", cel("Ativa"), sim_nao, obrigatorio=True)
        liberada = _valor(tab, n, "Liberada para envio", cel("Liberada para envio"), sim_nao, obrigatorio=True)
        data_lib = _valor(tab, n, "Data da liberação", cel("Data da liberação"), data_iso) or ""
        if liberada and not data_lib:
            tab.erro(n, "Data da liberação", "obrigatória quando a categoria está liberada para envio")
        cod_texto = texto(cel("Código do texto")).upper()
        if eh_placeholder(cod_texto):
            tab.erro(n, "Código do texto", f"valor ainda não preenchido ({E.PLACEHOLDER})")
            cod_texto = ""
        saida[cod] = {
            "nome": texto(cel("Nome")) or E.NOMES_CATEGORIA[cod], "acao": acao or E.ACAO_PADRAO[cod],
            "ativa": bool(ativa) if ativa is not None else True, "liberada": bool(liberada),
            "data_liberacao": data_lib, "codigo_texto": cod_texto, "_linha": n,
        }
        dados["_origem_xlsx"][f"Categorias:{cod}"] = n
    for cod in E.CODIGOS_CATEGORIA:
        if cod not in saida:
            erros.append(ErroCelula(E.ABA_CATEGORIAS, 0, "", f"categoria {cod} ausente"))
    dados["categorias"] = {k: {kk: vv for kk, vv in v.items() if kk != "_linha"} for k, v in saida.items()}
    return saida


def _palavras(linhas: List[Tuple], dados: Dict, erros: List[ErroCelula]) -> None:
    aba = E.ABA_PALAVRAS
    cab = next((i + 1 for i, l in enumerate(linhas[:20]) if l and texto(l[0]) == "Categoria"), 0)
    if not cab:
        erros.append(ErroCelula(aba, 0, "", "cabeçalho (Categoria | Termo | Peso | Ativo | Origem) não encontrado"))
        return
    params: Dict[str, float] = {}
    for n, linha in enumerate(linhas[: cab - 1], start=1):
        nome = texto(linha[0]) if linha else ""
        if nome in E.PARAMETROS_PALAVRAS:
            try:
                params[nome] = decimal(linha[1] if len(linha) > 1 else None, 0.0, excluir_minimo=True)
            except _Aviso as e:
                erros.append(ErroCelula(aba, n, "B", f"{nome}: {e}"))
    for nome in E.PARAMETROS_PALAVRAS:
        if nome not in params:
            erros.append(ErroCelula(aba, 0, "", f"parâmetro {nome} ausente no topo da aba"))
    tab = _Tabela(aba, linhas, erros, linha_cabecalho=cab)
    if not tab.ok:
        return
    categorias: Dict[str, Dict[str, Dict[str, float]]] = {}
    for n, cel in tab.registros():
        cat = texto(cel("Categoria")).upper()
        if cat not in E.CATEGORIAS_TERMOS:
            tab.erro(n, "Categoria", f"categoria inválida para termos: {cat!r} (use {', '.join(E.CATEGORIAS_TERMOS)})")
            continue
        termo = _valor(tab, n, "Termo", cel("Termo"), texto, obrigatorio=True)
        peso = _valor(tab, n, "Peso", cel("Peso"), decimal, obrigatorio=True, minimo=0.0, excluir_minimo=True)
        ativo = _valor(tab, n, "Ativo", cel("Ativo"), sim_nao)
        if not termo or peso is None or ativo is False:
            continue
        termos = categorias.setdefault(cat, {"termos": {}})["termos"]
        chave = termo.strip()
        if any(t.lower() == chave.lower() for t in termos):
            tab.erro(n, "Termo", f"termo repetido na categoria {cat}: {chave!r}")
            continue
        termos[chave] = peso
    dados["_inline"]["classificacao.arquivo_termos"] = {
        "peso_assunto": params.get("peso_assunto", 2.0), "saturacao": params.get("saturacao", 5.0),
        "categorias": categorias,
    }


def _textos(linhas: List[Tuple], dados: Dict, erros: List[ErroCelula]) -> Dict[str, Dict[str, str]]:
    tab = _Tabela(E.ABA_TEXTOS, linhas, erros)
    saida: Dict[str, Dict[str, str]] = {}
    if not tab.ok:
        return saida
    for n, cel in tab.registros():
        cod = texto(cel("Código")).upper()
        if cod not in E.CODIGOS_TEXTO_FIXOS and not _RE_CODIGO_RESP.match(cod):
            tab.erro(n, "Código", f"código inválido: {cod!r} (use RESP_<CATEGORIA>, {', '.join(E.CODIGOS_TEXTO_FIXOS)})")
            continue
        if cod in saida:
            tab.erro(n, "Código", "código repetido")
            continue
        corpo = cel("Corpo")
        if eh_placeholder(corpo):
            tab.erro(n, "Corpo", f"valor ainda não preenchido ({E.PLACEHOLDER})")
            continue
        corpo_t = "" if corpo is None else str(corpo).replace("\r\n", "\n").strip()
        prefixo = texto(cel("Assunto (prefixo)"))
        ok = True
        for col, valor in (("Corpo", corpo_t), ("Assunto (prefixo)", prefixo)):
            for campo in _RE_CAMPO.findall(valor):
                if campo not in E.CAMPOS_TEXTO:
                    tab.erro(n, col, f"campo desconhecido {{{campo}}} (disponíveis: "
                                     + ", ".join("{" + c + "}" for c in E.CAMPOS_TEXTO) + ")")
                    ok = False
        if not corpo_t and cod != "ASSINATURA":
            tab.erro(n, "Corpo", "preenchimento obrigatório")
            ok = False
        if ok:
            saida[cod] = {"assunto_prefixo": prefixo, "corpo": corpo_t}
    dados.setdefault("respostas", {})["textos"] = saida
    return saida


def _tutoriais(linhas: List[Tuple], dados: Dict, erros: List[ErroCelula], categorias: Dict[str, Dict]) -> None:
    tab = _Tabela(E.ABA_TUTORIAIS, linhas, erros)
    if not tab.ok:
        return
    cats: Dict[str, Dict[str, Any]] = {}
    vistos = set()
    link_forms: Optional[str] = None
    for n, cel in tab.registros():
        cod = texto(cel("Categoria")).upper()
        if cod not in E.CODIGOS_TUTORIAL + ["FORMS_PO"]:
            tab.erro(n, "Categoria", f"categoria sem tutorial nem formulário: {cod!r}")
            continue
        if cod in vistos:
            tab.erro(n, "Categoria", "categoria repetida")
            continue
        vistos.add(cod)
        dados["_origem_xlsx"][f"Tutoriais:{cod}"] = n
        if cod == "FORMS_PO":
            bruto = cel("Link do formulário")
            if eh_placeholder(bruto):
                tab.erro(n, "Link do formulário", f"valor ainda não preenchido ({E.PLACEHOLDER})")
                continue
            link = texto(bruto)
            if link and not link.lower().startswith("https://"):
                tab.erro(n, "Link do formulário", "use a URL completa (https://...)")
                continue
            link_forms = link
            continue
        acao = (categorias.get(cod) or {}).get("acao", "RESPONDER_TUTORIAL")
        caminho = _valor(tab, n, "Caminho do arquivo", cel("Caminho do arquivo"), texto,
                         obrigatorio=acao == "RESPONDER_TUTORIAL")
        limite = _valor(tab, n, "Limite (MB)", cel("Limite (MB)"), decimal, minimo=0.0, excluir_minimo=True)
        conf: Dict[str, Any] = {"caminho_arquivo": caminho or "",
                                "descricao": (categorias.get(cod) or {}).get("nome") or E.NOMES_CATEGORIA[cod]}
        if limite is not None:
            conf["limite_mb"] = limite
        cats[cod] = conf
    for cod in E.CODIGOS_TUTORIAL:
        if cod not in vistos and (categorias.get(cod) or {}).get("acao", "RESPONDER_TUTORIAL") == "RESPONDER_TUTORIAL":
            erros.append(ErroCelula(E.ABA_TUTORIAIS, 0, "", f"linha da categoria {cod} ausente"))
    dados["_inline"]["tutoriais.arquivo"] = {"raiz": "", "limite_anexo_mb": 20, "exigir_arquivo_local": True,
                                             "categorias": cats}
    if "FORMS_PO" in vistos and link_forms is not None:
        dados.setdefault("respostas", {})["link_forms_po"] = link_forms


def _destinatarios(linhas: List[Tuple], dados: Dict, erros: List[ErroCelula]) -> None:
    tab = _Tabela(E.ABA_DESTINATARIOS, linhas, erros)
    if not tab.ok:
        return
    por_tipo: Dict[str, List[str]] = {t: [] for t in E.TIPOS_DESTINATARIO}
    for n, cel in tab.registros():
        tipo = texto(cel("Tipo")).upper()
        if tipo not in E.TIPOS_DESTINATARIO:
            tab.erro(n, "Tipo", f"tipo inválido: {tipo!r} (use {', '.join(E.TIPOS_DESTINATARIO)})")
            continue
        end = _valor(tab, n, "E-mail", cel("E-mail"), email, obrigatorio=True)
        if end and end not in por_tipo[tipo]:
            por_tipo[tipo].append(end)
    if not por_tipo["AVISO_ERRO"] and not any(e.aba == E.ABA_DESTINATARIOS and "E-mail" == e.coluna for e in erros):
        erros.append(ErroCelula(E.ABA_DESTINATARIOS, 0, "", "AVISO_ERRO obrigatório (pelo menos um e-mail)"))
    d = dados.setdefault("destinatarios", {})
    d["avisos_erro"] = por_tipo["AVISO_ERRO"]
    d["analistas_cc"] = por_tipo["CC"]
    por_motivo = {}
    if por_tipo["MANUAL_SAP"]:
        por_motivo["SAP"] = por_tipo["MANUAL_SAP"]
    if por_tipo["MANUAL_NAO_IDENTIFICADO"]:
        por_motivo["NAO_IDENTIFICADO"] = por_tipo["MANUAL_NAO_IDENTIFICADO"]
    d["analise_manual"] = {"padrao": por_tipo["MANUAL_PADRAO"], "por_motivo": por_motivo}


def _filtros(linhas: List[Tuple], dados: Dict, erros: List[ErroCelula]) -> None:
    tab = _Tabela(E.ABA_FILTROS, linhas, erros)
    if not tab.ok:
        return
    listas: Dict[str, List[str]] = {t: [] for t in E.TIPOS_FILTRO}
    placeholder_dominio = False
    for n, cel in tab.registros():
        tipo = texto(cel("Tipo")).upper()
        if tipo not in E.TIPOS_FILTRO:
            tab.erro(n, "Tipo", f"tipo inválido: {tipo!r} (use {', '.join(E.TIPOS_FILTRO)})")
            continue
        ativo = _valor(tab, n, "Ativo", cel("Ativo"), sim_nao)
        if eh_placeholder(cel("Valor")) and tipo == "DOMINIO_INTERNO":
            placeholder_dominio = True
        valor = _valor(tab, n, "Valor", cel("Valor"), texto, obrigatorio=True)
        if not valor or ativo is False:
            continue
        if tipo.startswith("MARCADOR"):
            try:
                re.compile(valor)
            except re.error as e:
                tab.erro(n, "Valor", f"expressão regular inválida: {e}")
                continue
        if tipo == "DOMINIO_INTERNO":
            valor = normalizar_dominio(valor)
        listas[tipo].append(valor)
    if not listas["DOMINIO_INTERNO"] and not placeholder_dominio:
        erros.append(ErroCelula(E.ABA_FILTROS, 0, "", "DOMINIO_INTERNO obrigatório (pelo menos o domínio corporativo)"))
    f = dados.setdefault("filtros", {})
    f["dominios_internos"] = listas["DOMINIO_INTERNO"]
    f["assuntos_resposta_automatica"] = listas["ASSUNTO_RESPOSTA_AUTOMATICA"]
    f["mensagens_do_rpa"] = {"assuntos": listas["MARCADOR_ASSUNTO_RPA"], "textos": listas["MARCADOR_TEXTO_RPA"]}


def resumo_erros(erros: Sequence[ErroCelula]) -> List[str]:
    return [str(e) for e in erros]
