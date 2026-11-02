"""Snapshot imutavel de um ticker.

Um unico objeto concentra tudo o que os indicadores precisam. Antes, cada classe
de calculo criava o proprio ``yf.Ticker`` e refazia as mesmas requisicoes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class SnapshotFinanceiro:
    """Dados de um ticker em uma data de referencia."""

    ticker: str
    as_of: date
    info: dict[str, Any]
    financials: pd.DataFrame
    balance: pd.DataFrame
    cashflow: pd.DataFrame
    history: pd.Series
    dividends: pd.Series

    @property
    def preco_atual(self) -> float:
        """Ultimo preco de fechamento ajustado."""
        if self.history.empty:
            return float("nan")
        return float(self.history.iloc[-1])

    @property
    def data_ultimo_pregao(self) -> date | None:
        """Data do ultimo pregao disponivel."""
        if self.history.empty:
            return None
        return pd.Timestamp(self.history.index[-1]).date()


__all__ = ["SnapshotFinanceiro"]
