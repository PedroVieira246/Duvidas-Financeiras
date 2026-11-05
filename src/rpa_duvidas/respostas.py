"""Montagem do corpo das mensagens a partir dos modelos Jinja2 (F11 – RF05, RF07).

Os textos ficam em ``config/modelos/`` (um arquivo por categoria), para a área
poder alterar sem mexer no código (RNF07).
"""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, select_autoescape
from markupsafe import Markup

from .modelos import Classificacao, EmailRecebido


class ModeloAusente(Exception):
    pass


_RE_CAMPO = re.compile(r"\{([a-z_]+)\}")
_RE_URL = re.compile(r"(https://[^\s<>\"']+)")


def substituir_campos(texto: str, campos: Dict[str, Any]) -> str:
    """Troca ``{campo}`` pelos valores (campos desconhecidos ficam como estão – o leitor da planilha já os recusa)."""
    return _RE_CAMPO.sub(lambda m: str(campos.get(m.group(1), m.group(0))), texto or "")


def texto_html(texto: str, campos: Dict[str, Any], *, quebra: str = "p") -> Markup:
    """Texto da aba Textos → HTML seguro (seção 5.5): escapado, sem HTML livre, uma linha por ``<p>``
    (ou ``<br>`` com ``quebra="br"``). Endereços https:// viram link."""
    linhas = [html.escape(l.strip()) for l in substituir_campos(texto, campos).replace("\r\n", "\n").split("\n")]
    linhas = [_RE_URL.sub(r'<a href="\1">\1</a>', l) for l in linhas]
    if quebra == "br":
        return Markup("<br>".join(linhas))
    return Markup("".join(f"<p>{l}</p>" for l in linhas if l))


def protocolo(email: EmailRecebido) -> str:
    """Identificador curto e estável do e-mail, citado nas mensagens e no registro."""
    return hashlib.sha1(email.chave.encode("utf-8")).hexdigest()[:8].upper()


