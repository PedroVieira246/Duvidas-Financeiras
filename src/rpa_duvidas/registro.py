"""Registro, idempotência e auditoria (F15 + F16 – RF10, RNF01, RNF03).

Três saídas:
  * log técnico diário: ``logs/rpa_AAAA-MM-DD.log``;
  * banco SQLite de estado (fonte da verdade): tabela ``estado`` (uma linha por
    e-mail, usada para nunca responder duas vezes) e ``eventos`` (uma linha por
    tratamento, base da planilha) e, desde a v0.2.0, ``respostas_ia`` (JSON
    bruto devolvido pela IA – acesso restrito, RN8.3);
  * planilha de controle ``.xlsx`` exportada ao fim de cada ciclo, para a área
    e para medir o ganho. Se ela estiver aberta no Excel, o robô só avisa no
    log e tenta de novo no próximo ciclo – nada se perde, o banco já gravou.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .modelos import Resultado, Status
from .respostas import protocolo

log = logging.getLogger(__name__)

COLUNAS_EVENTO = [
    ("data_hora", "Data/hora"), ("ciclo_id", "Ciclo"), ("perfil", "Perfil"), ("modo", "Modo"),
    ("protocolo", "Protocolo"), ("id_mensagem", "ID da mensagem"), ("recebido_em", "Recebido em"),
    ("remetente", "Remetente"), ("assunto", "Assunto"), ("tem_anexos", "Tem anexos"),
    ("categoria", "Categoria"), ("categoria_sugerida", "Categoria sugerida"), ("confianca", "Confiança"),
    ("motivo", "Motivo da classificação"), ("motivo_manual", "Motivo manual"), ("acao", "Ação"),
    ("arquivo_enviado", "Arquivo enviado"), ("destinatarios", "Destinatários"), ("destino", "Pasta destino"),
    ("status", "Status"), ("erro", "Erro"), ("duracao_ms", "Duração (ms)"),
    # v0.2.0 – classificação por IA (E8 – RN8.1; auditoria RNF-IA02)
    ("classificador", "Classificador"), ("categoria_docx", "Categoria (.docx)"),
    ("categorias_secundarias", "Categorias secundárias"), ("sinais_excecao", "Sinais de exceção"),
    ("resumo_duvida", "Resumo da dúvida (IA)"), ("regra_decisao", "Regra de decisão"),
    ("modelo_ia", "Modelo da IA"), ("versao_prompt", "Versão do prompt"), ("hash_prompt", "Hash do prompt"),
    ("latencia_ia_ms", "Latência IA (ms)"), ("tentativas_ia", "Tentativas IA"), ("tokens", "Tokens"),
]
# v0.3.0 – calibração (seção 8). Lista separada para a migração da v0.2.x continuar
# reportando só as colunas dela; o banco e a planilha usam COLUNAS_REGISTRO.
COLUNAS_V030 = [
    ("escritorio", "Escritório"),
]
COLUNAS_REGISTRO = COLUNAS_EVENTO + COLUNAS_V030
# Colunas que entraram depois da v0.1.0 chegam a um banco antigo por ALTER TABLE (migrar – lacuna R7)

_SQL = f"""
CREATE TABLE IF NOT EXISTS estado (
    chave TEXT PRIMARY KEY,
    protocolo TEXT,
    status TEXT,
    acao TEXT,
    destino TEXT,
    acao_executada INTEGER DEFAULT 0,
    criado_em TEXT,
    atualizado_em TEXT
);
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    {", ".join(c + " TEXT" for c, _ in COLUNAS_EVENTO)}
);
CREATE TABLE IF NOT EXISTS respostas_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    data_hora TEXT, ciclo_id TEXT, protocolo TEXT, id_mensagem TEXT,
    modelo TEXT, versao_prompt TEXT, hash_prompt TEXT,
    chamada INTEGER, valida INTEGER, resposta_bruta TEXT
);
CREATE TABLE IF NOT EXISTS avisos (
    chave TEXT PRIMARY KEY, enviado_em TEXT
);
CREATE TABLE IF NOT EXISTS ciclos (
    ciclo_id TEXT PRIMARY KEY, perfil TEXT, modo TEXT, inicio TEXT, fim TEXT,
    lidos INTEGER, respondidos INTEGER, encaminhados INTEGER, ignorados INTEGER,
    erros INTEGER, reconciliados INTEGER, observacao TEXT
);
"""


# --------------------------------------------------------------------------- #
# log técnico
# --------------------------------------------------------------------------- #
def configurar_log(pasta: Path, nivel: str = "INFO", console: bool = True) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"rpa_{datetime.now():%Y-%m-%d}.log"
    raiz = logging.getLogger()
    raiz.setLevel(getattr(logging, str(nivel).upper(), logging.INFO))
    for h in list(raiz.handlers):
        raiz.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")
    fh = logging.FileHandler(arquivo, encoding="utf-8")
    fh.setFormatter(fmt)
    raiz.addHandler(fh)
    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S"))
        raiz.addHandler(ch)
    return arquivo


# --------------------------------------------------------------------------- #
# trava contra execuções simultâneas
# --------------------------------------------------------------------------- #
class ExecucaoEmAndamento(Exception):
    pass


@contextmanager
def trava(caminho: Path, validade_min: int = 120) -> Iterator[None]:
    """Impede dois ciclos ao mesmo tempo (ex.: Agendador disparando em cima)."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if caminho.exists():
        idade_min = (datetime.now().timestamp() - caminho.stat().st_mtime) / 60
        if idade_min < validade_min:
            raise ExecucaoEmAndamento(f"Outro ciclo em andamento (trava {caminho}, {idade_min:.0f} min)")
        log.warning("Trava antiga (%.0f min) removida: %s", idade_min, caminho)
        caminho.unlink()
    fd = os.open(str(caminho), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, f"{os.getpid()} {datetime.now().isoformat()}".encode())
    os.close(fd)
    try:
        yield
    finally:
        try:
            caminho.unlink()
        except FileNotFoundError:
            pass


