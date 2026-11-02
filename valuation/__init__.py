"""Valuation de empresas brasileiras por fluxo de caixa descontado.

Pacote organizado em tres camadas:

- ``valuation.domain``   -- matematica pura, sem rede e sem I/O;
- ``valuation.data``     -- coleta, cache e normalizacao de dados;
- ``valuation.pipeline`` -- orquestracao, validacao e relatorios.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__"]