class GeradorRespostas:
    def __init__(self, pasta_modelos: Path, contexto_fixo: Dict[str, Any],
                 pastas_personalizadas: Sequence[Path] = (), textos: Optional[Dict[str, Dict[str, str]]] = None):
        """``pastas_personalizadas`` (v0.3.0): pastas consultadas ANTES da padrão; um
        .j2 com o mesmo nome substitui o modelo empacotado, arquivo a arquivo."""
        self.pasta = Path(pasta_modelos)
        self.pastas = [Path(p) for p in pastas_personalizadas if Path(p).is_dir()] + [self.pasta]
        self.env = Environment(
            loader=FileSystemLoader([str(p) for p in self.pastas]),
            autoescape=select_autoescape(["html", "j2"]),
            undefined=StrictUndefined,      # variável faltando = erro, não texto vazio
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.contexto_fixo = dict(contexto_fixo)
        self.textos: Dict[str, Dict[str, str]] = dict(textos or {})   # v0.3.0 – aba Textos (seção 5.5)

    def _render(self, nome: str, **ctx: Any) -> str:
        try:
            modelo = self.env.get_template(nome)
        except TemplateNotFound as e:
            raise ModeloAusente(f"Modelo de resposta não encontrado: {self.pasta / nome}") from e
        dados = {**self.contexto_fixo, "data": f"{datetime.now():%d/%m/%Y %H:%M}", **ctx}
        faixa = dados.get("faixa_ambiente")
        if isinstance(faixa, str) and "{destinatario_original}" in faixa:   # perfil calibracao (seção 4.3)
            dados["faixa_ambiente"] = faixa.replace("{destinatario_original}",
                                                    str(ctx.get("destinatario_original") or "—"))
        return modelo.render(**dados)

    def existe(self, categoria: str) -> bool:
        return any((p / f"{categoria}.html.j2").exists() for p in self.pastas)

    # ------------------------------------------------------------------ #
    # ---- aba Textos (v0.3.0) ------------------------------------------- #
    def campos_texto(self, email: EmailRecebido, nome_arquivo: str = "") -> Dict[str, Any]:
        """Campos disponíveis na aba Textos: {nome_fornecedor}, {protocolo}, {nome_arquivo},
        {link_formulario}, {analista}, {data}."""
        return {
            "nome_fornecedor": email.nome_remetente or "", "protocolo": protocolo(email), "nome_arquivo": nome_arquivo,
            "link_formulario": self.contexto_fixo.get("link_forms", ""), "analista": self.contexto_fixo.get("analista", ""),
            "data": f"{datetime.now():%d/%m/%Y}",
        }

    def tem_texto(self, codigo: Optional[str]) -> bool:
        return bool(codigo) and codigo in self.textos

    def prefixo_assunto(self, codigo: Optional[str], email: EmailRecebido) -> str:
        if not self.tem_texto(codigo):
            return ""
        return substituir_campos(self.textos[codigo].get("assunto_prefixo", ""), self.campos_texto(email)).strip()

    def _textos_fixos(self, campos: Dict[str, Any]) -> Dict[str, Any]:
        """AVISO_AUTOMATICO (D09) e ASSINATURA, inseridos em TODA resposta (rascunho ou envio)."""
        extra: Dict[str, Any] = {}
        if self.textos.get("AVISO_AUTOMATICO", {}).get("corpo"):
            extra["aviso_automatico_html"] = texto_html(self.textos["AVISO_AUTOMATICO"]["corpo"], campos)
        if self.textos.get("ASSINATURA", {}).get("corpo"):
            extra["assinatura_html"] = texto_html(self.textos["ASSINATURA"]["corpo"], campos, quebra="br")
        return extra

    def resposta(self, email: EmailRecebido, categoria: str, *, nome_arquivo: str = "", descricao_tutorial: str = "",
                 destinatario_original: str = "", codigo_texto: Optional[str] = None) -> str:
        """Resposta ao fornecedor. Com ``codigo_texto`` existente na aba Textos, o texto da planilha
        tem prioridade sobre o ``.j2`` da categoria (o layout continua no ``_base.html.j2``)."""
        campos = self.campos_texto(email, nome_arquivo)
        ctx = dict(
            assunto=email.assunto,
            nome_remetente=email.nome_remetente,
            nome_arquivo=nome_arquivo,
            descricao_tutorial=descricao_tutorial,
            protocolo=protocolo(email),
            destinatario_original=destinatario_original,
            **self._textos_fixos(campos),
        )
        if self.tem_texto(codigo_texto):
            return self._render("TEXTO.html.j2", conteudo_html=texto_html(self.textos[codigo_texto]["corpo"], campos), **ctx)
        return self._render(f"{categoria}.html.j2", **ctx)

    def nota_manual(self, email: EmailRecebido, c: Optional[Classificacao], rotulo_motivo: str) -> str:
        """Nota interna do encaminhamento (E7).

        Desde a v0.2.0 inclui o resumo da IA, a categoria do .docx, as dúvidas
        secundárias e os sinais de exceção (RN7.2). Como o modelo usa
        ``StrictUndefined``, estas variáveis são SEMPRE passadas (vazias quando
        o classificador não as produz) – lacuna R6.
        """
        d = c.detalhes if c else {}
        cat_docx = str(d.get("categoria_docx") or "")
        if cat_docx and d.get("categoria_docx_descricao"):
            cat_docx = f"{cat_docx} – {d['categoria_docx_descricao']}"
        extra = {}
        if self.textos.get("NOTA_MANUAL", {}).get("corpo"):
            extra["nota_texto_html"] = texto_html(self.textos["NOTA_MANUAL"]["corpo"], self.campos_texto(email))
        return self._render(
            "encaminhamento_manual.html.j2",
            **extra,
            rotulo_motivo=rotulo_motivo,
            categoria=(d.get("categoria_sugerida") or c.categoria) if c else "—",
            confianca=c.confianca if c else 0.0,
            justificativa=c.motivo if c else "—",
            remetente=email.remetente,
            tem_anexos=email.tem_anexos,
            nomes_anexos=", ".join(email.nomes_anexos),
            protocolo=protocolo(email),
            resumo_duvida=str(d.get("resumo_duvida") or ""),
            categoria_docx=cat_docx,
            duvidas_secundarias=", ".join(d.get("categorias_secundarias") or []),
            sinais_excecao=", ".join(d.get("sinais_excecao") or []),
        )

    def aviso_ia_indisponivel(self, falhas: int) -> str:
        """Aviso único aos analistas quando a IA é desligada no ciclo (RNF-IA03)."""
        return self._render("aviso_ia_indisponivel.html.j2", falhas=falhas)

    def aviso_bloqueio(self, categoria: str, protocolos, data_liberacao: str) -> str:
        """v0.3.0 – bloqueio automático por "Tutorial errado" (seção 6.7)."""
        return self._render("aviso_bloqueio.html.j2", categoria=categoria, protocolos=", ".join(protocolos),
                            data_liberacao=data_liberacao)

    def aviso_falha_ciclo(self, mensagem: str) -> str:
        """v0.3.0 – o ciclo não rodou (ex.: planilha de escritórios indisponível – seção 5.9)."""
        return self._render("aviso_falha_ciclo.html.j2", mensagem=mensagem)

    def aviso_erro(self, email: EmailRecebido, erro: str, categoria: str, pasta_erro: str, movido: bool = True) -> str:
        return self._render(
            "aviso_erro.html.j2",
            remetente=email.remetente or "(desconhecido)",
            assunto=email.assunto,
            recebido=f"{email.data_recebimento:%d/%m/%Y %H:%M}" if email.data_recebimento else "—",
            categoria=categoria,
            erro=erro,
            pasta_erro=pasta_erro,
            movido=movido,
            protocolo=protocolo(email),
        )
