"""Testes do provedor de dados (retry e cache), sem rede."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from valuation.data.provider import YFinanceProvider
from valuation.domain.erros import ErroDados


class _TickerVazio:
    """Simula o Yahoo devolvendo 200 sem demonstracoes (throttling)."""

    criados = 0

    def __init__(self, ticker: str) -> None:
        _TickerVazio.criados += 1
        self.ticker = ticker

    @property
    def info(self) -> dict[str, object]:
        return {}

    @property
    def financials(self) -> pd.DataFrame:
        return pd.DataFrame()

    @property
    def balance_sheet(self) -> pd.DataFrame:
        return pd.DataFrame()

    @property
    def cashflow(self) -> pd.DataFrame:
        return pd.DataFrame()

    def history(self, **_: object) -> pd.DataFrame:
        return pd.DataFrame()

    @property
    def dividends(self) -> pd.Series:
        return pd.Series(dtype=float)


def test_demonstracoes_vazias_sao_retentadas(tmp_path: Path, monkeypatch) -> None:
    """Regressao: resposta vazia levantava ErroDados e pulava o retry."""
    _TickerVazio.criados = 0
    monkeypatch.setattr("valuation.data.provider.yf.Ticker", _TickerVazio)
    monkeypatch.setattr("valuation.data.provider.time.sleep", lambda _: None)

    provider = YFinanceProvider(tmp_path, tentativas=3)

    with pytest.raises(ErroDados) as exc:
        provider.obter("VAZIO3.SA")

    assert _TickerVazio.criados == 3
    assert "demonstracoes financeiras vazias" in str(exc.value)


def test_falha_de_coleta_nao_e_cacheada(tmp_path: Path, monkeypatch) -> None:
    """Uma coleta que falhou nao pode virar cache valido."""
    _TickerVazio.criados = 0
    monkeypatch.setattr("valuation.data.provider.yf.Ticker", _TickerVazio)

    provider = YFinanceProvider(tmp_path, tentativas=1)
    with pytest.raises(ErroDados):
        provider.obter("VAZIO3.SA")
    assert _TickerVazio.criados == 1

    # Nada foi gravado (a coleta falhou), entao a proxima chamada tenta de novo.
    with pytest.raises(ErroDados):
        provider.obter("VAZIO3.SA")
    assert _TickerVazio.criados == 2
