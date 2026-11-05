"""Montagem do corpo das mensagens a partir dos modelos Jinja2 (F11 – RF05, RF07).

Os textos ficam em ``config/modelos/`` (um arquivo por categoria), para a área
poder alterar sem mexer no código (RNF07).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, select_autoescape

from .modelos import Classificacao, EmailRecebido


class ModeloAusente(Exception):
    pass


def protocolo(email: EmailRecebido) -> str:
    """Identificador curto e estável do e-mail, citado nas mensagens e no registro."""
    return hashlib.sha1(email.chave.encode("utf-8")).hexdigest()[:8].upper()


class GeradorRespostas:
    def __init__(self, pasta_modelos: Path, contexto_fixo: Dict[str, Any],
                 pastas_personalizadas: Sequence[Path] = ()):
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

    def _render(self, nome: str, **ctx: Any) -> str:
        try:
            modelo = self.env.get_template(nome)
        except TemplateNotFound as e:
            raise ModeloAusente(f"Modelo de resposta não encontrado: {self.pasta / nome}") from e
        dados = {**self.contexto_fixo, "data": f"{datetime.now():%d/%m/%Y %H:%M}", **ctx}
        return modelo.render(**dados)

    def existe(self, categoria: str) -> bool:
        return any((p / f"{categoria}.html.j2").exists() for p in self.pastas)

    # ------------------------------------------------------------------ #
    def resposta(self, email: EmailRecebido, categoria: str, *, nome_arquivo: str = "", descricao_tutorial: str = "") -> str:
        return self._render(
            f"{categoria}.html.j2",
            assunto=email.assunto,
            nome_remetente=email.nome_remetente,
            nome_arquivo=nome_arquivo,
            descricao_tutorial=descricao_tutorial,
            protocolo=protocolo(email),
        )

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
        return self._render(
            "encaminhamento_manual.html.j2",
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
