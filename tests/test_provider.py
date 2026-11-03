"""Testes do provedor de dados (retry e cache), sem rede."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tests.fabricas import criar_snapshot
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


def _ticker_ok() -> type:
    """Classe que imita ``yf.Ticker`` devolvendo um snapshot completo."""
    base = criar_snapshot()

    class _TickerOk:
        criados = 0

        def __init__(self, ticker: str) -> None:
            _TickerOk.criados += 1
            self.ticker = ticker

        @property
        def info(self) -> dict[str, object]:
            return dict(base.info)

        @property
        def financials(self) -> pd.DataFrame:
            return base.financials

        @property
        def balance_sheet(self) -> pd.DataFrame:
            return base.balance

        @property
        def cashflow(self) -> pd.DataFrame:
            return base.cashflow

        def history(self, **_: object) -> pd.DataFrame:
            return base.history.to_frame("Close")

        @property
        def dividends(self) -> pd.Series:
            return base.dividends

    return _TickerOk


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


def test_cache_em_parquet_ida_e_volta(tmp_path: Path, monkeypatch) -> None:
    """Regressao: sem pyarrow o cache em parquet derrubava a coleta inteira.

    O CI instalava as dependencias do pyproject, que nao declaravam pyarrow, e
    nenhum teste exercitava a gravacao: o pipeline mensal quebrava em
    ``to_parquet`` enquanto a suite seguia verde.
    """
    ticker = _ticker_ok()
    monkeypatch.setattr("valuation.data.provider.yf.Ticker", ticker)

    provider = YFinanceProvider(tmp_path)

    primeiro = provider.obter("TEST3.SA")
    assert ticker.criados == 1
    assert primeiro.ticker == "TEST3.SA"

    # A segunda chamada tem que sair do cache, sem tocar no provedor.
    segundo = provider.obter("TEST3.SA")
    assert ticker.criados == 1
    assert segundo.financials.equals(primeiro.financials)
    assert segundo.history.equals(primeiro.history)


def test_cache_ilegivel_e_ignorado(tmp_path: Path, monkeypatch) -> None:
    """Cache corrompido nao pode impedir a coleta: baixa de novo."""
    ticker = _ticker_ok()
    monkeypatch.setattr("valuation.data.provider.yf.Ticker", ticker)

    provider = YFinanceProvider(tmp_path)
    provider.obter("TEST3.SA")

    # Corrompe os parquet mantendo o snapshot.json, que marca o cache como valido.
    for arquivo in tmp_path.glob("TEST3.SA/*/*.parquet"):
        arquivo.write_bytes(b"lixo")

    provider.obter("TEST3.SA")
    assert ticker.criados == 2
