"""Ponto de entrada legado da coleta de valuation.

Mantido para nao quebrar quem chama ``python codigos_rodando/rodando_valuations.py``
nem o workflow antigo. Toda a logica vive em :mod:`valuation.pipeline.run`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite rodar o arquivo diretamente, sem instalar o pacote.
RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from valuation.pipeline.run import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
