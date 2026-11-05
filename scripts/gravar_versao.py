"""Grava o versao.txt do pacote (versão, data do build e hash do commit) – usado pelo build_exe.bat."""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from rpa_duvidas import __version__  # noqa: E402


def commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RAIZ, capture_output=True, text=True, timeout=10)
        sujo = subprocess.run(["git", "status", "--porcelain"], cwd=RAIZ, capture_output=True, text=True, timeout=10)
        return (r.stdout.strip() or "sem-git") + (" (com alterações não commitadas)" if sujo.stdout.strip() else "")
    except Exception:
        return "sem-git"


if __name__ == "__main__":
    destino = Path(sys.argv[1] if len(sys.argv) > 1 else "versao.txt")
    destino.write_text(f"versao={__version__}\ndata={datetime.now().isoformat(timespec='seconds')}\ncommit={commit()}\n",
                       encoding="utf-8")
    print(destino.read_text(encoding="utf-8"), end="")
