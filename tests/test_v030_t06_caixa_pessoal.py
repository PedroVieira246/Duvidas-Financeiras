"""v0.3.0 – T06: leitura da caixa pessoal (marcar_nao_fornecedores e pular_ja_respondidos – seção 6.1).

COM do Outlook sempre simulado (objetos falsos de test_outlook_com)."""
import json
from datetime import datetime

from conftest import DESTINO_CAL
from rpa_duvidas.__main__ import montar_dependencias
from rpa_duvidas.caixa.outlook_com import PR_INTERNET_MESSAGE_ID, PR_LAST_VERB_EXECUTED, CaixaOutlookCOM
from rpa_duvidas.modelos import Acao, MotivoIgnorado, Status

from test_outlook_com import DESTINOS, Mensagem, Namespace, ns  # noqa: F401 (fixture)

CATS = ["RPA - Respondido", "RPA - Encaminhado", "RPA - Erro", "RPA - Ignorado", "RPA - Simulado"]


def _caixa(ns):
    return CaixaOutlookCOM("", "@inbox", DESTINOS, criar_pastas=True, mover_apos_tratar=False, categorias_rpa=CATS,
                           max_varredura=300, namespace=ns, aplicativo=None)


def _msg(pasta, n, de, verbo=None):
    props = {PR_INTERNET_MESSAGE_ID: f"<{n}@x>"}
    if verbo is not None:
        props[PR_LAST_VERB_EXECUTED] = verbo
    return Mensagem(pasta, assunto=f"Assunto {n}", de=de, data=datetime(2026, 11, 3, 8, n), props=props)


def test_filtro_de_remetente_roda_antes_do_lote(ns):
    """Pergunta 2 da Etapa 1: não fornecedores não ocupam o lote nem são convertidos."""
    cx = _caixa(ns)
    pessoais = [_msg(ns.inbox, n, f"colega{n}@empresa-exemplo.com.br") for n in range(1, 6)]
    fornecedor = _msg(ns.inbox, 9, "ana@fornecedor-exemplo.com.br")
    ns.inbox.Items._itens += pessoais + [fornecedor]
    vistos = []

    def aceitar(rem):
        vistos.append(rem)
        return rem.endswith("@fornecedor-exemplo.com.br")

    lidos = cx.ler_pendentes(2, aceitar_remetente=aceitar)
    assert [e.remetente for e in lidos] == ["ana@fornecedor-exemplo.com.br"]
    assert cx.descartados == 5 and len(vistos) == 6
    assert all(m.UnRead and m.Categories == "" and not m.salvo for m in pessoais)


def test_ultimo_verbo_e_finalizar_sem_marcar_lido(ns):
    cx = _caixa(ns)
    m = _msg(ns.inbox, 1, "ana@fornecedor-exemplo.com.br", verbo=102)
    ns.inbox.Items._itens.append(m)
    [e] = cx.ler_pendentes(10)
    assert e.ultimo_verbo == 102
    cx.finalizar(e, "ignorados", "RPA - Ignorado", marcar_lido=False)
    assert m.UnRead is True and m.Categories == "RPA - Ignorado"


def _json(entrada, n, remetente, assunto="Reembolso", corpo="preciso de reembolso", **extra):
    dados = {"id_mensagem": f"<cal-{n}@x>", "remetente": remetente, "nome_remetente": "X", "assunto": assunto,
             "corpo_texto": corpo, "data_recebimento": f"2026-11-03T09:{n:02d}:00", **extra}
    arq = entrada / f"{n:03d}.json"
    arq.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return arq


def test_ciclo_na_caixa_pessoal_nao_altera_e_nao_registra_terceiros(projeto_cal, cfg_cal, entrada):
    interno = _json(entrada, 1, "colega@empresa-exemplo.com.br", "Almoço", "vamos almoçar?")
    externo = _json(entrada, 2, "loja@desconhecido.com.br", "Promoção", "compre já")
    resposta_teste = _json(entrada, 3, DESTINO_CAL, "RE: Reembolso", "Resposta automática · protocolo ABCDEF12")
    ja_respondido = _json(entrada, 4, "ana@fornecedor-exemplo.com.br", ultimo_verbo=102)
    antes = {p: p.read_bytes() for p in (interno, externo, resposta_teste)}

    robo = montar_dependencias(cfg_cal)
    try:
        resumo = robo.executar_ciclo()
        assert resumo.nao_fornecedores == 3
        assert [r.email.remetente for r in resumo.resultados] == ["ana@fornecedor-exemplo.com.br"]
        [r] = resumo.resultados
        assert (r.acao, r.status) == (Acao.IGNORAR, Status.IGNORADO)
        assert r.motivo_ignorado.startswith(MotivoIgnorado.JA_TRATADO_PELO_ANALISTA)
        # critério 4: e-mails de fora da planilha de escritórios não mudam em nada
        assert {p: p.read_bytes() for p in antes} == antes
        assert {e["remetente"] for e in robo.registro.eventos()} == {"ana@fornecedor-exemplo.com.br"}
        ciclo = robo.registro.con.execute("SELECT nao_fornecedores FROM ciclos").fetchone()
        assert ciclo[0] == 3
    finally:
        robo.registro.fechar()
    # critério 5: o já respondido só recebe a categoria (sem resposta, sem marcar como lido)
    dados = json.loads(ja_respondido.read_text(encoding="utf-8"))
    assert dados["categorias_outlook"] == ["RPA - Ignorado"] and "lido" not in dados
    saida = projeto_cal / "dados_teste" / "caixa_simulada" / "saida"
    assert not list(saida.glob("*_RESPOSTA.json"))


def test_com_marcar_nao_fornecedores_s_o_comportamento_e_o_da_v021(projeto_cal, cfg_cal, entrada):
    cfg_cal.dados["caixa"]["marcar_nao_fornecedores"] = True
    _json(entrada, 1, "colega@empresa-exemplo.com.br", "Almoço", "vamos almoçar?")
    robo = montar_dependencias(cfg_cal)
    try:
        resumo = robo.executar_ciclo()
    finally:
        robo.registro.fechar()
    [r] = resumo.resultados
    assert r.status == Status.IGNORADO and r.motivo_ignorado.startswith(MotivoIgnorado.INTERNO)
    assert resumo.nao_fornecedores == 0
