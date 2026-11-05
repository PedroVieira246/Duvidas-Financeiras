"""DEV (Windows + Outlook clássico): cria e-mails de teste na pasta RPA_Teste.

    python scripts/enviar_emails_teste_outlook.py --para seu.email@empresa.com.br
    python scripts/enviar_emails_teste_outlook.py --para seu.email@empresa.com.br --ids S01 S06 S24

Envia, a partir da SUA conta, e-mails da massa sintética para o endereço
informado (normalmente você mesmo), com a marca [RPA-TESTE] no assunto.
Depois aguarda a chegada na Caixa de Entrada e move-os para a pasta de
entrada do perfil (caixa.pasta_entrada, ex.: @inbox/RPA_Teste).

v0.2.1: se a pasta de entrada do perfil for a própria Caixa de Entrada
(``@inbox``), os e-mails já estão no lugar certo e nada é movido. Se o Move
falhar (conta Exchange ActiveSync), o script avisa e segue.

Assim o robô trabalha só com e-mails de teste e nunca com a sua Caixa de
Entrada real.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from rpa_duvidas.caixa.outlook_com import OL_MAIL_ITEM, CaixaOutlookCOM, _iterar  # noqa: E402
from rpa_duvidas.config import carregar  # noqa: E402

MARCA = "[RPA-TESTE]"


def _mesma_pasta(a, b) -> bool:
    if a is b:
        return True
    try:
        return str(a.EntryID) == str(b.EntryID)
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--para", required=True, help="destinatário dos e-mails de teste (você)")
    ap.add_argument("--perfil", default="dev")
    ap.add_argument("--ids", nargs="*", help="IDs da massa sintética (padrão: um por categoria)")
    ap.add_argument("--espera", type=int, default=90, help="segundos aguardando a chegada")
    args = ap.parse_args()

    cfg = carregar(args.perfil)
    caixa = CaixaOutlookCOM(
        conta=cfg.get("caixa.conta", ""), pasta_entrada=cfg.exigir("caixa.pasta_entrada"),
        pastas_destino=dict(cfg.exigir("caixa.pastas_destino")), criar_pastas=True,
    )
    with (RAIZ / "tests" / "dados" / "massa_emails_sintetica.csv").open(encoding="utf-8") as f:
        massa = {r["id"]: r for r in csv.DictReader(f)}
    ids = args.ids or ["S01", "S06", "S11", "S15", "S19", "S24", "S32"]

    for i in ids:
        m = caixa.app.CreateItem(OL_MAIL_ITEM)
        m.To = args.para
        m.Subject = f"{MARCA} {massa[i]['assunto']}"
        m.Body = massa[i]["corpo"]
        m.Send()
        print(f"enviado {i}: {massa[i]['assunto']}")

    if _mesma_pasta(caixa.pasta_entrada, caixa.inbox):
        print("A pasta de entrada do perfil é a própria Caixa de Entrada: nada a mover.")
        print("Concluído. Os e-mails chegam em alguns segundos.")
        return 0
    print(f"Aguardando até {args.espera}s para mover para '{cfg.get('caixa.pasta_entrada')}'...")
    faltam, limite = len(ids), time.time() + args.espera
    while faltam and time.time() < limite:
        time.sleep(5)
        for item in list(_iterar(caixa.inbox.Items)):
            if MARCA in str(getattr(item, "Subject", "")):
                try:
                    item.Move(caixa.pasta_entrada)
                except Exception as e:  # ex.: conta Exchange ActiveSync
                    print(f"Não foi possível mover '{item.Subject}' ({e}). Mova manualmente.")
                    return 1
                faltam -= 1
    print("Concluído." if not faltam else f"{faltam} e-mail(s) não chegaram a tempo – mova manualmente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
