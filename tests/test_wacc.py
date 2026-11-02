"""Testes do custo medio ponderado de capital."""

from __future__ import annotations

import pytest

from valuation.domain.erros import ErroValidacao, Status
from valuation.domain.premissas import PremissasWACC
from valuation.domain.wacc import beta_alavancado, calcular_wacc, custo_divida


def _premissas(**overrides) -> PremissasWACC:
    dados = dict(
        rf=0.10,
        erp=0.05,
        beta_u=1.0,
        divida=0.0,
        patrimonio=1000.0,
        aliquota=0.34,
        kd=0.10,
    )
    dados.update(overrides)
    return PremissasWACC(**dados)


def test_capm_subtrai_rf() -> None:
    """Regressao: Ke = Rf + beta*Rm dava 20% em vez de 15%."""
    resultado = calcular_wacc(_premissas())
    assert resultado.ke == pytest.approx(0.15)
    assert resultado.wacc == pytest.approx(0.15)


def test_divida_nula_nao_explode() -> None:
    """Regressao: V=1 quando a divida era 0 gerava WACC de bilhoes."""
    resultado = calcular_wacc(_premissas(patrimonio=1e9))
    assert resultado.wacc == pytest.approx(0.15)
    assert resultado.peso_equity + resultado.peso_divida == pytest.approx(1.0)


def test_pesos_usam_divida_bruta() -> None:
    resultado = calcular_wacc(_premissas(divida=1000.0, patrimonio=1000.0))
    assert resultado.peso_equity == pytest.approx(0.5)
    assert resultado.peso_divida == pytest.approx(0.5)


def test_alavancagem_aumenta_beta_e_reduz_wacc() -> None:
    """Divida barata (Kd pos-imposto < Ke) reduz o WACC e eleva o beta."""
    sem_divida = calcular_wacc(_premissas())
    com_divida = calcular_wacc(_premissas(divida=1000.0))
    assert com_divida.beta_l > sem_divida.beta_l
    assert com_divida.wacc < sem_divida.wacc


def test_wacc_fora_da_faixa_levanta() -> None:
    with pytest.raises(ErroValidacao) as exc:
        calcular_wacc(_premissas(erp=0.20, beta_u=3.0, patrimonio=1.0))
    assert exc.value.status is Status.WACC_INVALIDO


def test_patrimonio_invalido_levanta() -> None:
    with pytest.raises(ErroValidacao) as exc:
        calcular_wacc(_premissas(patrimonio=0.0))
    assert exc.value.status is Status.WACC_INVALIDO


def test_beta_alavancado_hamada() -> None:
    assert beta_alavancado(1.0, 500.0, 1000.0, 0.34) == pytest.approx(1.33)


def test_beta_nao_alavancado_para_bancos() -> None:
    """Deposito nao e alavancagem: o beta do banco nao deve ser realavancado."""
    com = calcular_wacc(_premissas(divida=1000.0))
    sem = calcular_wacc(_premissas(divida=1000.0, alavancar_beta=False))
    assert com.beta_l > sem.beta_l
    assert sem.beta_l == pytest.approx(1.0)
    assert sem.ke == pytest.approx(0.15)


def test_beta_degenerado_levanta() -> None:
    """Regressao: AGXY3 (market cap R$ 5 mi, divida R$ 1 bi) dava Ke de 1.681%."""
    with pytest.raises(ErroValidacao) as exc:
        calcular_wacc(_premissas(divida=1_000.0, patrimonio=5.0))
    assert exc.value.status is Status.WACC_INVALIDO
    assert "degenerado" in exc.value.detalhe


def test_custo_divida_limitado() -> None:
    assert custo_divida(50.0, 500.0, rf=0.10) == pytest.approx(0.10)
    assert custo_divida(500.0, 1000.0, rf=0.10) == pytest.approx(0.20)
    assert custo_divida(float("nan"), 1000.0, rf=0.10) == pytest.approx(0.12)
    assert custo_divida(10.0, 0.0, rf=0.10) == pytest.approx(0.12)
