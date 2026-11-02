"""Testes dos utilitarios de series temporais."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from valuation.domain.series import (
    crescimento_log,
    deflacionar,
    indice_ipca_anual,
    linha,
    mediana_robusta,
    serie,
)


def _ipca(meses: list[float], inicio: str = "2020-01-01") -> pd.Series:
    return pd.Series(meses, index=pd.date_range(inicio, periods=len(meses), freq="MS"))


def test_deflacao_zera_crescimento_real() -> None:
    """Regressao: o codigo anterior multiplicava pelo indice, inflando a receita."""
    indice = indice_ipca_anual(_ipca([1.0] * 48))
    base = 1000.0

    receita = pd.Series(
        [base * indice.loc[2021], base * indice.loc[2022], base * indice.loc[2023]],
        index=pd.to_datetime(["2021-12-31", "2022-12-31", "2023-12-31"]),
    )
    real = deflacionar(receita, indice)

    assert real.pct_change().dropna().abs().max() < 1e-9
    assert real.iloc[0] == pytest.approx(base)


def test_indice_ipca_anual_acumula() -> None:
    ipca = _ipca([1.0] * 24)
    indice = indice_ipca_anual(ipca)
    assert indice.iloc[0] == pytest.approx(1.01**12)
    assert indice.iloc[1] == pytest.approx(1.01**24)


def test_crescimento_log_geometrico() -> None:
    receita = pd.Series([100.0, 110.0, 121.0, 133.1])
    assert crescimento_log(receita) == pytest.approx(0.10, abs=1e-9)


def test_crescimento_log_aplicar_clip() -> None:
    receita = pd.Series([100.0, 200.0, 400.0])
    assert crescimento_log(receita) == pytest.approx(0.20)


def test_crescimento_log_serie_curta() -> None:
    assert crescimento_log(pd.Series([100.0, 110.0])) == 0.0


def test_linha_com_fallback() -> None:
    df = pd.DataFrame({"x": [1.0]}, index=["Campo Alternativo"])
    assert linha(df, "Inexistente", "Campo Alternativo") == 1.0
    assert np.isnan(linha(df, "Inexistente"))
    assert linha(None, "Qualquer", padrao=7.0) == 7.0


def test_serie_ignora_nulos() -> None:
    df = pd.DataFrame([[1.0, np.nan, 3.0]], index=["Campo"], columns=[2020, 2021, 2022])
    assert list(serie(df, "Campo")) == [1.0, 3.0]


def test_mediana_robusta_com_minimo() -> None:
    assert mediana_robusta(pd.Series([1.0]), padrao=0.5) == 0.5
    assert mediana_robusta(pd.Series([1.0, 3.0]), padrao=0.5) == 2.0
    assert mediana_robusta(pd.Series([1.0, 3.0]), padrao=0.5, clip=(0.0, 1.5)) == 1.5
