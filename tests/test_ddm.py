"""Testes do modelo de dividendos descontados."""

from __future__ import annotations

import pytest

from valuation.domain.ddm import avaliar_ddm
from valuation.domain.erros import ErroValidacao, Status
from valuation.domain.premissas import PremissasDDM


def _premissas(**overrides) -> PremissasDDM:
    dados = dict(dps_base=1.0, g1=0.0, anos_g1=1, g_perpetuidade=0.0, ke=0.10)
    dados.update(overrides)
    return PremissasDDM(**dados)


def test_gordon_um_estagio() -> None:
    """Com g=0, P = D/Ke = 10."""
    assert avaliar_ddm(_premissas()).preco == pytest.approx(10.0)


def test_dois_estagios_valem_mais_que_perpetuidade() -> None:
    sem_crescimento = avaliar_ddm(_premissas(anos_g1=5))
    com_crescimento = avaliar_ddm(_premissas(g1=0.05, anos_g1=5))
    assert com_crescimento.preco > sem_crescimento.preco


def test_sem_dividendo_levanta() -> None:
    with pytest.raises(ErroValidacao) as exc:
        avaliar_ddm(_premissas(dps_base=0.0))
    assert exc.value.status is Status.SEM_DIVIDENDOS


def test_ke_menor_que_g_levanta() -> None:
    with pytest.raises(ErroValidacao) as exc:
        avaliar_ddm(_premissas(ke=0.02, g_perpetuidade=0.03))
    assert exc.value.status is Status.G_MAIOR_QUE_WACC


def test_g1_efetivo_e_limitado() -> None:
    """O primeiro estagio nunca se aproxima de Ke."""
    resultado = avaliar_ddm(_premissas(g1=0.50, anos_g1=5, ke=0.12, g_perpetuidade=0.03))
    assert resultado.g1_efetivo == pytest.approx(0.07)
    assert resultado.preco > 0
