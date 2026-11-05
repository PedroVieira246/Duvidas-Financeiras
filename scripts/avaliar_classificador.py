"""Mede o classificador contra uma massa de e-mails (base do F07).

    python scripts/avaliar_classificador.py
    python scripts/avaliar_classificador.py --massa tests/dados/massa_emails.csv --perfil dev
    python scripts/avaliar_classificador.py --classificador ia --limites 0.70,0.75,0.80,0.85,0.90

``--classificador`` escolhe a abordagem (padrão: a do perfil). ``--limites``
repete a decisão para cada limite de confiança, sem chamar a IA de novo
(a IA é consultada uma vez por e-mail e só as regras D1–D7 são reaplicadas),
e gera a tabela de calibração da seção 6.2: o limite escolhido é o MENOR que
mantém zero erros graves.

Massa: CSV com colunas id, assunto, corpo, categoria_esperada (seção 4 da
especificação). Indicadores:
  * acerto geral e por categoria;
  * % que vai para análise manual;
  * ERROS GRAVES: resposta automática errada enviada ao fornecedor
    (previsto TUT_*/FORMS_PO diferente do esperado) – o que mais pesa.

Gera relatorios/avaliacao_<data>.md e .csv.

ATENÇÃO: com a massa SINTÉTICA, o resultado só prova que a mecânica funciona.
Os termos foram escritos junto com a massa; o número que vale é o da massa
real enviada pela área.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from typing import Callable, Dict, List, Optional, Sequence, Tuple  # noqa: E402

from rpa_duvidas.classificacao import criar_classificador  # noqa: E402
from rpa_duvidas.config import Config, carregar  # noqa: E402
from rpa_duvidas.modelos import Categoria, Classificacao  # noqa: E402


def preparar(perfil: str, classificador: Optional[str] = None) -> Config:
    cfg = carregar(perfil)
    if classificador:
        cfg.dados.setdefault("classificacao", {})["tipo"] = classificador
    return cfg


def _decisor_para(cfg: Config, clf) -> Callable[[str, str], Callable[[float], Classificacao]]:
    """Devolve f(assunto, corpo) → g(limite) → Classificacao final (com o limite aplicado).

    * palavras-chave: classifica uma vez e aplica o limite como o ciclo faz;
    * IA: consulta a IA UMA vez e reaplica D1–D7 para cada limite.
    """
    if cfg.classificador == "ia":
        from rpa_duvidas.classificacao.decisao_ia import decidir

        def f(assunto: str, corpo: str):
            consulta = clf.consultar(assunto, corpo)

            def g(limite: float) -> Classificacao:
                return clf.montar_classificacao(consulta, decidir(consulta.resposta, clf.categorias, limite, consulta.falha))
            return g
        return f

    def f(assunto: str, corpo: str):
        c = clf.classificar(assunto, corpo)

        def g(limite: float) -> Classificacao:
            if c.categoria != Categoria.MANUAL and c.confianca < limite:
                return Classificacao(Categoria.MANUAL, c.confianca, c.motivo, "BAIXA_CONFIANCA",
                                     {**c.detalhes, "categoria_sugerida": c.detalhes.get("categoria_sugerida", c.categoria)})
            return c
        return g
    return f


def _linha(row: Dict[str, str], c: Classificacao, limite: float) -> Dict[str, str]:
    final = c.categoria
    esperado = row["categoria_esperada"].strip()
    grave = final in Categoria.RESPONDIVEIS and final != esperado
    return {
        "id": row["id"], "assunto": row["assunto"], "limite": f"{limite:.2f}", "esperada": esperado,
        "prevista": final, "sugerida": str(c.detalhes.get("categoria_sugerida", c.categoria)),
        "confianca": f"{c.confianca:.2f}", "acerto": "sim" if final == esperado else "não",
        "erro_grave": "SIM" if grave else "", "motivo_manual": c.motivo_manual or "",
        "regra": str(c.detalhes.get("regra_decisao", "")), "motivo": c.motivo,
    }


def avaliar_limites(massa: Path, cfg: Config, limites: Sequence[float]) -> Dict[float, List[Dict[str, str]]]:
    clf = criar_classificador(cfg)
    decisor = _decisor_para(cfg, clf)
    por_limite: Dict[float, List[Dict[str, str]]] = {lim: [] for lim in limites}
    with massa.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            g = decisor(row["assunto"], row["corpo"])
            for lim in limites:
                por_limite[lim].append(_linha(row, g(lim), lim))
    return por_limite


def avaliar(massa: Path, perfil: str, classificador: Optional[str] = None) -> Tuple[List[Dict[str, str]], float]:
    """Compatível com a v0.1.0: avalia só no limite da configuração."""
    cfg = preparar(perfil, classificador)
    limite = cfg.limite_confianca
    return avaliar_limites(massa, cfg, [limite])[limite], limite


def indicadores(linhas: List[Dict[str, str]]) -> Dict[str, float]:
    total = len(linhas)
    acertos = sum(1 for l in linhas if l["acerto"] == "sim")
    manuais = sum(1 for l in linhas if l["prevista"] == Categoria.MANUAL)
    graves = sum(1 for l in linhas if l["erro_grave"])
    return {"total": total, "acertos": acertos, "acerto": acertos / total if total else 0.0,
            "manuais": manuais, "pct_manual": manuais / total if total else 0.0, "graves": graves}


def tabela_calibracao(por_limite: Dict[float, List[Dict[str, str]]]) -> str:
    out = ["## Calibração do limite de confiança (seção 6.2)", "",
           "| Limite | Acerto | % manual | Erros graves |", "|---|---|---|---|"]
    sem_grave = []
    for lim in sorted(por_limite):
        ind = indicadores(por_limite[lim])
        out.append(f"| {lim:.2f} | {ind['acertos']}/{ind['total']} ({ind['acerto']:.0%}) | "
                   f"{ind['manuais']}/{ind['total']} ({ind['pct_manual']:.0%}) | {ind['graves']} |")
        if ind["graves"] == 0:
            sem_grave.append(lim)
    out.append("")
    out.append(f"**Menor limite com zero erros graves: {min(sem_grave):.2f}**" if sem_grave
               else "**Nenhum limite testado ficou sem erro grave.**")
    return "\n".join(out) + "\n"


def relatorio(linhas, limite, massa: Path) -> str:
    total = len(linhas)
    acertos = sum(1 for l in linhas if l["acerto"] == "sim")
    manuais = sum(1 for l in linhas if l["prevista"] == Categoria.MANUAL)
    graves = [l for l in linhas if l["erro_grave"]]
    por_cat = defaultdict(lambda: [0, 0])
    for l in linhas:
        por_cat[l["esperada"]][1] += 1
        por_cat[l["esperada"]][0] += l["acerto"] == "sim"
    confusao = Counter((l["esperada"], l["prevista"]) for l in linhas if l["acerto"] != "sim")

    out = [
        f"# Avaliação do classificador – {datetime.now():%d/%m/%Y %H:%M}",
        "",
        f"- Massa: `{massa.name}` ({total} e-mails) · limite de confiança: {limite:.2f}",
        f"- **Acerto geral: {acertos}/{total} ({acertos / total:.0%})**" if total else "- Massa vazia",
        f"- Para análise manual: {manuais}/{total} ({manuais / total:.0%})" if total else "",
        f"- **Erros graves (tutorial/link errado ao fornecedor): {len(graves)}**",
        "",
        "## Acerto por categoria esperada",
        "",
        "| Categoria | Acertos | Total | % |",
        "|---|---|---|---|",
    ]
    for cat in sorted(por_cat):
        a, t = por_cat[cat]
        out.append(f"| {cat} | {a} | {t} | {a / t:.0%} |")
    if confusao:
        out += ["", "## Erros (esperada → prevista)", "", "| Esperada | Prevista | Qtde |", "|---|---|---|"]
        out += [f"| {e} | {p} | {n} |" for (e, p), n in confusao.most_common()]
    if graves:
        out += ["", "## Erros graves", ""]
        out += [f"- {g['id']} · \"{g['assunto']}\" · esperado {g['esperada']}, previsto {g['prevista']} · {g['motivo']}" for g in graves]
    if "sintetica" in massa.name:
        out += ["", "> Massa SINTÉTICA: valida a mecânica, não o desempenho real. Repetir com a massa da área."]
    return "\n".join(out) + "\n"


def _limites(texto: str) -> List[float]:
    valores = sorted({round(float(x.strip().replace(",", ".")), 4) for x in (texto or "").split(";" if ";" in texto else ",") if x.strip()})
    if any(not 0 <= v <= 1 for v in valores):
        raise argparse.ArgumentTypeError("limites devem estar entre 0 e 1")
    return valores


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--massa", default=str(RAIZ / "tests" / "dados" / "massa_emails_sintetica.csv"))
    ap.add_argument("--perfil", default="demo")
    ap.add_argument("--classificador", choices=["palavras_chave", "ia"], help="padrão: classificacao.tipo do perfil")
    ap.add_argument("--limites", type=_limites, help="ex.: 0.70,0.75,0.80,0.85,0.90 (padrão: o limite do perfil)")
    ap.add_argument("--saida", default=str(RAIZ / "relatorios"))
    args = ap.parse_args(argv)

    massa = Path(args.massa)
    cfg = preparar(args.perfil, args.classificador)
    limites = args.limites or [cfg.limite_confianca]
    por_limite = avaliar_limites(massa, cfg, limites)
    limite_cfg = cfg.limite_confianca
    principal = limite_cfg if limite_cfg in por_limite else limites[len(limites) // 2]
    linhas = por_limite[principal]
    texto = f"Classificador: **{cfg.classificador}**\n\n" + relatorio(linhas, principal, massa)
    if len(limites) > 1:
        texto += "\n" + tabela_calibracao(por_limite)
        linhas = [l for lim in limites for l in por_limite[lim]]
    print(texto)

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    carimbo = f"{datetime.now():%Y%m%d-%H%M%S}"
    (saida / f"avaliacao_{carimbo}.md").write_text(texto, encoding="utf-8")
    with (saida / f"avaliacao_{carimbo}.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()) if linhas else ["id"], delimiter=";")
        w.writeheader()
        w.writerows(linhas)
    print(f"Relatório salvo em {saida / f'avaliacao_{carimbo}.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
