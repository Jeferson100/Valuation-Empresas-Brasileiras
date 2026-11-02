"""Atualiza apenas a secao de resultados do README.

Le o CSV gerado pelo pipeline e substitui o bloco entre os marcadores
``<!-- VALUATION:START -->`` e ``<!-- VALUATION:END -->``. Os caminhos sao
resolvidos a partir do arquivo, entao o script funciona de qualquer diretorio.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from valuation.pipeline.config import carregar_config  # noqa: E402
from valuation.pipeline.relatorio import atualizar_readme  # noqa: E402


def main() -> int:
    """Le ``dados/valores_valuations_acoes.csv`` e reescreve o README."""
    csv = RAIZ / "dados" / "valores_valuations_acoes.csv"
    readme = RAIZ / "README.md"
    config = carregar_config(RAIZ / "config.yaml")

    if not csv.exists():
        print(f"CSV nao encontrado: {csv}", file=sys.stderr)
        return 1

    dados = pd.read_csv(csv)
    if "status" not in dados.columns:
        print(
            f"{csv} esta no formato antigo (sem coluna 'status'). "
            "Rode o pipeline antes de atualizar o README.",
            file=sys.stderr,
        )
        return 1

    atualizar_readme(readme, dados, top=config.top_readme)
    print(f"README atualizado: {readme}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
