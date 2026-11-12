"""Arquivos do OneDrive "somente on-line" (v0.3.2).

No 1º teste da operação assistida a planilha de escritórios e os tutoriais estavam
só na nuvem e o robô parava pedindo "Sempre manter neste dispositivo". Agora ele
mesmo pede o download antes de usar o arquivo:

* lê o arquivo do começo ao fim – no Windows, o OneDrive (Arquivos sob Demanda)
  baixa o conteúdo quando um programa lê um arquivo "somente on-line";
* a leitura roda numa thread com tempo limite, para o robô não travar se o
  OneDrive estiver fechado ou sem rede;
* depois confere de novo o atributo do arquivo. Continuou na nuvem → ``ErroNuvem``
  com a orientação para o analista.

Não fixa o arquivo no dispositivo (não muda a configuração do OneDrive do
usuário) e não precisa de privilégio de administrador nem de biblioteca nova.
Fora do Windows o atributo não existe e nada muda.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

# Atributos de arquivo do Windows usados pelo OneDrive para "somente on-line"
ATRIBUTOS_NUVEM = 0x00400000 | 0x00040000 | 0x00001000  # RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN | OFFLINE
_BLOCO = 1024 * 1024
_ESPERA_APOS_LEITURA_S = 3.0

# Ajustado por config.carregar() a partir de ``onedrive.*`` (settings.yaml)
_CONF = {"baixar": True, "tempo_limite_s": 120.0}


class ErroNuvem(Exception):
    """O arquivo continua só na nuvem: não foi possível baixá-lo."""


def configurar(baixar: Optional[bool] = None, tempo_limite_s: Optional[float] = None) -> None:
    if baixar is not None:
        _CONF["baixar"] = bool(baixar)
    if tempo_limite_s is not None:
        _CONF["tempo_limite_s"] = max(1.0, float(tempo_limite_s))


def somente_na_nuvem(caminho: Path) -> bool:
    atributos = getattr(os.stat(caminho), "st_file_attributes", 0)  # só existe no Windows
    return bool(atributos & ATRIBUTOS_NUVEM)


def _orientacao(caminho: Path, motivo: str) -> str:
    return (f"Arquivo existe só na nuvem (OneDrive) e {motivo}: {caminho}. Confira se o OneDrive está aberto e "
            "conectado, ou marque a pasta como 'Sempre manter neste dispositivo'.")


def garantir_local(caminho: Path, somente_na_nuvem: Optional[Callable[[Path], bool]] = None,
                   tempo_limite_s: Optional[float] = None, baixar: Optional[bool] = None) -> bool:
    """Garante que o arquivo está baixado. Devolve ``True`` se precisou baixar agora.

    Levanta ``ErroNuvem`` se continuar só na nuvem (download desligado, OneDrive
    fechado/sem rede ou tempo limite esgotado). Pastas só são conferidas.
    """
    verificar = somente_na_nuvem or globals()["somente_na_nuvem"]
    caminho = Path(caminho)
    if not verificar(caminho):
        return False
    baixar = _CONF["baixar"] if baixar is None else baixar
    if not baixar or caminho.is_dir():
        raise ErroNuvem(_orientacao(caminho, "o download automático está desligado" if not baixar
                                    else "não pode ser baixado automaticamente"))
    limite = float(tempo_limite_s or _CONF["tempo_limite_s"])
    log.info("Baixando do OneDrive (arquivo só na nuvem): %s", caminho)
    falha: list = []

    def ler() -> None:
        try:
            with open(caminho, "rb") as f:
                while f.read(_BLOCO):
                    pass
        except OSError as e:          # ex.: provedor de nuvem não está em execução
            falha.append(e)

    inicio = time.monotonic()
    t = threading.Thread(target=ler, name="rpa-download-onedrive", daemon=True)
    t.start()
    t.join(limite)
    if t.is_alive():
        raise ErroNuvem(_orientacao(caminho, f"o download não terminou em {limite:g} s"))
    if falha:
        raise ErroNuvem(_orientacao(caminho, f"o download falhou ({falha[0]})"))
    fim = time.monotonic() + _ESPERA_APOS_LEITURA_S
    while verificar(caminho):
        if time.monotonic() >= fim:
            raise ErroNuvem(_orientacao(caminho, "o OneDrive não o manteve no dispositivo após a leitura"))
        time.sleep(0.25)
    log.info("Baixado do OneDrive em %.1f s: %s", time.monotonic() - inicio, caminho)
    return True
