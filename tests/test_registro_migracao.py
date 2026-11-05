"""E8 – novas colunas, tabela respostas_ia e migração automática de um banco v0.1.0 (lacuna R7)."""
import sqlite3

from rpa_duvidas.modelos import Acao, Classificacao, EmailRecebido, Resultado, Status
from rpa_duvidas.registro import COLUNAS_EVENTO, Registro

# Esquema EXATO da v0.1.0 (registro.py, 19/10/2026)
COLUNAS_V010 = ["data_hora", "ciclo_id", "perfil", "modo", "protocolo", "id_mensagem", "recebido_em", "remetente",
                "assunto", "tem_anexos", "categoria", "categoria_sugerida", "confianca", "motivo", "motivo_manual",
                "acao", "arquivo_enviado", "destinatarios", "destino", "status", "erro", "duracao_ms"]
SQL_V010 = f"""
CREATE TABLE estado (chave TEXT PRIMARY KEY, protocolo TEXT, status TEXT, acao TEXT, destino TEXT,
    acao_executada INTEGER DEFAULT 0, criado_em TEXT, atualizado_em TEXT);
CREATE TABLE eventos (id INTEGER PRIMARY KEY AUTOINCREMENT, {", ".join(c + " TEXT" for c in COLUNAS_V010)});
CREATE TABLE ciclos (ciclo_id TEXT PRIMARY KEY, perfil TEXT, modo TEXT, inicio TEXT, fim TEXT,
    lidos INTEGER, respondidos INTEGER, encaminhados INTEGER, ignorados INTEGER,
    erros INTEGER, reconciliados INTEGER, observacao TEXT);
"""
NOVAS = ["classificador", "categoria_docx", "categorias_secundarias", "sinais_excecao", "resumo_duvida",
         "regra_decisao", "modelo_ia", "versao_prompt", "hash_prompt", "latencia_ia_ms", "tentativas_ia", "tokens"]


def _banco_v010(caminho):
    con = sqlite3.connect(str(caminho))
    con.executescript(SQL_V010)
    con.execute("INSERT INTO eventos (protocolo, categoria, status) VALUES ('ABCD1234', 'TUT_CONNECT', 'SIMULADO')")
    con.execute("INSERT INTO estado (chave, protocolo, status, acao, acao_executada) VALUES ('<x@y>', 'ABCD1234', 'SIMULADO', 'RESPONDER_TUTORIAL', 1)")
    con.commit()
    con.close()


def test_rn81_colunas_novas_estao_no_registro():
    nomes = [c for c, _ in COLUNAS_EVENTO]
    assert nomes[:22] == COLUNAS_V010                         # ordem antiga preservada
    assert all(n in nomes for n in NOVAS)


def test_migracao_de_banco_v010_preserva_dados_e_cria_colunas(tmp_path):
    banco = tmp_path / "estado.db"
    _banco_v010(banco)
    reg = Registro(banco, "demo")
    assert reg.colunas_migradas == NOVAS
    colunas = {r[1] for r in reg.con.execute("PRAGMA table_info(eventos)")}
    assert set(NOVAS) <= colunas
    assert reg.eventos()[0]["protocolo"] == "ABCD1234" and reg.eventos()[0]["classificador"] is None
    assert reg.estado("<x@y>")["acao_executada"] == 1          # idempotência mantida
    assert reg.respostas_ia() == []
    reg.fechar()
    assert Registro(banco, "demo").colunas_migradas == []      # 2ª abertura: nada a migrar


def test_gravar_evento_da_ia_e_resposta_bruta_em_tabela_separada(tmp_path):
    banco = tmp_path / "estado.db"
    _banco_v010(banco)
    reg = Registro(banco, "demo")
    email = EmailRecebido("<ia@t>", "f@fornecedor-exemplo.com.br", "F", "Assunto", "", "texto", None)
    c = Classificacao("MANUAL", 0.88, "IA C03", "MULTIPLAS_DUVIDAS", {
        "classificador": "ia", "categoria_docx": "C03", "categorias_secundarias": ["C05"],
        "sinais_excecao": ["ERRO_SISTEMA"], "resumo_duvida": "O fornecedor não consegue subir a NF.",
        "regra_decisao": "D4", "modelo": "sim", "versao_prompt": "classificacao_v1", "hash_prompt": "abc123",
        "latencia_ms": 15, "tentativas": 2, "tokens": 900,
        "respostas_brutas": [{"chamada": 1, "texto": "lixo", "valida": False}, {"chamada": 2, "texto": "{}", "valida": True}],
    })
    reg.gravar(Resultado(email=email, acao=Acao.ENCAMINHAR_MANUAL, status=Status.SIMULADO, classificacao=c), "c1", "SIMULACAO")
    ev = reg.eventos()[-1]
    assert (ev["classificador"], ev["categoria_docx"], ev["categorias_secundarias"], ev["sinais_excecao"]) == \
        ("ia", "C03", "C05", "ERRO_SISTEMA")
    assert (ev["regra_decisao"], ev["modelo_ia"], ev["versao_prompt"], ev["latencia_ia_ms"], ev["tentativas_ia"], ev["tokens"]) == \
        ("D4", "sim", "classificacao_v1", "15", "2", "900")
    assert ev["resumo_duvida"] == "O fornecedor não consegue subir a NF."
    brutas = reg.respostas_ia()
    assert [(b["chamada"], b["valida"], b["resposta_bruta"]) for b in brutas] == [(1, 0, "lixo"), (2, 1, "{}")]
    assert "lixo" not in str(dict(ev))                          # o JSON bruto não vai para eventos/planilha

    destino = tmp_path / "controle.xlsx"
    assert reg.exportar_planilha(destino)
    from openpyxl import load_workbook

    cab = [c.value for c in load_workbook(destino)["Registro"][1]]
    assert "Resumo da dúvida (IA)" in cab and "Regra de decisão" in cab and "Tokens" in cab
    reg.fechar()
