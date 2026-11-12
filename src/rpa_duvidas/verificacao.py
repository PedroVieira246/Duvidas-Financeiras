"""Checagens do comando ``verificar`` acrescentadas na v0.3.0 (seção 7.2).

Cada função devolve uma lista de ``Item(nivel, mensagem)``:
``ERRO`` impede a execução; ``AVISO`` e ``INFO`` só informam.
"""
from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any, List, Optional

from .config import Config, ErroConfiguracao

ERRO, AVISO, INFO, OK = "ERRO", "AVISO", "INFO", "OK"

# OlAccountType
TIPOS_CONTA = {0: "Microsoft Exchange", 1: "IMAP", 2: "POP3", 3: "HTTP", 4: "Exchange ActiveSync", 5: "outro"}
OL_EXCHANGE, OL_EAS = 0, 4

CHAVE_NOVO_OUTLOOK = r"Software\Microsoft\Office\16.0\Outlook\Preferences"


@dataclass(frozen=True)
class Item:
    nivel: str
    mensagem: str

    def __str__(self) -> str:
        return f"  {self.nivel:<5} {self.mensagem}"


def novo_outlook_ativo() -> Optional[bool]:
    """``HKCU\\...\\Outlook\\Preferences\\UseNewOutlook = 1`` → True. Fora do Windows (ou sem a chave) → None."""
    if not sys.platform.startswith("win"):
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CHAVE_NOVO_OUTLOOK) as chave:
            valor, _ = winreg.QueryValueEx(chave, "UseNewOutlook")
            return int(valor) == 1
    except OSError:
        return None


def planilha_configuracao(cfg: Config) -> List[Item]:
    if not cfg.usa_xlsx:
        return []
    origem = cfg.get("configuracao_xlsx.lido_de", "")
    if not cfg.erros_xlsx:
        return [Item(OK, f"planilha válida: {origem} (modelo {cfg.get('configuracao_xlsx.versao_modelo', '?')})")]
    return [Item(ERRO, str(e)) for e in cfg.erros_xlsx]


def outlook(cfg: Config, novo_outlook=None) -> List[Item]:
    """Novo Outlook ligado (não tem COM) e e-mail da caixa × destino padrão."""
    itens: List[Item] = []
    if cfg.get("caixa.tipo") == "outlook_com":
        ativo = (novo_outlook or novo_outlook_ativo)()
        if ativo:
            itens.append(Item(ERRO, "o Novo Outlook está ligado (UseNewOutlook = 1) e não tem COM: desligue a opção "
                                    "'Novo Outlook' e use o Outlook clássico"))
        elif ativo is False:
            itens.append(Item(OK, "Outlook clássico (Novo Outlook desligado)"))
    conta = str(cfg.get("caixa.conta", "") or "").lower()
    destino = cfg.destino_teste
    if destino:
        if destino == conta:
            itens.append(Item(ERRO, f"e-mail destino padrão igual ao e-mail da caixa ({destino})"))
        else:
            itens.append(Item(OK, f"respostas de teste vão para {destino} (caixa: {conta or 'conta padrão'})"))
    return itens


def tipo_conta(cfg: Config, caixa: Any) -> List[Item]:
    obter = getattr(caixa, "tipo_conta", None)
    if not callable(obter):
        return []
    tipo = obter()
    nome = TIPOS_CONTA.get(tipo, "não identificado") if tipo is not None else "não identificado"
    itens = [Item(INFO, f"tipo da conta no Outlook: {nome}")]
    if tipo == OL_EAS and cfg.get("caixa.mover_apos_tratar", True):
        itens.append(Item(AVISO, "conta Exchange ActiveSync com mover_apos_tratar = S: o Outlook não move e-mails "
                                 "via COM nesse tipo de conta"))
    return itens