# --------------------------------------------------------------------------- #
# migração de banco existente (lacuna R7)
# --------------------------------------------------------------------------- #
def migrar(con: sqlite3.Connection, colunas=None) -> List[str]:
    """Acrescenta em ``eventos`` as colunas que faltam (``CREATE TABLE IF NOT EXISTS``
    não altera tabela que já existe). Idempotente. Devolve as colunas criadas."""
    colunas = COLUNAS_EVENTO if colunas is None else colunas
    existentes = {row[1] for row in con.execute("PRAGMA table_info(eventos)")}
    novas = [c for c, _ in colunas if c not in existentes]
    for coluna in novas:
        con.execute(f"ALTER TABLE eventos ADD COLUMN {coluna} TEXT")
    if novas:
        log.info("Banco de estado migrado: %d coluna(s) nova(s) em eventos (%s)", len(novas), ", ".join(novas))
    return novas


def _lista(valor) -> str:
    return ", ".join(str(x) for x in valor) if isinstance(valor, (list, tuple)) else str(valor or "")


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #
class Registro:
    def __init__(self, banco: Path, perfil: str):
        banco.parent.mkdir(parents=True, exist_ok=True)
        self.banco = banco
        self.perfil = perfil
        self.con = sqlite3.connect(str(banco))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(_SQL)
        self.colunas_migradas = migrar(self.con)
        self.colunas_migradas_v030 = migrar(self.con, COLUNAS_V030)
        self.con.commit()

    def fechar(self) -> None:
        self.con.close()

    # ---- idempotência (RNF01) -------------------------------------------- #
    def estado(self, chave: str) -> Optional[sqlite3.Row]:
        return self.con.execute("SELECT * FROM estado WHERE chave = ?", (chave,)).fetchone()

    def marcar_em_andamento(self, chave: str, prot: str, acao: str) -> None:
        agora = datetime.now().isoformat(timespec="seconds")
        self.con.execute(
            """INSERT INTO estado (chave, protocolo, status, acao, acao_executada, criado_em, atualizado_em)
               VALUES (?, ?, ?, ?, 0, ?, ?)
               ON CONFLICT(chave) DO UPDATE SET status=excluded.status, acao=excluded.acao,
                   acao_executada=0, atualizado_em=excluded.atualizado_em""",
            (chave, prot, Status.EM_ANDAMENTO, acao, agora, agora),
        )
        self.con.commit()

    def marcar_acao_executada(self, chave: str) -> None:
        """Gravado assim que a resposta/encaminhamento sai – antes de mover o e-mail."""
        self.con.execute(
            "UPDATE estado SET acao_executada = 1, atualizado_em = ? WHERE chave = ?",
            (datetime.now().isoformat(timespec="seconds"), chave),
        )
        self.con.commit()

    def esquecer(self, prot: str) -> int:
        """Permite reprocessar um e-mail SIMULADO ou em ERRO (nunca um CONCLUIDO)."""
        cur = self.con.execute(
            "DELETE FROM estado WHERE protocolo = ? AND status IN (?, ?)",
            (prot.upper(), Status.SIMULADO, Status.ERRO),
        )
        self.con.commit()
        return cur.rowcount

    # ---- eventos (RF10) -------------------------------------------------- #
    def gravar(self, r: Resultado, ciclo_id: str, modo: str) -> None:
        e, c = r.email, r.classificacao
        agora = datetime.now().isoformat(timespec="seconds")
        prot = protocolo(e)
        linha = {
            "data_hora": agora, "ciclo_id": ciclo_id, "perfil": self.perfil, "modo": modo,
            "protocolo": prot, "id_mensagem": e.id_mensagem,
            "recebido_em": e.data_recebimento.isoformat(timespec="seconds") if e.data_recebimento else "",
            "remetente": e.remetente, "assunto": e.assunto, "tem_anexos": "sim" if e.tem_anexos else "não",
            "categoria": c.categoria if c else "", "categoria_sugerida": (c.detalhes.get("categoria_sugerida", "") if c else ""),
            "confianca": f"{c.confianca:.2f}" if c else "", "motivo": c.motivo if c else e.motivo_resposta_automatica,
            "motivo_manual": (c.motivo_manual or "") if c else "", "acao": r.acao,
            "arquivo_enviado": r.arquivo_enviado, "destinatarios": "; ".join(r.destinatarios),
            "destino": r.destino, "status": r.status, "erro": r.erro, "duracao_ms": str(r.duracao_ms),
            "escritorio": e.escritorio,
        }
        if not c and r.motivo_ignorado:
            linha["motivo"] = r.motivo_ignorado
        d = c.detalhes if c else {}
        ia = d.get("classificador") == "ia"
        linha.update({
            "classificador": str(d.get("classificador") or ""),
            "categoria_docx": str(d.get("categoria_docx") or ""),
            "categorias_secundarias": _lista(d.get("categorias_secundarias")),
            "sinais_excecao": _lista(d.get("sinais_excecao")),
            "resumo_duvida": str(d.get("resumo_duvida") or ""),
            "regra_decisao": str(d.get("regra_decisao") or ""),
            "modelo_ia": str(d.get("modelo") or "") if ia else "",
            "versao_prompt": str(d.get("versao_prompt") or ""),
            "hash_prompt": str(d.get("hash_prompt") or ""),
            "latencia_ia_ms": str(d.get("latencia_ms")) if ia and d.get("latencia_ms") is not None else "",
            "tentativas_ia": str(d.get("tentativas")) if ia and d.get("tentativas") is not None else "",
            "tokens": str(d.get("tokens")) if ia and d.get("tokens") is not None else "",
        })
        cols = [k for k, _ in COLUNAS_REGISTRO]
        self.con.execute(
            f"INSERT INTO eventos ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
            [linha[k] for k in cols],
        )
        for bruta in d.get("respostas_brutas") or []:      # RN8.3: tabela separada, fora da planilha
            self.con.execute(
                """INSERT INTO respostas_ia (data_hora, ciclo_id, protocolo, id_mensagem, modelo, versao_prompt,
                   hash_prompt, chamada, valida, resposta_bruta) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (agora, ciclo_id, prot, e.id_mensagem, str(d.get("modelo") or ""), str(d.get("versao_prompt") or ""),
                 str(d.get("hash_prompt") or ""), int(bruta.get("chamada", 0)), 1 if bruta.get("valida") else 0,
                 bruta.get("texto") if isinstance(bruta.get("texto"), str) else json.dumps(bruta.get("texto"))),
            )
        if r.status != Status.RECONCILIADO:
            self.con.execute(
                """INSERT INTO estado (chave, protocolo, status, acao, destino, acao_executada, criado_em, atualizado_em)
                   VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                   ON CONFLICT(chave) DO UPDATE SET status=excluded.status, acao=excluded.acao,
                       destino=excluded.destino, atualizado_em=excluded.atualizado_em""",
                (e.chave, prot, r.status, r.acao, r.destino, agora, agora),
            )
        self.con.commit()

    def gravar_ciclo(self, ciclo_id: str, modo: str, inicio: datetime, resumo: Dict[str, int], obs: str = "") -> None:
        self.con.execute(
            """INSERT OR REPLACE INTO ciclos VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ciclo_id, self.perfil, modo, inicio.isoformat(timespec="seconds"),
             datetime.now().isoformat(timespec="seconds"), resumo.get("lidos", 0), resumo.get("respondidos", 0),
             resumo.get("encaminhados", 0), resumo.get("ignorados", 0), resumo.get("erros", 0),
             resumo.get("reconciliados", 0), obs),
        )
        self.con.commit()

    # ---- avisos únicos (v0.3.0) ------------------------------------------ #
    def ja_avisado(self, chave: str) -> bool:
        return self.con.execute("SELECT 1 FROM avisos WHERE chave = ?", (chave,)).fetchone() is not None

    def registrar_aviso(self, chave: str) -> None:
        self.con.execute("INSERT OR REPLACE INTO avisos VALUES (?, ?)",
                         (chave, datetime.now().isoformat(timespec="seconds")))
        self.con.commit()

    def eventos(self) -> List[sqlite3.Row]:
        return self.con.execute("SELECT * FROM eventos ORDER BY id").fetchall()

    def respostas_ia(self) -> List[sqlite3.Row]:
        return self.con.execute("SELECT * FROM respostas_ia ORDER BY id").fetchall()

    # ---- planilha de controle (RNF03) ----------------------------------- #
    def exportar_planilha(self, destino: Path) -> bool:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "Registro"
        ws.append([titulo for _, titulo in COLUNAS_REGISTRO])
        for row in self.eventos():
            ws.append([row[c] for c, _ in COLUNAS_REGISTRO])
        cab = PatternFill("solid", fgColor="1F3864")
        for cel in ws[1]:
            cel.font = Font(bold=True, color="FFFFFF")
            cel.fill = cab
            cel.alignment = Alignment(vertical="center", wrap_text=True)
        larguras = {"Assunto": 40, "Motivo da classificação": 50, "Erro": 40, "ID da mensagem": 30, "Destinatários": 30,
                    "Resumo da dúvida (IA)": 50}
        for i, (_, titulo) in enumerate(COLUNAS_REGISTRO, start=1):
            ws.column_dimensions[get_column_letter(i)].width = larguras.get(titulo, 16)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        wc = wb.create_sheet("Ciclos")
        colunas_ciclo = ["ciclo_id", "perfil", "modo", "inicio", "fim", "lidos", "respondidos",
                         "encaminhados", "ignorados", "erros", "reconciliados", "observacao"]
        wc.append(colunas_ciclo)
        for row in self.con.execute("SELECT * FROM ciclos ORDER BY inicio"):
            wc.append([row[c] for c in colunas_ciclo])
        for cel in wc[1]:
            cel.font = Font(bold=True, color="FFFFFF")
            cel.fill = cab

        wr = wb.create_sheet("Resumo")
        wr.append(["Categoria", "Ação", "Status", "Quantidade"])
        for row in self.con.execute(
            "SELECT categoria, acao, status, COUNT(*) n FROM eventos GROUP BY categoria, acao, status ORDER BY n DESC"
        ):
            wr.append([row["categoria"] or "—", row["acao"], row["status"], row["n"]])
        for cel in wr[1]:
            cel.font = Font(bold=True, color="FFFFFF")
            cel.fill = cab
        for col in "ABCD":
            wr.column_dimensions[col].width = 22

        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = destino.with_name(f".{destino.stem}.tmp.xlsx")
        try:
            wb.save(temporario)
            os.replace(temporario, destino)
            return True
        except PermissionError:
            log.warning("Planilha de controle em uso (aberta no Excel?): %s – será atualizada no próximo ciclo", destino)
            try:
                temporario.unlink()
            except OSError:
                pass
            return False
