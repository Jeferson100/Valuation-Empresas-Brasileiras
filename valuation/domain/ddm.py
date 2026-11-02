"""Dividendos descontados em dois estagios.

Substitui o modelo de Gordon de um estagio, que produzia 43 precos negativos
porque ``g_sustentavel = ROE * (1 - payout)`` frequentemente supera o custo de
capital proprio e nao havia guarda alguma.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .erros import ErroValidacao, Status
from .premissas import PremissasDDM


@dataclass(frozen=True)
class ResultadoDDM:
    """Resultado do DDM de dois estagios."""

    preco: float
    vp_explicito: float
    vp_valor_terminal: float
    g1_efetivo: float


def avaliar_ddm(p: PremissasDDM) -> ResultadoDDM:
    """Desconta dividendos do primeiro estagio e o valor terminal."""
    if p.dps_base <= 0:
        raise ErroValidacao(Status.SEM_DIVIDENDOS, "DPS base <= 0")
    if p.ke <= p.g_perpetuidade + 0.01:
        raise ErroValidacao(
            Status.G_MAIOR_QUE_WACC,
            f"Ke={p.ke:.4f} <= g={p.g_perpetuidade:.4f} + 1 p.p.",
        )

    # Guarda: o crescimento do primeiro estagio nunca pode se aproximar de Ke.
    g1 = min(p.g1, p.ke - p.g_perpetuidade - 0.02)

    dividendo = p.dps_base
    vp_explicito = 0.0
    for ano in range(1, p.anos_g1 + 1):
        dividendo *= 1.0 + g1
        vp_explicito += dividendo / (1.0 + p.ke) ** ano

    vp_valor_terminal = (dividendo * (1.0 + p.g_perpetuidade) / (p.ke - p.g_perpetuidade)) / (
        1.0 + p.ke
    ) ** p.anos_g1

    preco = vp_explicito + vp_valor_terminal
    if not math.isfinite(preco):
        raise ErroValidacao(Status.NAO_AVALIAVEL, "resultado nao finito")

    return ResultadoDDM(
        preco=preco,
        vp_explicito=vp_explicito,
        vp_valor_terminal=vp_valor_terminal,
        g1_efetivo=g1,
    )


__all__ = ["ResultadoDDM", "avaliar_ddm"]
