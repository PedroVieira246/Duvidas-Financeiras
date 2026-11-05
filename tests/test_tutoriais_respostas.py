import os
import time
from pathlib import Path

import pytest

from rpa_duvidas.modelos import Categoria, Classificacao, EmailRecebido, MotivoManual
from rpa_duvidas.respostas import GeradorRespostas, ModeloAusente, protocolo
from rpa_duvidas.tutoriais import RepositorioTutoriais, TutorialIndisponivel


def _repo(raiz: Path, **kw):
    dados = {
        "raiz": str(raiz),
        "limite_anexo_mb": kw.get("limite", 20),
        "categorias": {"TUT_CONNECT": {"pasta": "Connect", "padrao": "*.pptx", "descricao": "Acesso"}},
    }
    return RepositorioTutoriais(dados, lambda v: Path(v))


def test_localiza_o_mais_recente(tmp_path):
    pasta = tmp_path / "Connect"
    pasta.mkdir()
    antigo, novo = pasta / "v1.pptx", pasta / "v2.pptx"
    antigo.write_bytes(b"x" * 10)
    novo.write_bytes(b"y" * 10)
    os.utime(antigo, (time.time() - 3600, time.time() - 3600))
    (pasta / "~$v2.pptx").write_bytes(b"lock")  # arquivo temporário do Office é ignorado
    t = _repo(tmp_path).localizar(Categoria.TUT_CONNECT)
    assert t.nome == "v2.pptx"


@pytest.mark.parametrize("preparar, mensagem", [
    (lambda p: None, "Pasta do tutorial não encontrada"),
    (lambda p: (p / "Connect").mkdir(), "Nenhum arquivo"),
    (lambda p: ((p / "Connect").mkdir(), (p / "Connect" / "a.pptx").write_bytes(b"")), "vazio"),
])
def test_falhas_de_validacao(tmp_path, preparar, mensagem):
    preparar(tmp_path)
    with pytest.raises(TutorialIndisponivel, match=mensagem):
        _repo(tmp_path).localizar(Categoria.TUT_CONNECT)


def test_limite_de_tamanho(tmp_path):
    (tmp_path / "Connect").mkdir()
    (tmp_path / "Connect" / "grande.pptx").write_bytes(b"x" * 2 * 1024 * 1024)
    with pytest.raises(TutorialIndisponivel, match="excede"):
        _repo(tmp_path, limite=1).localizar(Categoria.TUT_CONNECT)


def test_categoria_sem_tutorial(tmp_path):
    with pytest.raises(TutorialIndisponivel, match="sem tutorial"):
        _repo(tmp_path).localizar(Categoria.TUT_REEMBOLSO)


def test_tutoriais_ficticios_do_demo_estao_completos(cfg):
    repo = RepositorioTutoriais(cfg.yaml_referenciado("tutoriais.arquivo"), lambda v: cfg.caminho(v, eh_valor=True))
    assert all(ok for _, ok, _ in repo.verificar_todos())


# --------------------------------------------------------------------------- #
@pytest.fixture()
def gerador(cfg):
    return GeradorRespostas(cfg.caminho("respostas.pasta_modelos"),
                            {"assinatura": "Equipe CAP", "faixa_ambiente": "[TESTE]", "link_forms": "https://forms/x"})


@pytest.fixture()
def email():
    return EmailRecebido("<a@b>", "f@x.com", "Fulano", "Assunto", "", "texto", None)


@pytest.mark.parametrize("cat", Categoria.TUTORIAIS)
def test_resposta_tutorial_cita_o_arquivo(gerador, email, cat):
    html = gerador.resposta(email, cat, nome_arquivo="manual.pptx")
    assert "manual.pptx" in html and "Equipe CAP" in html and "[TESTE]" in html
    assert protocolo(email) in html


def test_resposta_forms_traz_o_link(gerador, email):
    assert "https://forms/x" in gerador.resposta(email, Categoria.FORMS_PO)


def test_nota_manual_e_aviso(gerador, email):
    c = Classificacao(Categoria.MANUAL, 0.4, "motivo x", MotivoManual.BAIXA_CONFIANCA, {"categoria_sugerida": "TUT_CONNECT"})
    nota = gerador.nota_manual(email, c, "BAIXA CONFIANÇA")
    assert "BAIXA CONFIANÇA" in nota and "TUT_CONNECT" in nota and "40%" in nota
    assert "falhou &lt;tag&gt;" in gerador.aviso_erro(email, "falhou <tag>", "", "Erro")  # HTML escapado


def test_modelo_ausente(gerador, email):
    with pytest.raises(ModeloAusente):
        gerador.resposta(email, "CATEGORIA_INEXISTENTE")


def test_protocolo_estavel(email):
    assert protocolo(email) == protocolo(EmailRecebido("<A@B>", "", "", "", "", "", None))
