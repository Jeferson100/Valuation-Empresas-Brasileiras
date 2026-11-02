"""Fixtures compartilhadas: snapshots sinteticos, sem rede."""

from __future__ import annotations

import pandas as pd
import pytest

from tests.fabricas import (
    criar_balance,
    criar_cashflow,
    criar_financials,
    criar_snapshot,
)


@pytest.fixture
def financials() -> pd.DataFrame:
    return criar_financials()


@pytest.fixture
def balance() -> pd.DataFrame:
    return criar_balance()


@pytest.fixture
def cashflow() -> pd.DataFrame:
    return criar_cashflow()


@pytest.fixture
def snapshot():
    return criar_snapshot()
