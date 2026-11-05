"""Fixtures comuns: um projeto temporário com o perfil demo (caixa simulada)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from rpa_duvidas.config import carregar

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture()
def projeto(tmp_path: Path) -> Path:
    """Cópia de config/ e dos tutoriais fictícios num diretório temporário."""
    shutil.copytree(RAIZ / "config", tmp_path / "config")
    shutil.copytree(RAIZ / "dados_teste" / "tutoriais", tmp_path / "dados_teste" / "tutoriais")
    (tmp_path / "dados_teste" / "caixa_simulada" / "entrada").mkdir(parents=True)
    return tmp_path


@pytest.fixture()
def cfg(projeto):
    return carregar("demo", raiz=projeto)


@pytest.fixture()
def entrada(projeto) -> Path:
    return projeto / "dados_teste" / "caixa_simulada" / "entrada"


@pytest.fixture()
def novo_email(entrada):
    """Cria um e-mail .json na caixa simulada. Devolve o caminho."""
    contador = {"n": 0}

    def _novo(assunto: str, corpo: str = "", remetente: str = "maria@fornecedor-exemplo.com.br", **extra) -> Path:
        contador["n"] += 1
        n = contador["n"]
        dados = {
            "id_mensagem": f"<teste-{n}@local>",
            "remetente": remetente,
            "nome_remetente": "Teste",
            "assunto": assunto,
            "corpo_texto": corpo,
            "data_recebimento": f"2026-10-19T08:{n:02d}:00",
        }
        dados.update(extra)
        caminho = entrada / f"{n:03d}.json"
        caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return caminho

    return _novo


# --------------------------------------------------------------------------- #
# v0.2.0 – classificação por IA (perfil demo_ia, provedor simulado)
# --------------------------------------------------------------------------- #
@pytest.fixture()
def cfg_ia(projeto):
    """Perfil demo_ia: caixa simulada + classificacao.tipo = ia + provedor simulado."""
    return carregar("demo_ia", raiz=projeto)


def json_ia(**sobrescrever):
    """Resposta da IA válida (contrato da seção 5.1), com campos sobrescrevíveis."""
    base = {
        "categoria": "C03", "categorias_secundarias": [], "tutorial": "TUT_UPLOAD_NF", "confianca": 0.92,
        "acao": "RESPONDER_TUTORIAL", "sinais_excecao": [], "resumo_duvida": None,
        "justificativa": "Pergunta como inserir a NF no portal.",
    }
    base.update(sobrescrever)
    return base
