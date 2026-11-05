"""Prepara a demonstração com a caixa SIMULADA (perfil demo).

    python scripts/preparar_demo.py            # 12 cenários escolhidos
    python scripts/preparar_demo.py --todos    # + os 40 e-mails da massa sintética
    python scripts/preparar_demo.py --ia       # cenários da classificação por IA (perfil demo_ia)

O que faz:
  1. apaga a caixa simulada e o registro do perfil demo;
  2. garante os tutoriais FICTÍCIOS em dados_teste/tutoriais;
  3. coloca os e-mails de teste em dados_teste/caixa_simulada/entrada.

Depois:  python -m rpa_duvidas executar --perfil demo        (ou --perfil demo_ia com --ia)
Todos os nomes, e-mails e empresas são fictícios.
"""
from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CAIXA = RAIZ / "dados_teste" / "caixa_simulada"
TUTORIAIS = RAIZ / "dados_teste" / "tutoriais"
MASSA = RAIZ / "tests" / "dados" / "massa_emails_sintetica.csv"
REGISTRO_DEMO = RAIZ / "dados" / "demo"
REGISTRO_DEMO_IA = RAIZ / "dados" / "demo_ia"

ARQUIVOS_TUTORIAL = {
    "04. Suporte Connect": ("Tutorial - Acesso ao Connect.pptx", "Acesso ao portal Connect"),
    "Upload de NF": ("PYM (Connect) - Upload e consulta de NFs.pdf", "Upload e consulta de NFs no PYM"),
    "Reembolso": ("Como abrir um chamado de Reembolso.pptx", "Como abrir um chamado de Reembolso"),
    "03. Tutorial de acessos": ("Tutorial - Atualizacao de cadastro.pptx", "Atualização de cadastro"),
}

REMETENTE = ("Maria Souza", "maria.souza@fornecedor-exemplo.com.br")
CURADOS = ["S01", "S06", "S11", "S15", "S19", "S24", "S30", "S32"]

CORPO_HTML_COM_HISTORICO = """<html><body>
<p>Bom dia,</p>
<p>Ainda não consegui fazer o <b>primeiro acesso ao Connect</b>. O link do convite expirou.</p>
<p>Atenciosamente,</p>
<p>João Pereira<br>Analista Financeiro – Fornecedor Exemplo Ltda<br>(11) 99999-0000</p>
<p style="font-size:8pt">AVISO DE CONFIDENCIALIDADE: esta mensagem é destinada exclusivamente ao destinatário.</p>
<div id="divRplyFwdMsg"><b>De:</b> Contas a Pagar<br><b>Enviado:</b> segunda-feira<br><b>Assunto:</b> Cadastro</div>
<div><p>Prezado fornecedor, segue o convite para o portal. Qualquer dúvida sobre pagamento, reembolso ou pedido de compra estamos à disposição.</p></div>
</body></html>"""


def pdf_ficticio(destino: Path, titulo: str) -> None:
    """PDF de 1 página, sem dependências, para simular um tutorial (v0.2.1)."""
    linhas = [
        (18, f"TUTORIAL FICTÍCIO – {titulo}"),
        (14, "Arquivo de demonstração do RPA Dúvidas Financeiras."),
        (14, "Será substituído pelo tutorial oficial publicado no SharePoint."),
    ]

    def esc(t: str) -> str:
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    y, partes = 760, ["BT"]
    for tam, txt in linhas:
        partes.append(f"/F1 {tam} Tf 1 0 0 1 56 {y} Tm ({esc(txt)}) Tj")
        y -= tam + 18
    partes.append("ET")
    conteudo = "\n".join(partes).encode("cp1252")
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(conteudo)).encode() + b" >>\nstream\n" + conteudo + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    saida, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, start=1):
        offsets.append(len(saida))
        saida += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref = len(saida)
    saida += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        saida += f"{off:010d} 00000 n \n".encode()
    saida += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    destino.write_bytes(bytes(saida))


def gerar_tutoriais() -> None:
    try:
        from pptx import Presentation
        from pptx.util import Pt
    except ImportError:
        Presentation = None
    for pasta, (nome, titulo) in ARQUIVOS_TUTORIAL.items():
        destino = TUTORIAIS / pasta / nome
        if destino.exists():
            continue
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.suffix.lower() == ".pdf":
            pdf_ficticio(destino, titulo)
            print(f"  tutorial fictício criado: {destino.relative_to(RAIZ)}")
            continue
        if Presentation is None:
            raise SystemExit("Tutoriais fictícios ausentes e python-pptx não instalado: pip install python-pptx")
        prs = Presentation()
        s = prs.slides.add_slide(prs.slide_layouts[0])
        s.shapes.title.text = f"TUTORIAL FICTÍCIO – {titulo}"
        s.placeholders[1].text = "Arquivo de demonstração do RPA Dúvidas Financeiras.\nSubstituído pelo tutorial oficial do SharePoint."
        s.placeholders[1].text_frame.paragraphs[0].runs[0].font.size = Pt(18)
        prs.save(destino)
        print(f"  tutorial fictício criado: {destino.relative_to(RAIZ)}")


