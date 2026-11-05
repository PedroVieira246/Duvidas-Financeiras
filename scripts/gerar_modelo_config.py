"""Gera o configuracao.xlsx (v0.3.0 – tarefa T02).

    python scripts/gerar_modelo_config.py                         # modelo da calibração (A_PREENCHER)
    python scripts/gerar_modelo_config.py --perfil dev --migrar   # migra o perfil dev para o xlsx
    python scripts/gerar_modelo_config.py --saida dist/config/configuracao.xlsx --senha <senha da BT>

A senha das abas protegidas (Geral, Filtros, Listas e a área de parâmetros da
Palavras_chave) é passada só na linha de comando: não fica no código nem no
repositório. Sem --senha, as abas ficam protegidas sem senha.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from rpa_duvidas.config import carregar  # noqa: E402
from rpa_duvidas.config_xlsx_modelo import gerar_modelo  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--perfil", default="calibracao", help="perfil YAML de origem (padrão: calibracao)")
    p.add_argument("--migrar", action="store_true",
                   help="copia os valores do perfil (sem A_PREENCHER) – para conferir a migração dos YAMLs")
    p.add_argument("--saida", default=str(RAIZ / "config" / "configuracao.xlsx"))
    p.add_argument("--senha", default=None, help="senha das abas protegidas (opcional)")
    args = p.parse_args(argv)
    cfg = carregar(args.perfil, raiz=RAIZ)
    destino = gerar_modelo(cfg, Path(args.saida), modelo="perfil" if args.migrar else "calibracao", senha=args.senha)
    print(f"Modelo gravado em {destino}")
    if not args.senha:
        print("AVISO: abas protegidas sem senha (use --senha para a senha da BT).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
