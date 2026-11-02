"""Testes da grade de sensibilidade e da faixa de preco."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from valuation.domain.dcf import avaliar_dcf
from valuation.domain.erros import ErroValidacao, Status
from valuation.domain.premissas import PremissasDCF
from valuation.domain.sensibilidade import faixa_preco, grade_sensibilidade


def _premissas(**overrides) -> PremissasDCF:
    dados = dict(
        receita_base=1000.0,
        crescimento_receita=0.0,
        margem_ebit=0.20,
        aliquota=0.34,
        da_receita=0.05,
        capex_receita=0.05,
        nwc_receita=0.0,
        wacc=0.12,
        g_perpetuidade=0.03,
        anos=5,
        num_acoes=100.0,
    )
    dados.update(overrides)
    return PremissasDCF(**dados)


def test_faixa_ordena_os_percentis() -> None:
    grade = pd.DataFrame([[1.0, 2.0, 3.0, 4.0, 5.0]])
    p25, p50, p75 = faixa_preco(grade)

    assert p25 < p50 < p75
    assert p50 == pytest.approx(3.0)


def test_faixa_ignora_cenarios_invalidos() -> None:
    grade = pd.DataFrame([[np.nan, -10.0, 0.0, 2.0, 2.0, 2.0]])
    assert faixa_preco(grade) == pytest.approx((2.0, 2.0, 2.0))


def test_faixa_sem_cenarios_levanta() -> None:
    grade = pd.DataFrame([[np.nan, -1.0, 0.0]])
    with pytest.raises(ErroValidacao) as exc:
        faixa_preco(grade)
    assert exc.value.status is Status.NAO_AVALIAVEL


def test_grade_cobre_wacc_e_g() -> None:
    premissas = _premissas()
    grade = grade_sensibilidade(premissas, delta_wacc=0.02, g_max=0.04, passo=0.005)

    assert grade.shape == (9, 9)
    assert grade.index.min() == pytest.approx(0.10)
    assert grade.index.max() == pytest.approx(0.14)
    assert grade.columns.max() == pytest.approx(0.04)

    # O centro da grade e o cenario base.
    centro = grade.loc[0.12, 0.03]
    assert centro == pytest.approx(avaliar_dcf(premissas).preco_por_acao)


def test_grade_marca_cenarios_invalidos_como_nan() -> None:
    """Com WACC baixo, os maiores g violam g < WACC e viram NaN."""
    grade = grade_sensibilidade(_premissas(wacc=0.04, g_perpetuidade=0.03))
    assert grade.isna().to_numpy().any()