def email_json(ident, assunto, corpo_texto="", corpo_html="", remetente=REMETENTE, minutos=0, **extra) -> dict:
    d = {
        "id_mensagem": f"<{ident}@demo.rpa-duvidas.local>",
        "nome_remetente": remetente[0],
        "remetente": remetente[1],
        "assunto": assunto,
        "data_recebimento": (datetime(2026, 10, 19, 8, 0) + timedelta(minutes=minutos)).isoformat(),
    }
    if corpo_html:
        d["corpo_html"] = corpo_html
    else:
        d["corpo_texto"] = corpo_texto
    d.update(extra)
    return d


def cenarios(todos: bool) -> list:
    with MASSA.open(encoding="utf-8") as f:
        massa = {r["id"]: r for r in csv.DictReader(f)}
    ids = list(massa) if todos else CURADOS
    lista = [
        email_json(f"demo-{i}", massa[i]["assunto"], massa[i]["corpo"], minutos=n * 3)
        for n, i in enumerate(ids)
    ]
    base = len(lista) * 3
    lista += [
        email_json("demo-html", "RE: Convite portal", corpo_html=CORPO_HTML_COM_HISTORICO,
                   remetente=("João Pereira", "joao.pereira@fornecedor-exemplo.com.br"), minutos=base + 1,
                   anexos=["print_erro.png"]),
        email_json("demo-auto", "Resposta automática: Pagamento NF 123",
                   "Estou fora do escritório até 25/10. Em caso de urgência, contate o financeiro.",
                   minutos=base + 2, cabecalhos={"Auto-Submitted": "auto-replied"}),
        email_json("demo-fora", "Dúvida sobre upload de NF", "Como faço o upload da nota fiscal no portal?",
                   remetente=("Carlos Lima", "carlos@empresa-desconhecida.com.br"), minutos=base + 3),
        email_json("demo-falha", "Reembolso de despesas", "Preciso solicitar reembolso das despesas de viagem.",
                   minutos=base + 4, simular_falha="responder"),
    ]
    return lista


def cenarios_ia() -> list:
    """Cenários da v0.2.0 (perfil demo_ia, IA SIMULADA): exemplos do Anexo A anonimizados + E2 + D1."""
    interno = ("Ana Analista", "ana.analista@empresa-exemplo.com.br")
    itens = [
        ("ia-c03", "Faturamento - [MÊS]/[ANO]", "A NF do faturamento já foi validada e emitida. Precisamos inseri-la no sistema de vocês. Como fazemos?", {}),
        ("ia-c03-erro", "Faturamento [MÊS]/[ANO]", "Estamos tentando inserir a NF no sistema, mas ele volta sempre para a tela de login e não consigo seguir mais.", {"anexos": ["print_erro.png"]}),
        ("ia-c03-po", "Contratação", "Como devemos emitir a NF e fazer o upload? Ainda não recebemos o número do pedido.", {}),
        ("ia-c05", "Atualização de cadastro", "Houve alteração societária no escritório e precisamos atualizar o cadastro junto a vocês. Qual o procedimento?", {}),
        ("ia-c06", "Reembolso de despesas", "Gostaria de saber como fazer o passo a passo para solicitar o reembolso de uma despesa.", {}),
        ("ia-c06-nd", "Reembolso", "Para o reembolso, devo emitir Nota de Débito ou NF?", {}),
        ("ia-c07", "RES: Prévias de Honorários", "Seguem as prévias de honorários para conferência. Por favor, nos orientem sobre o preenchimento do formulário.", {"anexos": ["previas_honorarios.pdf"]}),
        ("ia-c99", "Proposta", "Boa tarde, alguma novidade sobre a nossa proposta comercial?", {}),
        ("ia-timeout", "Faturamento", "Como inserimos a NF? [[simular_timeout]]", {}),
        ("ia-json", "Faturamento", "Como inserimos a NF? [[simular_json_corrigido]]", {}),
    ]
    lista = [email_json(i, a, c, minutos=n * 3, **x) for n, (i, a, c, x) in enumerate(itens)]
    lista.append(email_json("ia-interno", "RE: Faturamento", "Fornecedor, segue o tutorial em anexo.",
                            remetente=interno, minutos=len(itens) * 3 + 1))
    return lista


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--todos", action="store_true", help="inclui os 40 e-mails da massa sintética")
    ap.add_argument("--ia", action="store_true", help="cenários da classificação por IA (perfil demo_ia)")
    args = ap.parse_args()

    perfil = "demo_ia" if args.ia else "demo"
    print(f"Preparando demonstração (perfil {perfil})...")
    for p in (CAIXA, REGISTRO_DEMO_IA if args.ia else REGISTRO_DEMO):
        if p.exists():
            shutil.rmtree(p)
    gerar_tutoriais()
    entrada = CAIXA / "entrada"
    entrada.mkdir(parents=True, exist_ok=True)
    lista = cenarios_ia() if args.ia else cenarios(args.todos)
    for i, d in enumerate(lista, start=1):
        (entrada / f"{i:03d}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  {len(lista)} e-mails fictícios em {entrada.relative_to(RAIZ)}")
    print(f"\nPróximo passo:\n  python -m rpa_duvidas executar --perfil {perfil}")
    print(f"Resultado: dados_teste/caixa_simulada/saida/_indice.html e dados/{perfil}/registro_controle.xlsx")


if __name__ == "__main__":
    main()
