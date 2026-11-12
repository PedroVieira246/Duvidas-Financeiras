"""Linha de comando do robô.

    python -m rpa_duvidas executar   [--perfil dev|demo|prod|calibracao] [--loop]
    python -m rpa_duvidas verificar  [--perfil ...]
    python -m rpa_duvidas previa     [--perfil ...] [--detalhe]
    python -m rpa_duvidas reprocessar <PROTOCOLO> [--perfil ...]
    python -m rpa_duvidas exportar   [--perfil ...]
    python -m rpa_duvidas arquivar-pendentes [--perfil ...]     (v0.3.0)
    python -m rpa_duvidas menu       [--perfil ...]             (v0.3.0)

No executável (RPA_DuvidasFinanceiras.exe), o perfil padrão é ``calibracao`` e o
duplo clique, sem argumentos, abre o menu do console.

Códigos de saída: 0 ok · 1 erro de configuração/caixa · 2 houve e-mails em
erro no ciclo · 3 outro ciclo já em andamento.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import __version__
from .caixa import criar_caixa
from .caixa.base import ErroCaixa
from .ciclo import Robo
from .classificacao import criar_classificador
from .config import Config, ErroConfiguracao, carregar, expandir
from .filtros import ErroEscritorios, ListaFornecedores, ler_planilha_escritorios, valores_sem_escritorio
from .registro import ExecucaoEmAndamento, Registro, configurar_log, trava
from .respostas import GeradorRespostas
from .tutoriais import RepositorioTutoriais

log = logging.getLogger("rpa_duvidas")


def montar_dependencias(cfg: Config, caixa=None):
    """Cria todas as peças a partir da configuração (injeção simples)."""
    registro = Registro(cfg.caminho("registro.banco_estado"), cfg.perfil,
                        str(cfg.get("execucao.destino_respostas", "") or ""))
    registro.criterio = (float(cfg.get("registro.criterio_acerto", 0.95)),
                         int(cfg.get("registro.criterio_minimo_avaliados", 20)))
    tutoriais = RepositorioTutoriais(
        cfg.yaml_referenciado("tutoriais.arquivo"), lambda v: cfg.caminho(v, eh_valor=True)
    )
    respostas = GeradorRespostas(
        cfg.caminho("respostas.pasta_modelos"),
        {
            "assinatura": cfg.get("respostas.assinatura", ""),
            "faixa_ambiente": cfg.get("respostas.faixa_ambiente", ""),
            "link_forms": cfg.get("respostas.link_forms_po", ""),
            "analista": cfg.get("respostas.contexto.analista", ""),
        },
        pastas_personalizadas=_pastas_modelos_personalizados(cfg),
        textos=cfg.get("respostas.textos", {}) or {},
    )
    fornecedores = ListaFornecedores(cfg.yaml_referenciado("filtros.arquivo_fornecedores"))
    robo = Robo(
        cfg=cfg,
        caixa=caixa or criar_caixa(cfg),
        classificador=criar_classificador(cfg),
        registro=registro,
        tutoriais=tutoriais,
        respostas=respostas,
        fornecedores=fornecedores,
        fonte_escritorios=fonte_escritorios(cfg),
    )
    return robo


def fonte_escritorios(cfg: Config):
    """v0.3.0 – leitor da planilha de escritórios (None quando ``escritorios.arquivo`` está vazio)."""
    if not cfg.get("escritorios.arquivo"):
        return None
    return lambda: ler_planilha_escritorios(
        cfg.caminho("escritorios.arquivo"), str(cfg.get("escritorios.aba", "") or ""),
        str(cfg.get("escritorios.coluna_dominio", "Domínio")), str(cfg.get("escritorios.coluna_escritorio", "Escritório")),
        valores_sem_escritorio=valores_sem_escritorio(cfg),
    )


def _pastas_modelos_personalizados(cfg: Config):
    """``modelos\\`` ao lado do .exe: um .j2 ali substitui o padrão (seção 4.4)."""
    nome = cfg.get("respostas.pasta_modelos_personalizados", "")
    if not nome:
        return []
    p = Path(expandir(str(nome)))
    return [p if p.is_absolute() else cfg.raiz / p]


def _preparar(perfil: Optional[str], validar: bool = True) -> Config:
    cfg = carregar(perfil)
    configurar_log(cfg.caminho("registro.pasta_logs"), cfg.get("registro.nivel_log", "INFO"))
    log.info("RPA Dúvidas Financeiras v%s | perfil %s | ambiente %s", __version__, cfg.perfil, cfg.ambiente)
    if validar:
        erros = cfg.validar()
        if erros:
            raise ErroConfiguracao("Configuração inválida:\n  - " + "\n  - ".join(erros))
    return cfg


# --------------------------------------------------------------------------- #
def cmd_executar(args) -> int:
    cfg = _preparar(args.perfil)
    if not cfg.envio_real:
        log.info("MODO SIMULAÇÃO: nenhuma mensagem será enviada, só rascunhos (execucao.envio_real=false)")
    caminho_trava = cfg.caminho("registro.banco_estado").with_suffix(".lock")
    intervalo = int(cfg.get("execucao.intervalo_minutos", 15))
    codigo = 0
    while True:
        try:
            with trava(caminho_trava):
                robo = montar_dependencias(cfg)
                try:
                    resumo = robo.executar_ciclo()
                    if robo.registro.exportar_planilha(cfg.caminho("registro.planilha_controle")):
                        log.info("Planilha de controle atualizada: %s", cfg.caminho("registro.planilha_controle"))
                    codigo = 1 if resumo.falha else 2 if resumo.contagem()["erros"] else 0
                finally:
                    robo.registro.fechar()
                    robo.caixa.fechar()
        except ExecucaoEmAndamento as e:
            log.warning(str(e))
            codigo = 3
        if not args.loop:
            return codigo
        log.info("Próximo ciclo em %d min (Ctrl+C para parar)", intervalo)
        time.sleep(intervalo * 60)


def cmd_verificar(args) -> int:
    from . import verificacao as V

    cfg = _preparar(args.perfil, validar=False)
    linhas: List[str] = []

    def p(texto: str = "") -> None:
        print(texto)
        linhas.append(texto)

    problemas: List[str] = [e for e in cfg.validar() if not cfg.erros_xlsx or e not in {str(x) for x in cfg.erros_xlsx}]
    p(f"\nRPA Dúvidas Financeiras v{__version__} | {datetime.now():%d/%m/%Y %H:%M}")
    p(f"Perfil: {cfg.perfil} | ambiente: {cfg.ambiente} | caixa: {cfg.get('caixa.tipo')} | "
      f"envio real: {'SIM' if cfg.envio_real else 'não (simulação)'}")

    def secao(titulo: str, itens) -> None:
        if not itens:
            return
        p(f"\n[{titulo}]")
        for item in itens:
            p(str(item))
            if item.nivel == V.ERRO:
                problemas.append(item.mensagem)

    secao("Planilha de configuração", V.planilha_configuracao(cfg))
    secao("Outlook e destino das respostas", V.outlook(cfg))

    if cfg.usa_xlsx:
        secao("Tutoriais", V.tutoriais(cfg))
        secao("Formulário de PO", V.formulario(cfg))
    else:
        p("\n[Tutoriais]")
        try:
            repo = RepositorioTutoriais(cfg.yaml_referenciado("tutoriais.arquivo"), lambda v: cfg.caminho(v, eh_valor=True))
            for cat, ok, det in repo.verificar_todos():
                p(f"  {'OK ' if ok else 'ERRO'} {cat:<14} {det}")
                if not ok:
                    problemas.append(f"Tutorial {cat}: {det}")
        except ErroConfiguracao as e:
            problemas.append(str(e))

    p("\n[Modelos de resposta]")
    pasta = cfg.caminho("respostas.pasta_modelos")
    for nome in ["TUT_CONNECT", "TUT_UPLOAD_NF", "TUT_REEMBOLSO", "TUT_CADASTRO", "FORMS_PO",
                 "encaminhamento_manual", "aviso_erro"]:
        ok = (pasta / f"{nome}.html.j2").exists()
        p(f"  {'OK ' if ok else 'ERRO'} {nome}")
        if not ok:
            problemas.append(f"Modelo ausente: {nome}.html.j2")

    p("\n[Classificação]")
    tipo = cfg.classificador
    p(f"  tipo: {tipo} | limite de confiança efetivo: {cfg.limite_confianca:.2f}")
    if cfg.usa_xlsx:
        p("  IA: desligada nesta etapa")                    # D04: nada da IA é consultado no perfil calibracao
    else:
        from .classificacao.ia import verificar_ia

        try:
            tutoriais_cfg = list((cfg.yaml_referenciado("tutoriais.arquivo").get("categorias") or {}).keys())
        except ErroConfiguracao:
            tutoriais_cfg = []
        modelos = [m.name[: -len(".html.j2")] for m in pasta.glob("*.html.j2")]
        problemas_ia = verificar_ia(cfg, modelos, tutoriais_cfg)
        if tipo == "ia":
            p(f"  provedor: {cfg.get('classificacao.ia.provedor.tipo', 'simulado')} | prompt: "
              f"{cfg.get('classificacao.ia.arquivo_prompt')} | categorias: {cfg.get('classificacao.ia.arquivo_categorias')}")
            if not (pasta / "aviso_ia_indisponivel.html.j2").exists():
                problemas_ia.append("Modelo ausente: aviso_ia_indisponivel.html.j2")
            for prob in problemas_ia:
                p(f"  ERRO {prob}")
            if not problemas_ia:
                p("  OK  prompt, categorias_ia.yaml, mapeamento categoria → tutorial e provedor")
            problemas += problemas_ia
        else:
            situacao = "OK " if not problemas_ia else "AVISO"
            p(f"  {situacao} configuração da IA (desligada; só informativo){': ' + '; '.join(problemas_ia) if problemas_ia else ''}")
    secao("Categorias", V.categorias(cfg))

    p("\n[Filtros]")
    try:
        n_forn = len(ListaFornecedores(cfg.yaml_referenciado("filtros.arquivo_fornecedores")))
    except ErroConfiguracao:
        n_forn = 0
    if cfg.get("escritorios.arquivo"):
        p(f"  domínios internos: {len(cfg.get('filtros.dominios_internos', []) or [])} | "
          f"não fornecedores: {'marcados' if cfg.get('caixa.marcar_nao_fornecedores', True) else 'não alterados'} | "
          f"pular já respondidos: {'sim' if cfg.get('caixa.pular_ja_respondidos', False) else 'não'}")
    else:
        p(f"  fornecedores na lista: {n_forn} | domínios internos: {len(cfg.get('filtros.dominios_internos', []) or [])} | "
          f"spam (SCL): {'ligado' if cfg.get('filtros.spam.ativo', False) else 'desligado'}")
    if cfg.ambiente == "prod" and cfg.get("filtros.validar_fornecedor", True) and n_forn == 0:
        alerta = ("ALERTA: lista de fornecedores VAZIA em prod – todos os e-mails irão para "
                  "[MANUAL – FORA DA LISTA] (solicitação S06 / lacuna R8)")
        p(f"  {alerta}")
        problemas.append(alerta)
    secao("Planilha de escritórios", V.escritorios(cfg))
    secao("Arquivamento .msg", V.arquivamento(cfg))

    p("\n[Caixa de e-mail]")
    try:
        caixa = criar_caixa(cfg)
        for aviso in getattr(caixa, "avisos", lambda: [])():
            p(f"  INFO {aviso}")
        for item in V.tipo_conta(cfg, caixa):
            p(str(item))
        extras = caixa.verificar()
        p("  OK  conexão" + (f" | conta: {cfg.get('caixa.conta')}" if cfg.get("caixa.conta") else "")
          if not extras else "  ERRO " + "; ".join(extras))
        problemas += extras
    except (ErroCaixa, ErroConfiguracao) as e:
        p(f"  ERRO {e}")
        problemas.append(str(e))

    if cfg.erros_xlsx:
        problemas = [str(e) for e in cfg.erros_xlsx] + problemas
    problemas = list(dict.fromkeys(problemas))
    p("\n" + ("Tudo certo para executar." if not problemas else "Pendências:\n  - " + "\n  - ".join(problemas)))
    _salvar_evidencia(cfg, linhas)
    return 0 if not problemas else 1


def _salvar_evidencia(cfg: Config, linhas: List[str]) -> None:
    """Saída do verificar em logs\\verificar_AAAA-MM-DD_HHMM.txt – evidência da instalação (seção 7.2)."""
    try:
        pasta = cfg.caminho("registro.pasta_logs")
        pasta.mkdir(parents=True, exist_ok=True)
        arq = pasta / f"verificar_{datetime.now():%Y-%m-%d_%H%M}.txt"
        arq.write_text("\n".join(linhas) + "\n", encoding="utf-8")
        print(f"\nResultado salvo em {arq}")
    except OSError as e:
        log.warning("Não foi possível salvar o resultado do verificar: %s", e)


def cmd_previa(args) -> int:
    """Lê e classifica os pendentes SEM responder, encaminhar nem mover nada."""
    from . import extracao
    from .filtros import FiltroInterno, FiltroSpam

    cfg = _preparar(args.perfil)
    robo = montar_dependencias(cfg)
    interno: FiltroInterno = robo.filtro_interno
    spam: FiltroSpam = robo.filtro_spam
    try:
        robo.atualizar_escritorios()
        emails = robo.ler_pendentes(int(cfg.get("caixa.lote_maximo", 50)))
        print(f"\n{len(emails)} e-mail(s) na pasta de entrada (nenhuma ação será executada)\n")
        if not robo.marcar_nao_fornecedores:
            print(f"{getattr(robo.caixa, 'descartados', 0)} e-mail(s) de não fornecedores ignorados sem alteração\n")
        from .modelos import VERBOS_JA_TRATADO
        for e in emails:
            extracao.processar(e, cfg.get("extracao", {}) or {}, cfg.get("filtros.assuntos_resposta_automatica", []),
                               cfg.get("filtros.mensagens_do_rpa", {}) or {})
            eh_interno, det_interno = interno.interno(e.remetente)
            eh_spam, det_spam = spam.spam(e.cabecalhos)
            if robo.pular_ja_respondidos and e.ultimo_verbo in VERBOS_JA_TRATADO:
                destino = "IGNORAR – JÁ TRATADO PELO ANALISTA"
            elif e.resposta_automatica:
                destino = f"IGNORAR ({e.motivo_resposta_automatica})"
            elif e.gerada_pelo_rpa:
                destino = f"IGNORAR – PRÓPRIO RPA ({e.motivo_gerada_pelo_rpa})"
            elif eh_interno:
                destino = f"IGNORAR – INTERNO ({det_interno})"
            elif eh_spam:
                destino = f"IGNORAR – SPAM ({det_spam})"
            elif cfg.get("filtros.validar_fornecedor", True) and not robo.fornecedores.conhecido(e.remetente):
                destino = "MANUAL – FORA DA LISTA"
            else:
                c = robo.classificador.classificar(e.assunto, e.corpo_limpo, email=e)
                baixa = c.categoria != "MANUAL" and c.confianca < cfg.limite_confianca
                destino = f"{'MANUAL (baixa confiança) ← ' if baixa else ''}{c.categoria} {c.confianca:.2f}"
                if c.motivo_manual:
                    destino += f" [{c.motivo_manual}]"
                if c.detalhes.get("classificador") == "ia":
                    destino += f" · IA {c.detalhes.get('categoria_docx') or '-'} · regra {c.detalhes.get('regra_decisao')}"
            print(f"- {e.remetente or '-'} | {e.assunto[:50]}\n    → {destino}")
            if args.detalhe:
                print("    texto usado: " + e.corpo_limpo[:300].replace("\n", " / "))
    finally:
        robo.registro.fechar()
    return 0


def cmd_reprocessar(args) -> int:
    cfg = _preparar(args.perfil, validar=False)
    reg = Registro(cfg.caminho("registro.banco_estado"), cfg.perfil)
    n = reg.esquecer(args.protocolo)
    reg.fechar()
    if n:
        print(f"Protocolo {args.protocolo.upper()} liberado. Mova o e-mail de volta para a pasta de entrada.")
        return 0
    print("Nada liberado: protocolo inexistente ou já CONCLUIDO (envio real nunca é repetido).")
    return 1


def cmd_arquivar_pendentes(args) -> int:
    """v0.3.0 – refaz o arquivamento .msg dos e-mails cuja coluna "Arquivado em" ficou com FALHA."""
    cfg = _preparar(args.perfil)
    if not cfg.get("arquivamento.raiz"):
        print("Arquivamento desligado (arquivamento.raiz / caminho_arquivo_emails vazio).")
        return 1
    robo = montar_dependencias(cfg)
    falhas = 0
    try:
        pendentes = robo.registro.pendentes_arquivamento()
        print(f"{len(pendentes)} e-mail(s) com arquivamento pendente")
        for ev in pendentes:
            email = robo.caixa.localizar(ev["id_mensagem"])
            if email is None:
                print(f"- {ev['protocolo']}: e-mail não encontrado na caixa – continua pendente")
                falhas += 1
                continue
            email.escritorio = ev["escritorio"] or email.escritorio
            resultado = robo.arquivador.arquivar(robo.caixa, email)
            robo.registro.atualizar_arquivamento(ev["id"], resultado)
            ok = not resultado.startswith("FALHA")
            falhas += 0 if ok else 1
            print(f"- {ev['protocolo']}: {resultado}")
        if pendentes and robo.registro.exportar_planilha(cfg.caminho("registro.planilha_controle")):
            print(f"Planilha de controle atualizada: {cfg.caminho('registro.planilha_controle')}")
    finally:
        robo.registro.fechar()
        robo.caixa.fechar()
    return 0 if not falhas else 2


def cmd_exportar(args) -> int:
    cfg = _preparar(args.perfil, validar=False)
    reg = Registro(cfg.caminho("registro.banco_estado"), cfg.perfil)
    ok = reg.exportar_planilha(cfg.caminho("registro.planilha_controle"))
    reg.fechar()
    print(cfg.caminho("registro.planilha_controle") if ok else "Planilha em uso – feche o Excel e tente de novo.")
    return 0 if ok else 1


MENU = """
RPA Dúvidas Financeiras v{versao} – {conta}
1) Verificar configuração
2) Prévia (não altera nada)
3) Executar um ciclo
4) Executar continuamente (a cada {intervalo} min)
5) Abrir planilha de controle
0) Sair
"""


def _abrir_arquivo(caminho: Path) -> None:
    abrir = getattr(os, "startfile", None)
    if abrir is None:
        print(f"Planilha de controle: {caminho}")
        return
    abrir(str(caminho))  # pragma: no cover - só no Windows


def cmd_menu(args, entrada=input) -> int:
    """Menu do console aberto pelo duplo clique no .exe (seção 7.2)."""
    perfil = getattr(args, "perfil", None)
    while True:
        conta, intervalo, planilha = "", 15, None
        try:
            cfg = carregar(perfil)
            conta = str(cfg.get("caixa.conta", "") or "conta padrão do Outlook")
            intervalo = int(cfg.get("execucao.intervalo_minutos", 15) or 15)
            planilha = cfg.caminho("registro.planilha_controle")
        except ErroConfiguracao as e:
            conta = f"configuração com erro – {e}"
        print(MENU.format(versao=__version__, conta=conta, intervalo=intervalo))
        try:
            opcao = entrada("Escolha uma opção: ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        ns = argparse.Namespace(perfil=perfil, loop=False, detalhe=False)
        try:
            if opcao == "0":
                return 0
            if opcao == "1":
                cmd_verificar(ns)
            elif opcao == "2":
                cmd_previa(ns)
            elif opcao == "3":
                cmd_executar(ns)
            elif opcao == "4":
                ns.loop = True
                cmd_executar(ns)
            elif opcao == "5":
                if planilha is not None and planilha.exists():
                    _abrir_arquivo(planilha)
                else:
                    print(f"Planilha de controle ainda não existe: {planilha} (rode um ciclo primeiro)")
            else:
                print("Opção inválida.")
                continue
        except (ErroConfiguracao, ErroCaixa, ErroEscritorios) as erro:
            print(f"\nERRO: {erro}")
        except KeyboardInterrupt:
            print("\nInterrompido.")
        try:
            entrada("\nPressione Enter para voltar ao menu...")
        except (EOFError, KeyboardInterrupt):
            return 0


def main(argv: Optional[List[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv and getattr(sys, "frozen", False):        # duplo clique no .exe
        try:
            return cmd_menu(argparse.Namespace(perfil=None))
        except Exception as erro:  # pragma: no cover - não fechar o console sem mostrar o erro
            print(f"\nERRO: {erro}")
            input("\nPressione Enter para sair...")
            return 1
    p = argparse.ArgumentParser(prog="rpa_duvidas", description="RPA Dúvidas Financeiras – Frente 1")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="comando")

    def com_perfil(sp):
        sp.add_argument("--perfil", help="dev | demo | prod | calibracao (padrão: variável RPA_PERFIL; "
                                         "calibracao no executável, dev no código-fonte)")
        return sp

    e = com_perfil(sub.add_parser("executar", help="executa um ciclo (ou vários com --loop)"))
    e.add_argument("--loop", action="store_true", help="repete a cada execucao.intervalo_minutos")
    e.set_defaults(func=cmd_executar)
    com_perfil(sub.add_parser("verificar", help="checa configuração, tutoriais, modelos e caixa")).set_defaults(func=cmd_verificar)
    pv = com_perfil(sub.add_parser("previa", help="mostra como cada pendente seria tratado, sem agir"))
    pv.add_argument("--detalhe", action="store_true", help="mostra o texto limpo usado na classificação")
    pv.set_defaults(func=cmd_previa)
    r = com_perfil(sub.add_parser("reprocessar", help="libera um e-mail SIMULADO/ERRO para novo tratamento"))
    r.add_argument("protocolo")
    r.set_defaults(func=cmd_reprocessar)
    com_perfil(sub.add_parser("exportar", help="regera a planilha de controle")).set_defaults(func=cmd_exportar)
    com_perfil(sub.add_parser("arquivar-pendentes", help="refaz o arquivamento .msg que falhou")).set_defaults(
        func=cmd_arquivar_pendentes)
    com_perfil(sub.add_parser("menu", help="menu do console (o mesmo do duplo clique no .exe)")).set_defaults(
        func=cmd_menu)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 1
    try:
        return args.func(args)
    except (ErroConfiguracao, ErroCaixa, ErroEscritorios) as erro:
        logging.getLogger("rpa_duvidas").error(str(erro))
        print(f"\nERRO: {erro}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
