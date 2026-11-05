"""Comando verificar (item p) e scripts/avaliar_classificador.py (item q, seção 6.2)."""
import importlib.util
import shutil

import pytest

from conftest import RAIZ
from rpa_duvidas.__main__ import main
from rpa_duvidas.config import carregar


@pytest.fixture()
def cli(projeto, monkeypatch):
    import rpa_duvidas.config as config

    monkeypatch.setattr("rpa_duvidas.__main__.carregar", lambda p=None: config.carregar(p, raiz=projeto))
    return projeto


def test_verificar_aponta_prompt_quebrado(cli, capsys):
    prompt = cli / "config" / "prompts" / "classificacao_v1.txt"
    prompt.write_text(prompt.read_text(encoding="utf-8").replace("{{CORPO}}", ""), encoding="utf-8")
    assert main(["verificar", "--perfil", "demo_ia"]) == 1
    assert "{{CORPO}}" in capsys.readouterr().out


def test_verificar_aponta_categoria_sem_tutorial_configurado(cli, capsys):
    arq = cli / "config" / "tutoriais_demo.yaml"
    arq.write_text(arq.read_text(encoding="utf-8").replace("  TUT_CADASTRO:", "  TUT_CADASTRO_OUTRO:"), encoding="utf-8")
    assert main(["verificar", "--perfil", "demo_ia"]) == 1
    assert "C05 → TUT_CADASTRO sem entrada no arquivo de tutoriais" in capsys.readouterr().out


def test_verificar_exige_credencial_com_http_generico(cli, capsys, monkeypatch):
    arq = cli / "config" / "perfis" / "demo_ia.yaml"
    arq.write_text(arq.read_text(encoding="utf-8").replace(
        "      tipo: simulado                       # nunca chama IA real",
        "      tipo: http_generico\n      http_generico:\n        endpoint: \"https://ia.exemplo.invalid\"\n"
        "        modelo: \"m\"\n        credencial: \"ia_teste_inexistente\""), encoding="utf-8")
    monkeypatch.setattr("rpa_duvidas.segredos.obter", lambda nome, obrigatorio=True: None)
    assert main(["verificar", "--perfil", "demo_ia"]) == 1
    assert "Credencial da IA 'ia_teste_inexistente' não encontrada" in capsys.readouterr().out


def test_verificar_alerta_lista_de_fornecedores_vazia_em_prod(cli, capsys, monkeypatch):
    class CaixaFalsa:                      # não abre o Outlook de verdade durante o teste
        def verificar(self):
            return []
    monkeypatch.setattr("rpa_duvidas.__main__.criar_caixa", lambda cfg: CaixaFalsa())
    assert carregar("prod", raiz=cli).ambiente == "prod"
    assert main(["verificar", "--perfil", "prod"]) == 1
    assert "lista de fornecedores VAZIA em prod" in capsys.readouterr().out


def test_verificar_palavras_chave_continua_ok(cli, capsys):
    assert main(["verificar", "--perfil", "demo"]) == 0
    assert "tipo: palavras_chave | limite de confiança efetivo: 0.70" in capsys.readouterr().out


def _script():
    spec = importlib.util.spec_from_file_location("avaliar_classificador", RAIZ / "scripts" / "avaliar_classificador.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_avaliar_ia_em_varios_limites(projeto, tmp_path, monkeypatch):
    mod = _script()
    monkeypatch.setattr(mod, "carregar", lambda p=None: carregar(p, raiz=projeto))
    cfg = mod.preparar("demo", "ia")
    assert cfg.classificador == "ia" and cfg.limite_confianca == 0.80
    massa = tmp_path / "massa.csv"
    massa.write_text(
        "id,assunto,corpo,categoria_esperada\n"
        "A1,NF,\"Precisamos inserir a NF no sistema, como fazemos?\",TUT_UPLOAD_NF\n"
        "A2,Proposta,\"Alguma novidade sobre a proposta?\",MANUAL\n"
        "A3,Cadastro,\"Houve alteração societária, como atualizar o cadastro?\",TUT_CADASTRO\n", encoding="utf-8")
    limites = mod._limites("0.70,0.75,0.80,0.85,0.90")
    por_limite = mod.avaliar_limites(massa, cfg, limites)
    assert sorted(por_limite) == [0.7, 0.75, 0.8, 0.85, 0.9]
    ind80 = mod.indicadores(por_limite[0.8])
    assert ind80["acertos"] == 3 and ind80["graves"] == 0 and ind80["manuais"] == 1
    ind90 = mod.indicadores(por_limite[0.9])                     # 0.93 e 0.94 passam; nada muda
    assert ind90["acertos"] == 3
    tabela = mod.tabela_calibracao(por_limite)
    assert "| 0.70 |" in tabela and "Menor limite com zero erros graves: 0.70" in tabela


def test_avaliar_main_gera_relatorio(projeto, tmp_path, monkeypatch, capsys):
    mod = _script()
    monkeypatch.setattr(mod, "carregar", lambda p=None: carregar(p, raiz=projeto))
    massa = RAIZ / "tests" / "dados" / "massa_emails_sintetica.csv"
    assert mod.main(["--massa", str(massa), "--classificador", "ia", "--limites", "0.70,0.80,0.90",
                     "--saida", str(tmp_path)]) == 0
    saida = capsys.readouterr().out
    assert "Classificador: **ia**" in saida and "Calibração do limite de confiança" in saida
    assert list(tmp_path.glob("avaliacao_*.md")) and list(tmp_path.glob("avaliacao_*.csv"))


def test_avaliar_palavras_chave_compativel_com_v010(projeto, monkeypatch):
    mod = _script()
    monkeypatch.setattr(mod, "carregar", lambda p=None: carregar(p, raiz=projeto))
    linhas, limite = mod.avaliar(RAIZ / "tests" / "dados" / "massa_emails_sintetica.csv", "demo")
    assert limite == 0.70 and len(linhas) == 40
    assert sum(l["acerto"] == "sim" for l in linhas) == 40 and not any(l["erro_grave"] for l in linhas)
