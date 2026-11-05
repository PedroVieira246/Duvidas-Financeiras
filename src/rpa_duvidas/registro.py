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

import getpass
import json
import logging
import os
import socket
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from . import __version__
from .config_xlsx_esquema import CODIGOS_CATEGORIA
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
    ("escritorio", "Escritório"), ("destinatario_original", "Destinatário original"),
    ("destino_respostas", "Destino das respostas"), ("enviado", "Enviado"),
    ("categoria_liberada", "Categoria liberada"), ("arquivado_em", "Arquivado em"),
    ("maquina", "Máquina"), ("usuario_windows", "Usuário"), ("versao_app", "Versão"),
]
COLUNAS_REGISTRO = COLUNAS_EVENTO + COLUNAS_V030

# v0.3.0 – retorno manual (D08 – seção 6.5): preenchido pelo analista na aba Registro,
# lido de volta para a tabela retorno_manual (fonte da verdade) a cada exportação.
COLUNAS_RETORNO = [
    ("avaliacao", "Avaliação"), ("categoria_correta", "Categoria correta"), ("observacao", "Observação"),
    ("tempo_manual_min", "Tempo manual (min)"), ("revisado_por", "Revisado por"), ("data_revisao", "Data da revisão"),
]
AVALIACOES = ["Correto", "Categoria errada", "Deveria encaminhar", "Deveria responder", "Tutorial errado"]
AVALIACOES_GRAVES = ("Tutorial errado", "Deveria encaminhar")
TEMPO_MAXIMO_MIN = 240


def _maquina() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return ""


