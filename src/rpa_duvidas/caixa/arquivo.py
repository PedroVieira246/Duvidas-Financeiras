"""Caixa de e-mail SIMULADA em disco (demonstração e testes).

Implementa a mesma interface ``CaixaEmail`` do Outlook, então o ciclo inteiro
roda em qualquer máquina, sem Outlook e sem tocar em e-mail real.

Estrutura (``caixa.arquivo.raiz``)::

    entrada/        e-mails pendentes (.json ou .eml)
    respondidos/    ┐
    encaminhados/   ├ destinos (nomes vêm de caixa.pastas_destino)
    erro/           │
    ignorados/      ┘
    saida/          mensagens geradas pelo robô (.json + .html para abrir no
                    navegador) e _indice.html com todas elas

Formato .json de entrada::

    {"id_mensagem": "...", "remetente": "...", "nome_remetente": "...",
     "assunto": "...", "corpo_html": "..." | "corpo_texto": "...",
     "data_recebimento": "2026-10-19T09:30:00", "anexos": ["nf.pdf"],
     "cabecalhos": {"Auto-Submitted": "auto-replied"},
     "classe_mensagem": "IPM.Note",
     "simular_falha": "responder" | "encaminhar" | "finalizar"   (só testes)}
"""
from __future__ import annotations

import email as email_lib
import html
import json
import shutil
import uuid
from datetime import datetime
from email import policy
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..modelos import EmailRecebido
from .base import CaixaEmail, ErroCaixa, TravaDestinatarios