def escritorios(cfg: Config) -> List[Item]:
    if not cfg.get("escritorios.arquivo"):
        return []
    from .filtros import ErroEscritorios, ler_planilha_escritorios, valores_sem_escritorio

    try:
        mapa = ler_planilha_escritorios(
            cfg.caminho("escritorios.arquivo"), str(cfg.get("escritorios.aba", "") or ""),
            str(cfg.get("escritorios.coluna_dominio", "Domínio")), str(cfg.get("escritorios.coluna_escritorio", "Escritório")),
            valores_sem_escritorio=valores_sem_escritorio(cfg),
        )
    except ErroEscritorios as e:
        return [Item(ERRO, str(e))]
    itens = [Item(OK, f"planilha de escritórios: {mapa.resumo()} – {mapa.origem}")]
    itens += [Item(AVISO, a) for a in mapa.avisos]
    internos = {str(d).lower() for d in cfg.get("filtros.dominios_internos", []) or []}
    for d in sorted(set(mapa.mapa) & internos):
        itens.append(Item(AVISO, f"{d} está na planilha de escritórios e nos domínios internos: vale o interno"))
    return itens


def tutoriais(cfg: Config) -> List[Item]:
    """Cada tutorial existe, está baixado e cabe no limite (com aba/linha da planilha quando houver)."""
    from .tutoriais import RepositorioTutoriais

    origem = cfg.get("_origem_xlsx", {}) or {}
    try:
        repo = RepositorioTutoriais(cfg.yaml_referenciado("tutoriais.arquivo"), lambda v: cfg.caminho(v, eh_valor=True))
    except ErroConfiguracao as e:
        return [Item(ERRO, str(e))]
    acoes = {c: str((v or {}).get("acao", "")) for c, v in (cfg.get("categorias", {}) or {}).items()}
    itens = []
    for cat, ok, det in repo.verificar_todos():
        if not ok and acoes.get(cat) and acoes[cat] != "RESPONDER_TUTORIAL":
            itens.append(Item(INFO, f"{cat:<14} sem tutorial (ação {acoes[cat]})"))
            continue
        linha = origem.get(f"Tutoriais:{cat}")
        local = f'Aba Tutoriais, linha {linha}, coluna "Caminho do arquivo": ' if linha and not ok else ""
        itens.append(Item(OK if ok else ERRO, f"{cat:<14} {local}{det}"))
    return itens


def formulario(cfg: Config) -> List[Item]:
    if not cfg.usa_xlsx:
        return []
    link = str(cfg.get("respostas.link_forms_po", "") or "").strip()
    if not link:
        return [Item(AVISO, "link do formulário de PO vazio: a categoria FORMS_PO será tratada como MANUAL")]
    return [Item(OK, f"link do formulário de PO: {link}")]


def arquivamento(cfg: Config) -> List[Item]:
    if not cfg.get("arquivamento.raiz"):
        return []
    from .tutoriais import _somente_na_nuvem

    raiz = cfg.caminho("arquivamento.raiz")
    avisos: List[Item] = []
    bruto = str(cfg.get("arquivamento.raiz") or "").strip()
    if bruto and not any(s in bruto for s in ("\\", "/", ":")) and bruto.lower() != "arquivo":
        # v0.3.1: no 1º teste a área preencheu "Diretório" (nome de coluna) em vez de um caminho
        avisos.append(Item(AVISO, f"caminho_arquivo_emails = '{bruto}' não é um caminho completo: os .msg vão para "
                                  f"{raiz}. Confira se era essa a pasta desejada."))
    try:
        raiz.mkdir(parents=True, exist_ok=True)
        if _somente_na_nuvem(raiz):
            return [Item(ERRO, f"pasta de arquivamento só na nuvem (OneDrive): {raiz}")]
        teste = raiz / f".rpa_teste_{uuid.uuid4().hex[:8]}"
        teste.write_text("teste", encoding="utf-8")
        try:
            os.remove(teste)
        except OSError:
            pass
    except OSError as e:
        return [Item(ERRO, f"pasta de arquivamento sem permissão de gravação ou inacessível: {raiz} ({e})")]
    return [Item(OK, f"pasta de arquivamento aceita gravação: {raiz}")] + avisos


def categorias(cfg: Config) -> List[Item]:
    cats = cfg.get("categorias", {}) or {}
    liberadas = sorted(c for c, v in cats.items() if (v or {}).get("liberada"))
    if not cats:
        return []
    if not liberadas:
        return [Item(INFO, "nenhuma categoria liberada para envio: só rascunhos")]
    if not cfg.envio_real:
        return [Item(AVISO, f"categorias liberadas para envio ({', '.join(liberadas)}) com modo_execucao = SIMULACAO: "
                            "continuam gerando só rascunhos")]
    return [Item(INFO, f"envio REAL liberado para: {', '.join(liberadas)} (sempre só ao destino padrão)")]