def _usuario() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return os.environ.get("USERNAME", "")
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
CREATE TABLE IF NOT EXISTS retorno_manual (
    protocolo TEXT PRIMARY KEY, avaliacao TEXT, categoria_correta TEXT, observacao TEXT,
    tempo_manual_min INTEGER, revisado_por TEXT, data_revisao TEXT, lido_em TEXT
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


def _sn(valor) -> str:
    return "" if valor is None else ("S" if valor else "N")


def _lista(valor) -> str:
    return ", ".join(str(x) for x in valor) if isinstance(valor, (list, tuple)) else str(valor or "")


# --------------------------------------------------------------------------- #
# Registro
# --------------------------------------------------------------------------- #
class Registro:
    def __init__(self, banco: Path, perfil: str, destino_respostas: str = ""):
        banco.parent.mkdir(parents=True, exist_ok=True)
        self.banco = banco
        self.perfil = perfil
        self.destino_respostas = destino_respostas
        self.criterio: Tuple[float, int] = (0.95, 20)       # critério de liberação (§12.8) – só informativo
        self.con = sqlite3.connect(str(banco))
        self.con.row_factory = sqlite3.Row
        self.con.executescript(_SQL)
        self.colunas_migradas = migrar(self.con)
        self.colunas_migradas_v030 = migrar(self.con, COLUNAS_V030)
        if "nao_fornecedores" not in {r[1] for r in self.con.execute("PRAGMA table_info(ciclos)")}:
            self.con.execute("ALTER TABLE ciclos ADD COLUMN nao_fornecedores INTEGER")   # v0.3.0
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
            "escritorio": e.escritorio, "destinatario_original": r.destinatario_original,
            "destino_respostas": self.destino_respostas, "enviado": _sn(r.enviado),
            "categoria_liberada": _sn(r.categoria_liberada), "arquivado_em": r.arquivado_em,
            "maquina": _maquina(), "usuario_windows": _usuario(), "versao_app": __version__,
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

    def gravar_ciclo(self, ciclo_id: str, modo: str, inicio: datetime, resumo: Dict[str, int], obs: str = "",
                     nao_fornecedores: int = 0) -> None:
        self.con.execute(
            """INSERT OR REPLACE INTO ciclos (ciclo_id, perfil, modo, inicio, fim, lidos, respondidos, encaminhados,
               ignorados, erros, reconciliados, observacao, nao_fornecedores) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ciclo_id, self.perfil, modo, inicio.isoformat(timespec="seconds"),
             datetime.now().isoformat(timespec="seconds"), resumo.get("lidos", 0), resumo.get("respondidos", 0),
             resumo.get("encaminhados", 0), resumo.get("ignorados", 0), resumo.get("erros", 0),
             resumo.get("reconciliados", 0), obs, nao_fornecedores),
        )
        self.con.commit()

    # ---- arquivamento .msg (v0.3.0 – seção 6.4) ------------------------- #
    def pendentes_arquivamento(self) -> List[sqlite3.Row]:
        """Último evento de cada protocolo cujo arquivamento falhou (e que não foi refeito depois)."""
        return self.con.execute(
            """SELECT e.* FROM eventos e
               WHERE e.arquivado_em LIKE 'FALHA%'
                 AND e.id = (SELECT MAX(x.id) FROM eventos x WHERE x.protocolo = e.protocolo
                             AND COALESCE(x.arquivado_em, '') <> '')
               ORDER BY e.id"""
        ).fetchall()

    def atualizar_arquivamento(self, evento_id: int, valor: str) -> None:
        self.con.execute("UPDATE eventos SET arquivado_em = ? WHERE id = ?", (valor, evento_id))
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

    # ---- retorno manual (v0.3.0 – D08, seção 6.5) ----------------------- #
    def retornos(self) -> Dict[str, sqlite3.Row]:
        return {r["protocolo"]: r for r in self.con.execute("SELECT * FROM retorno_manual")}

    def gravar_retorno(self, prot: str, valores: Dict[str, Any]) -> bool:
        """Upsert do retorno de um protocolo. Valores vazios NÃO apagam o que já está gravado."""
        valores = {k: v for k, v in valores.items() if v not in (None, "")}
        if not valores:
            return False
        atual = self.con.execute("SELECT * FROM retorno_manual WHERE protocolo = ?", (prot,)).fetchone()
        if atual is not None and all(str(atual[k]) == str(v) for k, v in valores.items()):
            return False
        agora = datetime.now().isoformat(timespec="seconds")
        if atual is None:
            self.con.execute("INSERT INTO retorno_manual (protocolo, lido_em) VALUES (?, ?)", (prot, agora))
        sets = ", ".join(f"{k} = ?" for k in valores)
        self.con.execute(f"UPDATE retorno_manual SET {sets}, lido_em = ? WHERE protocolo = ?",
                         [*valores.values(), agora, prot])
        self.con.commit()
        return True

    @staticmethod
    def _validar_retorno(coluna: str, valor: Any) -> Any:
        """Converte/valida uma célula de retorno. Valor inválido → ValueError (a célula é ignorada)."""
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            return None
        if coluna == "avaliacao":
            v = str(valor).strip()
            iguais = [a for a in AVALIACOES if a.lower() == v.lower()]
            if not iguais:
                raise ValueError(f"avaliação fora da lista: {v!r}")
            return iguais[0]
        if coluna == "categoria_correta":
            v = str(valor).strip().upper()
            if v not in CODIGOS_CATEGORIA:
                raise ValueError(f"categoria inexistente: {v!r}")
            return v
        if coluna == "tempo_manual_min":
            n = float(str(valor).replace(",", "."))
            if not n.is_integer() or not 0 <= n <= TEMPO_MAXIMO_MIN:
                raise ValueError(f"tempo deve ser inteiro de 0 a {TEMPO_MAXIMO_MIN}: {valor!r}")
            return int(n)
        if coluna == "data_revisao":
            if isinstance(valor, datetime):
                return valor.date().isoformat()
            if isinstance(valor, date):
                return valor.isoformat()
            texto = str(valor).strip()
            for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                try:
                    return datetime.strptime(texto, fmt).date().isoformat()
                except ValueError:
                    pass
            raise ValueError(f"data inválida: {valor!r}")
        return str(valor).strip()

    def importar_retorno(self, planilha: Path) -> int:
        """Lê as colunas de retorno da aba Registro e grava no SQLite. Devolve quantos protocolos mudaram.

        ``PermissionError`` sobe (planilha aberta no Excel): quem chama decide.
        """
        from openpyxl import load_workbook

        wb = load_workbook(planilha, read_only=True, data_only=True)
        try:
            if "Registro" not in wb.sheetnames:
                return 0
            linhas = list(wb["Registro"].iter_rows(values_only=True))
        finally:
            wb.close()
        if not linhas:
            return 0
        cab = [str(c or "").strip() for c in linhas[0]]
        if "Protocolo" not in cab:
            return 0
        i_prot = cab.index("Protocolo")
        indices = {col: cab.index(tit) for col, tit in COLUNAS_RETORNO if tit in cab}
        por_protocolo: Dict[str, Dict[str, Any]] = {}
        for n, linha in enumerate(linhas[1:], start=2):
            prot = str(linha[i_prot] or "").strip().upper() if i_prot < len(linha) else ""
            if not prot:
                continue
            destino = por_protocolo.setdefault(prot, {})
            for col, i in indices.items():
                bruto = linha[i] if i < len(linha) else None
                try:
                    v = self._validar_retorno(col, bruto)
                except (TypeError, ValueError) as e:
                    log.warning("Planilha de controle, linha %d, coluna %s: %s – valor ignorado", n, dict(COLUNAS_RETORNO)[col], e)
                    continue
                if v is None:
                    continue
                if col in destino and destino[col] != v:
                    log.warning("Retorno do protocolo %s com valores diferentes em linhas distintas (%s): vale o da "
                                "linha %d", prot, dict(COLUNAS_RETORNO)[col], n)
                destino[col] = v
        return sum(1 for prot, valores in por_protocolo.items() if self.gravar_retorno(prot, valores))

    # ---- bloqueio por "Tutorial errado" (v0.3.0 – T13) ------------------ #
    def tutoriais_errados_desde(self, categoria: str, data_liberacao: str) -> List[str]:
        """Protocolos com avaliação "Tutorial errado" em e-mails da categoria tratados a partir da data."""
        rows = self.con.execute(
            """SELECT DISTINCT e.protocolo FROM eventos e JOIN retorno_manual r ON r.protocolo = e.protocolo
               WHERE r.avaliacao = 'Tutorial errado' AND e.categoria = ? AND substr(e.data_hora, 1, 10) >= ?
               ORDER BY e.protocolo""",
            (categoria, data_liberacao),
        ).fetchall()
        return [r[0] for r in rows]

    # ---- resumo da calibração ------------------------------------------- #
    def resumo_calibracao(self) -> List[Dict[str, Any]]:
        """Por categoria (do último evento de cada protocolo avaliado): avaliados, corretos, acerto, graves, tempo."""
        rows = self.con.execute(
            """SELECT e.categoria, r.avaliacao, r.tempo_manual_min FROM retorno_manual r
               JOIN eventos e ON e.id = (SELECT MAX(x.id) FROM eventos x WHERE x.protocolo = r.protocolo)
               WHERE COALESCE(r.avaliacao, '') <> ''"""
        ).fetchall()
        acerto_min, minimo = self.criterio
        saida: Dict[str, Dict[str, Any]] = {}
        for cat, aval, tempo in rows:
            d = saida.setdefault(cat or "—", {"categoria": cat or "—", "avaliados": 0, "corretos": 0, "graves": 0,
                                               "tempo": 0})
            d["avaliados"] += 1
            if aval == "Correto":
                d["corretos"] += 1
                d["tempo"] += int(tempo or 0)
            if aval in AVALIACOES_GRAVES:
                d["graves"] += 1
        for d in saida.values():
            d["acerto"] = d["corretos"] / d["avaliados"] if d["avaliados"] else 0.0
            d["atinge"] = d["avaliados"] >= minimo and d["acerto"] >= acerto_min
        return sorted(saida.values(), key=lambda d: d["categoria"])

    # ---- planilha de controle (RNF03) ----------------------------------- #
    def exportar_planilha(self, destino: Path) -> bool:
        """Planilha de controle (RNF03) com o retorno manual (v0.3.0 – seção 6.5).

        1. se a planilha existe, lê as colunas de retorno e grava no SQLite (célula vazia não apaga);
        2. regera a planilha a partir do SQLite (eventos + retorno);
        3. planilha aberta (``PermissionError``): pula 1 e 2, avisa no log e tenta no próximo ciclo.
        """
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill, Protection
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.datavalidation import DataValidation

        destino = Path(destino)
        if destino.exists():
            try:
                n = self.importar_retorno(destino)
                if n:
                    log.info("Retorno manual lido da planilha de controle: %d protocolo(s) atualizado(s)", n)
            except PermissionError:
                log.warning("Planilha de controle em uso (aberta no Excel?): %s – será atualizada no próximo ciclo",
                            destino)
                return False
            except Exception:
                log.exception("Não foi possível ler o retorno manual de %s – planilha não regerada", destino)
                return False

        wb = Workbook()
        ws = wb.active
        ws.title = "Registro"
        colunas = COLUNAS_REGISTRO + COLUNAS_RETORNO
        ws.append([titulo for _, titulo in colunas])
        retornos = self.retornos()
        for row in self.eventos():
            ret = retornos.get(row["protocolo"])
            valores = [row[c] for c, _ in COLUNAS_REGISTRO]
            for c, _ in COLUNAS_RETORNO:
                v = ret[c] if ret is not None else None
                if c == "data_revisao" and v:
                    try:
                        v = datetime.strptime(v, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                valores.append(v)
            ws.append(valores)
        cab = PatternFill("solid", fgColor="1F3864")
        cab_robo = PatternFill("solid", fgColor="2E75B6")        # colunas novas do robô (v0.3.0)
        cab_retorno = PatternFill("solid", fgColor="C65911")     # colunas que o analista preenche
        n_antigas, n_robo = len(COLUNAS_EVENTO), len(COLUNAS_V030)
        for i, cel in enumerate(ws[1], start=1):
            cel.font = Font(bold=True, color="FFFFFF")
            cel.fill = cab if i <= n_antigas else cab_robo if i <= n_antigas + n_robo else cab_retorno
            cel.alignment = Alignment(vertical="center", wrap_text=True)
        larguras = {"Assunto": 40, "Motivo da classificação": 50, "Erro": 40, "ID da mensagem": 30, "Destinatários": 30,
                    "Resumo da dúvida (IA)": 50, "Arquivado em": 50, "Observação": 40, "Avaliação": 20,
                    "Categoria correta": 22, "Destinatário original": 30}
        for i, (_, titulo) in enumerate(colunas, start=1):
            ws.column_dimensions[get_column_letter(i)].width = larguras.get(titulo, 16)
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        # validações e proteção: só as colunas de retorno ficam editáveis
        ultima = max(ws.max_row, 2)
        col_ret = {c: get_column_letter(len(COLUNAS_REGISTRO) + i) for i, (c, _) in enumerate(COLUNAS_RETORNO, start=1)}

        def validar(dv: DataValidation, coluna: str) -> None:
            dv.showErrorMessage = True
            ws.add_data_validation(dv)
            dv.add(f"{col_ret[coluna]}2:{col_ret[coluna]}{ultima}")

        validar(DataValidation(type="list", formula1='"' + ",".join(AVALIACOES) + '"', allow_blank=True,
                               errorTitle="Avaliação", error="Escolha uma avaliação da lista."), "avaliacao")
        validar(DataValidation(type="list", formula1='"' + ",".join(CODIGOS_CATEGORIA) + '"', allow_blank=True,
                               errorTitle="Categoria correta", error="Use um código da aba Categorias."),
                "categoria_correta")
        validar(DataValidation(type="whole", operator="between", formula1="0", formula2=str(TEMPO_MAXIMO_MIN),
                               allow_blank=True, errorTitle="Tempo manual",
                               error=f"Número inteiro de 0 a {TEMPO_MAXIMO_MIN}."), "tempo_manual_min")
        validar(DataValidation(type="date", operator="greaterThan", formula1="36526", allow_blank=True,
                               errorTitle="Data da revisão", error="Informe uma data."), "data_revisao")
        livre = Protection(locked=False)
        for coluna in col_ret.values():
            for r in range(2, ultima + 1):
                cel = ws[f"{coluna}{r}"]
                cel.protection = livre
                if coluna == col_ret["data_revisao"]:
                    cel.number_format = "DD/MM/YYYY"
        ws.protection.sheet = True                  # sem senha: só evita edição acidental das colunas do robô
        ws.protection.autoFilter = False            # o filtro automático continua utilizável
        ws.protection.sort = False
        ws.protection.formatColumns = False

        wc = wb.create_sheet("Ciclos")
        colunas_ciclo = ["ciclo_id", "perfil", "modo", "inicio", "fim", "lidos", "respondidos",
                         "encaminhados", "ignorados", "erros", "reconciliados", "observacao", "nao_fornecedores"]
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
        # v0.3.0 – calibração por categoria (seção 6.5)
        wr.append([])
        acerto_min, minimo = self.criterio
        wr.append(["Calibração por categoria (retorno manual)"])
        wr.cell(row=wr.max_row, column=1).font = Font(bold=True)
        titulos = ["Categoria", "Avaliados", "Corretos", "Acerto (%)", "Erros graves", "Tempo economizado (min)",
                   f"Atinge o critério (≥{acerto_min:.0%} em ≥{minimo})"]
        wr.append(titulos)
        for cel in wr[wr.max_row]:
            cel.font = Font(bold=True, color="FFFFFF")
            cel.fill = cab_retorno
        for d in self.resumo_calibracao():
            wr.append([d["categoria"], d["avaliados"], d["corretos"], round(d["acerto"] * 100, 1), d["graves"],
                       d["tempo"], "SIM" if d["atinge"] else "NÃO"])
        for col in "ABCDEFG":
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
