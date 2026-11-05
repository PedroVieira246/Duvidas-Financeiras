"""Ponto de entrada do executável (PyInstaller – rpa_duvidas.spec).

Sem argumentos (duplo clique) abre o menu do console; com argumentos mantém a
linha de comando: verificar, previa, executar [--loop], reprocessar, exportar,
arquivar-pendentes. Perfil padrão no .exe: calibracao.
"""
import sys

from rpa_duvidas.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
