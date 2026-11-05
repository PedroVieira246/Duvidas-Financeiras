"""v0.3.0 – T10: textos da aba Textos e aviso de resposta automática (D09 – seção 5.5)."""
import json

from conftest import preencher_calibracao, usar_caixa_simulada
from rpa_duvidas import config_xlsx_esquema as E
from rpa_duvidas import extracao
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.config import carregar
from rpa_duvidas.config_xlsx_modelo import gerar_modelo
from rpa_duvidas.modelos import Acao, EmailRecebido, Status
from rpa_duvidas.respostas import texto_html

FORNECEDOR = "ana@fornecedor-exemplo.com.br"


def _email(entrada, assunto, corpo, n=1):
    (entrada / f"{n:03d}.json").write_text(json.dumps({
        "id_mensagem": f"<{n}@x>", "remetente": FORNECEDOR, "nome_remetente": "Ana Souza", "assunto": assunto,
        "corpo_texto": corpo, "data_recebimento": "2026-11-03T09:00:00"}), encoding="utf-8")


def _rodar(cfg, projeto):
    robo = montar_dependencias(cfg)
    try:
        resumo = robo.executar_ciclo()
    finally:
        robo.registro.fechar()
    saida = projeto / "dados_teste" / "caixa_simulada" / "saida"
    return resumo, [json.loads(p.read_text(encoding="utf-8")) for p in sorted(saida.glob("*_RESPOSTA.json"))]


def test_rascunho_com_o_aviso_e_os_campos_substituidos(projeto_cal, cfg_cal, entrada):
    """Critério da T10."""
    _email(entrada, "Pedido de compra", "preciso do pedido de compra")
    resumo, [resp] = _rodar(cfg_cal, projeto_cal)
    assert resumo.resultados[0].status == Status.SIMULADO and resp["modo"] == "RASCUNHO"
    html = resp["corpo_html"]
    assert E.TEXTO_AVISO_AUTOMATICO in html                       # D09: aviso em toda resposta
    assert "Maria Laura<br>Equipe Financeiro – Contas a Pagar" in html   # {analista} substituído
    assert "{analista}" not in html
    # o rodapé que protege contra laço continua lá
    assert extracao.detectar_mensagem_do_rpa(
        EmailRecebido("<x>", "", "", "RE: x", "", "", None),
        extracao.normalizar(extracao.html_para_texto(html)), cfg_cal.get("filtros.mensagens_do_rpa"))[0]


def test_codigo_do_texto_tem_prioridade_sobre_o_modelo(projeto, entrada):
    preencher_calibracao(
        projeto,
        categorias={"TUT_REEMBOLSO": {"Código do texto": "RESP_TUT_REEMBOLSO"}},
        textos={"RESP_TUT_REEMBOLSO": "Olá, {nome_fornecedor}!\nSegue o tutorial {nome_arquivo} (protocolo {protocolo}).\n"
                                      "<b>sem html</b>"},
    )
    cfg = usar_caixa_simulada(carregar("calibracao", raiz=projeto))
    assert cfg.erros_xlsx == []
    _email(entrada, "Reembolso", "preciso de reembolso")
    _, [resp] = _rodar(cfg, projeto)
    html = resp["corpo_html"]
    assert "<p>Olá, Ana Souza!</p>" in html
    assert "<p>Segue o tutorial Como abrir um chamado de Reembolso.pptx (protocolo " in html
    assert "&lt;b&gt;sem html&lt;/b&gt;" in html                     # texto escapado
    assert "Anexamos o tutorial" not in html                         # o .j2 da categoria não foi usado
    assert resp["anexos"] == ["Como abrir um chamado de Reembolso.pptx"]


def test_responder_texto_sem_anexo_e_prefixo_no_assunto(projeto, entrada):
    from openpyxl import load_workbook

    arq = preencher_calibracao(
        projeto,
        categorias={"TUT_CADASTRO": {"Ação": "RESPONDER_TEXTO", "Código do texto": "RESP_TUT_CADASTRO"}},
        textos={"RESP_TUT_CADASTRO": "Para atualizar o cadastro, acesse {link_formulario}"},
    )
    wb = load_workbook(arq)
    for linha in wb[E.ABA_TEXTOS].iter_rows(min_row=2):
        if linha[0].value == "RESP_TUT_CADASTRO":
            linha[1].value = "[Cadastro {protocolo}]"
    wb.save(arq)
    cfg = usar_caixa_simulada(carregar("calibracao", raiz=projeto))
    assert cfg.erros_xlsx == []
    _email(entrada, "Cadastro", "preciso atualizar cadastro e dados bancarios")
    resumo, [resp] = _rodar(cfg, projeto)
    r = resumo.resultados[0]
    assert r.acao == Acao.RESPONDER_TEXTO and r.status == Status.SIMULADO
    assert resp["anexos"] == []
    assert resp["assunto"].startswith("[Cadastro ") and resp["assunto"].endswith("RE: Cadastro")
    assert '<a href="https://forms.office.com/r/EXEMPLO-PO">' in resp["corpo_html"]


def test_textos_migrados_do_dev_reproduzem_a_resposta_da_v021(projeto, tmp_path):
    dev = carregar("dev", raiz=projeto)
    via_xlsx = carregar("dev", raiz=projeto, arquivo_xlsx=gerar_modelo(dev, tmp_path / "d.xlsx", modelo="perfil"))
    email = EmailRecebido("<1@x>", FORNECEDOR, "Ana", "Reembolso", "", "", None)
    htmls = []
    for cfg in (dev, via_xlsx):
        robo = montar_dependencias(cfg, caixa=object())
        try:
            htmls.append(robo.respostas.resposta(email, "TUT_REEMBOLSO", nome_arquivo="t.pptx"))
        finally:
            robo.registro.fechar()
    corta = lambda h: h.split("Resposta automática · protocolo")[0]  # noqa: E731 (a data/hora muda)
    assert corta(htmls[0]) == corta(htmls[1])


def test_nota_manual_no_encaminhamento(projeto, entrada):
    preencher_calibracao(projeto, geral={"acao_manual": "ENCAMINHAR"},
                         textos={"NOTA_MANUAL": "Analista: confira o retorno na planilha. Protocolo {protocolo}"})
    cfg = usar_caixa_simulada(carregar("calibracao", raiz=projeto))
    _email(entrada, "Pagamento", "quando vou receber o pagamento?")
    robo = montar_dependencias(cfg)
    try:
        robo.executar_ciclo()
    finally:
        robo.registro.fechar()
    saida = projeto / "dados_teste" / "caixa_simulada" / "saida"
    [enc] = [json.loads(p.read_text(encoding="utf-8")) for p in saida.glob("*_ENCAMINHAMENTO.json")]
    assert "<p>Analista: confira o retorno na planilha. Protocolo " in enc["corpo_html"]


def test_texto_html_escapa_e_quebra_linhas():
    h = texto_html("a <script>\n\nb {analista} https://x.com/a?b=1", {"analista": "Ana"})
    assert str(h) == '<p>a &lt;script&gt;</p><p>b Ana <a href="https://x.com/a?b=1">https://x.com/a?b=1</a></p>'
