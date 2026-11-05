import pytest

from rpa_duvidas.config import ErroConfiguracao, carregar, expandir, mesclar


def test_mesclar_recursivo_preserva_o_que_nao_foi_sobrescrito():
    base = {"caixa": {"tipo": "outlook_com", "lote": 50}, "x": [1, 2]}
    final = mesclar(base, {"caixa": {"tipo": "arquivo"}, "x": [3]})
    assert final == {"caixa": {"tipo": "arquivo", "lote": 50}, "x": [3]}
    assert base["caixa"]["tipo"] == "outlook_com"  # base intacta


def test_expandir_variaveis_estilo_windows_e_unix(monkeypatch):
    monkeypatch.setenv("RPA_TESTE_DIR", "C:/Users/fulano")
    assert expandir("%RPA_TESTE_DIR%/Tutoriais") == "C:/Users/fulano/Tutoriais"
    assert expandir("${RPA_TESTE_DIR}/Tutoriais") == "C:/Users/fulano/Tutoriais"


def test_perfil_inexistente(projeto):
    with pytest.raises(ErroConfiguracao, match="não existe"):
        carregar("nao_existe", raiz=projeto)


def test_perfil_por_variavel_de_ambiente(projeto, monkeypatch):
    monkeypatch.setenv("RPA_PERFIL", "demo")
    assert carregar(raiz=projeto).perfil == "demo"


def test_demo_valido(cfg):
    assert cfg.validar() == []
    assert cfg.get("caixa.tipo") == "arquivo"
    assert cfg.envio_real is False


def test_perfil_aponta_valores_a_preencher(projeto):
    # v0.2.1: o dev já foi preenchido na máquina do Pedro; o prod continua com
    # <PREENCHER> até a TI entregar a caixa da automação (S03).
    cfg = carregar("prod", raiz=projeto)
    pend = cfg.pendencias()
    assert any("analistas_cc" in p for p in pend)
    assert any("PREENCHER" in e for e in cfg.validar())


def test_trava_de_seguranca_obrigatoria_fora_de_prod(cfg):
    cfg.dados["seguranca"]["destinatarios_permitidos"] = []
    assert any("destinatarios_permitidos" in e for e in cfg.validar())


def test_destino_manual_por_motivo(cfg):
    cfg.dados["destinatarios"]["analise_manual"]["por_motivo"] = {"SAP": ["sap@empresa-exemplo.com.br"]}
    assert cfg.destino_manual("SAP") == ["sap@empresa-exemplo.com.br"]
    assert cfg.destino_manual("NAO_IDENTIFICADO") == ["analistas.cap@empresa-exemplo.com.br"]


def test_nenhum_endereco_fixo_no_codigo():
    """RNF07 / migração: o código-fonte não pode conter e-mails nem caminhos de pasta reais."""
    import re
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "src"
    for arq in src.rglob("*.py"):
        texto = arq.read_text(encoding="utf-8")
        enderecos = re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", texto)
        assert not enderecos, f"endereço fixo em {arq.name}: {enderecos}"
        assert "C:\\\\Users" not in texto and "C:/Users" not in texto, f"caminho fixo em {arq.name}"
