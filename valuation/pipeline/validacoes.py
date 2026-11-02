"""Portoes de sanidade e recomendacao.

Nenhum numero entra no ranking sem passar por aqui. Antes, valores como WACC de
4 bilhoes ou preco de R$ 5.674 disputavam espaco com resultados legitimos.
"""

from __future__ import annotations

import math

from ..data.universo import eh_financeiro
from ..domain.erros import Status

MODELO_DCF = "dcf"
MODELO_DDM = "ddm"


def validar_resultado(
    preco_alvo_p50: float,
    preco_atual: float,
    dias_ultimo_pregao: int,
    setor: str,
    modelo: str,
    upside_max: float = 0.90,
) -> tuple[Status, list[str]]:
    """Aplica os portoes na ordem de gravidade e devolve ``(status, flags)``."""
    flags: list[str] = []

    if modelo == MODELO_DCF and eh_financeiro(setor):
        return Status.SETOR_INCOMPATIVEL, ["financeira avaliada por FCFF"]

    if dias_ultimo_pregao > 5:
        flags.append(f"ultimo pregao ha {dias_ultimo_pregao} dias")
        return Status.PRECO_DESATUALIZADO, flags

    if preco_atual is None or not math.isfinite(preco_atual) or preco_atual <= 0:
        return Status.PRECO_DESATUALIZADO, ["preco atual invalido"]

    if preco_alvo_p50 is None or not math.isfinite(preco_alvo_p50) or preco_alvo_p50 <= 0:
        return Status.NAO_AVALIAVEL, ["preco-alvo nao finito ou <= 0"]

    upside = preco_alvo_p50 / preco_atual - 1.0
    if abs(upside) > upside_max:
        flags.append(f"upside {upside:.1%} fora do limite de {upside_max:.0%}")
        return Status.RESULTADO_ABSURDO, flags

    return Status.OK, flags


def recomendacao(preco_p25: float, preco_atual: float, margem_seguranca: float) -> str:
    """Decisao binaria com margem de seguranca sobre o piso da faixa."""
    if preco_p25 is None or preco_atual is None or preco_atual <= 0:
        return "n/d"
    if not math.isfinite(preco_p25):
        return "n/d"
    if preco_p25 * (1.0 - margem_seguranca) > preco_atual:
        return "compra"
    if preco_p25 > preco_atual:
        return "neutro"
    return "caro"


__all__ = ["MODELO_DCF", "MODELO_DDM", "recomendacao", "validar_resultado"]