class CaixaArquivo(CaixaEmail):
    def __init__(self, raiz: Path, pasta_entrada: str, pastas_destino: Dict[str, str], criar: bool = True,
                 mover_apos_tratar: bool = True, trava: Optional[TravaDestinatarios] = None):
        self.raiz = Path(raiz)
        self.trava = trava
        self.mover = bool(mover_apos_tratar)   # v0.3.0: False imita a caixa pessoal (nada sai da entrada)
        self.entrada = self.raiz / pasta_entrada
        self.destinos = {k: self.raiz / v for k, v in pastas_destino.items()}
        self.saida = self.raiz / "saida"
        if criar:
            for p in [self.entrada, self.saida, *self.destinos.values()]:
                p.mkdir(parents=True, exist_ok=True)
        self._arquivos: Dict[str, Path] = {}
        self._brutos: Dict[str, dict] = {}

    # ------------------------------------------------------------------ #
    # leitura
    # ------------------------------------------------------------------ #
    def ler_pendentes(self, limite: int, aceitar_remetente=None) -> List[EmailRecebido]:
        if not self.entrada.exists():
            raise ErroCaixa(f"Pasta de entrada não existe: {self.entrada}")
        self.descartados = 0
        emails: List[EmailRecebido] = []
        for arq in sorted(self.entrada.iterdir()):
            if arq.suffix.lower() == ".json":
                bruto = json.loads(arq.read_text(encoding="utf-8"))
            elif arq.suffix.lower() == ".eml":
                bruto = _eml_para_dict(arq)
            else:
                continue
            em = _dict_para_email(bruto, arq)
            if bruto.get("categorias_outlook") and not self.mover:
                continue                                  # modo sem mover: já tratado
            if aceitar_remetente is not None and not aceitar_remetente(em.remetente):
                self.descartados += 1                     # não fornecedor: arquivo intocado
                continue
            self._arquivos[em.chave] = arq
            self._brutos[em.chave] = bruto
            emails.append(em)
        emails.sort(key=lambda e: (e.data_recebimento or datetime.min, e.id_mensagem))
        return emails[: max(0, int(limite))]

    # ------------------------------------------------------------------ #
    # ações
    # ------------------------------------------------------------------ #
    def _falha(self, email: EmailRecebido, etapa: str) -> None:
        if self._brutos.get(email.chave, {}).get("simular_falha") == etapa:
            raise ErroCaixa(f"Falha simulada em '{etapa}' (teste)")

    def responder(self, email, corpo_html, *, anexos=(), cc=(), responder_todos=False, enviar=False,
                  redirecionar_para=None, prefixo_assunto="") -> str:
        self._falha(email, "responder")
        assunto = email.assunto if email.assunto.lower().startswith("re:") else f"RE: {email.assunto}"
        if prefixo_assunto:
            assunto = f"{prefixo_assunto} {assunto}"
        para, cc = ([redirecionar_para], []) if redirecionar_para else ([email.remetente], list(cc))
        if redirecionar_para:
            TravaDestinatarios([redirecionar_para], [], []).conferir("responder", para + cc)
        return self._gravar_saida(
            tipo="RESPOSTA", para=para, cc=cc, assunto=assunto,
            corpo_html=corpo_html, anexos=[str(a) for a in anexos], enviar=enviar,
            em_resposta_a=email.id_mensagem, operacao="responder",
            destinatario_original=email.remetente if redirecionar_para else "",
        )

    def encaminhar(self, email, para, prefixo_assunto, nota_html, *, enviar=False) -> str:
        self._falha(email, "encaminhar")
        original = (
            "<hr><p><b>De:</b> {r}<br><b>Assunto:</b> {a}</p>{c}".format(
                r=html.escape(f"{email.nome_remetente} <{email.remetente}>"),
                a=html.escape(email.assunto),
                c=email.corpo_html or f"<pre>{html.escape(email.corpo_texto_bruto)}</pre>",
            )
        )
        return self._gravar_saida(
            tipo="ENCAMINHAMENTO", para=list(para), cc=[], assunto=f"{prefixo_assunto} {email.assunto}",
            corpo_html=nota_html + original, anexos=list(email.nomes_anexos), enviar=enviar,
            em_resposta_a=email.id_mensagem, operacao="encaminhar",
        )

    def enviar_novo(self, para, assunto, corpo_html, *, enviar=False) -> str:
        return self._gravar_saida(
            tipo="AVISO", para=list(para), cc=[], assunto=assunto, corpo_html=corpo_html,
            anexos=[], enviar=enviar, em_resposta_a="", operacao="enviar_novo",
        )

    def finalizar(self, email: EmailRecebido, destino: str, categoria: Optional[str] = None, *,
                  marcar_lido: bool = True) -> None:
        self._falha(email, "finalizar")
        arq = self._arquivos.get(email.chave)
        if arq is None or not arq.exists():
            raise ErroCaixa(f"E-mail não está mais na entrada: {email.id_mensagem}")
        pasta = self.destinos.get(destino)
        if pasta is None:
            raise ErroCaixa(f"Destino desconhecido: {destino}")
        pasta.mkdir(parents=True, exist_ok=True)
        if arq.suffix.lower() == ".json":
            bruto = json.loads(arq.read_text(encoding="utf-8"))
            if marcar_lido:
                bruto["lido"] = True
            if categoria:
                bruto.setdefault("categorias_outlook", []).append(categoria)
            arq.write_text(json.dumps(bruto, ensure_ascii=False, indent=2), encoding="utf-8")
        if not self.mover:
            return                                        # v0.3.0 – modo sem mover: fica na entrada
        alvo = pasta / arq.name
        if alvo.exists():
            alvo = pasta / f"{arq.stem}_{uuid.uuid4().hex[:6]}{arq.suffix}"
        shutil.move(str(arq), str(alvo))
        self._arquivos[email.chave] = alvo

    def verificar(self) -> List[str]:
        return [] if self.entrada.exists() else [f"Pasta de entrada não existe: {self.entrada}"]

    # ------------------------------------------------------------------ #
    # saída visual
    # ------------------------------------------------------------------ #
    def _gravar_saida(self, *, tipo, para, cc, assunto, corpo_html, anexos, enviar, em_resposta_a,
                      operacao="", destinatario_original="") -> str:
        if self.trava is not None:
            self.trava.conferir(operacao, list(para) + list(cc))      # seção 6.2, item 4
        self.saida.mkdir(parents=True, exist_ok=True)
        ident = f"{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
        modo = "ENVIADO" if enviar else "RASCUNHO"
        dados = {
            "id": ident, "tipo": tipo, "modo": modo, "para": para, "cc": cc,
            "assunto": assunto, "anexos": [Path(a).name for a in anexos],
            "destinatario_original": destinatario_original,
            "caminhos_anexos": anexos, "em_resposta_a": em_resposta_a,
            "gerado_em": datetime.now().isoformat(timespec="seconds"), "corpo_html": corpo_html,
        }
        (self.saida / f"{ident}_{tipo}.json").write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")
        (self.saida / f"{ident}_{tipo}.html").write_text(_html_visual(dados), encoding="utf-8")
        self._atualizar_indice()
        return ident

    def _atualizar_indice(self) -> None:
        linhas = []
        for arq in sorted(self.saida.glob("*.json")):
            d = json.loads(arq.read_text(encoding="utf-8"))
            linhas.append(
                "<tr><td>{g}</td><td>{t}</td><td>{m}</td><td>{p}</td><td><a href='{h}'>{a}</a></td><td>{x}</td></tr>".format(
                    g=d["gerado_em"], t=d["tipo"], m=d["modo"], p=html.escape(", ".join(d["para"])),
                    h=arq.with_suffix(".html").name, a=html.escape(d["assunto"]),
                    x=html.escape(", ".join(d["anexos"])) or "—",
                )
            )
        (self.saida / "_indice.html").write_text(
            _PAGINA.format(
                titulo="Mensagens geradas pelo robô",
                corpo="<table><tr><th>Gerado em</th><th>Tipo</th><th>Modo</th><th>Para</th>"
                "<th>Assunto</th><th>Anexo</th></tr>" + "".join(linhas) + "</table>",
            ),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------- #
# conversões
# ---------------------------------------------------------------------- #
def _dict_para_email(d: dict, arq: Path) -> EmailRecebido:
    data = d.get("data_recebimento")
    try:
        data_dt = datetime.fromisoformat(data) if data else None
    except ValueError:
        data_dt = None
    anexos = list(d.get("anexos") or [])
    return EmailRecebido(
        id_mensagem=str(d.get("id_mensagem") or arq.stem),
        remetente=str(d.get("remetente", "")).strip().lower(),
        nome_remetente=str(d.get("nome_remetente", "")),
        assunto=str(d.get("assunto", "")),
        corpo_html=str(d.get("corpo_html", "")),
        corpo_texto_bruto=str(d.get("corpo_texto", "")),
        data_recebimento=data_dt,
        tem_anexos=bool(anexos),
        nomes_anexos=anexos,
        cabecalhos={str(k).lower(): str(v) for k, v in (d.get("cabecalhos") or {}).items()},
        classe_mensagem=str(d.get("classe_mensagem", "IPM.Note")),
        id_conversa=str(d.get("id_conversa", "")),
        ultimo_verbo=int(d.get("ultimo_verbo") or 0),
    )


def _eml_para_dict(arq: Path) -> dict:
    msg = email_lib.message_from_bytes(arq.read_bytes(), policy=policy.default)
    corpo_html = corpo_texto = ""
    anexos = []
    for parte in msg.walk():
        if parte.is_multipart():
            continue
        if parte.get_filename():
            anexos.append(parte.get_filename())
        elif parte.get_content_type() == "text/html" and not corpo_html:
            corpo_html = parte.get_content()
        elif parte.get_content_type() == "text/plain" and not corpo_texto:
            corpo_texto = parte.get_content()
    nome, endereco = email_lib.utils.parseaddr(str(msg.get("From", "")))
    data = None
    try:
        data = email_lib.utils.parsedate_to_datetime(str(msg.get("Date"))).replace(tzinfo=None).isoformat()
    except Exception:
        pass
    return {
        "id_mensagem": str(msg.get("Message-ID") or arq.stem),
        "remetente": endereco, "nome_remetente": nome, "assunto": str(msg.get("Subject", "")),
        "corpo_html": corpo_html, "corpo_texto": corpo_texto, "data_recebimento": data,
        "anexos": anexos, "cabecalhos": {k: str(v) for k, v in msg.items()},
    }


_PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{titulo}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;color:#1e293b}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #cbd5e1;padding:6px 8px;text-align:left;font-size:13px}}
th{{background:#f1f5f9}}.cab td:first-child{{width:110px;font-weight:600;background:#f8fafc}}
.modo{{display:inline-block;padding:2px 8px;border-radius:4px;font-weight:600}}
.RASCUNHO{{background:#fef3c7;color:#92400e}}.ENVIADO{{background:#dcfce7;color:#166534}}
.corpo{{border:1px solid #cbd5e1;padding:16px;margin-top:16px}}</style></head>
<body><h2>{titulo}</h2>{corpo}</body></html>"""


def _html_visual(d: dict) -> str:
    cab = (
        "<table class='cab'>"
        f"<tr><td>Modo</td><td><span class='modo {d['modo']}'>{d['modo']}</span> · {d['tipo']}</td></tr>"
        f"<tr><td>Para</td><td>{html.escape(', '.join(d['para']))}</td></tr>"
        f"<tr><td>Cc</td><td>{html.escape(', '.join(d['cc'])) or '—'}</td></tr>"
        f"<tr><td>Assunto</td><td>{html.escape(d['assunto'])}</td></tr>"
        f"<tr><td>Anexos</td><td>{html.escape(', '.join(d['anexos'])) or '—'}</td></tr>"
        f"<tr><td>Gerado em</td><td>{d['gerado_em']}</td></tr></table>"
    )
    return _PAGINA.format(titulo=html.escape(d["assunto"]), corpo=cab + f"<div class='corpo'>{d['corpo_html']}</div>")
