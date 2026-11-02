"""Sensibilidade e faixa de valor.

Um DCF e uma faixa, nao um numero. A grade WACC x g alimenta os percentis
publicados (P25/P50/P75) e a decisao de margem de seguranca.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .dcf import avaliar_dcf
from .ddm import avaliar_ddm
from .erros import ErroValidacao, Status
from .premissas import PremissasDCF, PremissasDDM


def _percentis(valores: np.ndarray) -> tuple[float, float, float]:
    limpos = valores[np.isfinite(valores) & (valores > 0)]
    if limpos.size == 0:
        raise ErroValidacao(Status.NAO_AVALIAVEL, "grade de sensibilidade sem cenarios validos")
    p25, p50, p75 = np.percentile(limpos, [25, 50, 75])
    return float(p25), float(p50), float(p75)


def grade_sensibilidade(
    p: PremissasDCF,
    delta_wacc: float = 0.02,
    g_max: float = 0.04,
    passo: float = 0.005,
) -> pd.DataFrame:
    """Preco por acao para cada combinacao de WACC e g."""
    waccs = np.arange(p.wacc - delta_wacc, p.wacc + delta_wacc + 1e-9, passo)
    perpetuidades = np.arange(0.0, g_max + 1e-9, passo)

    matriz: list[list[float]] = []
    for wacc in waccs:
        linha: list[float] = []
        for g in perpetuidades:
            cenario = p.model_copy(update={"wacc": float(wacc), "g_perpetuidade": float(g)})
            try:
                linha.append(avaliar_dcf(cenario).preco_por_acao)
            except ErroValidacao:
                linha.append(float("nan"))
        matriz.append(linha)

    return pd.DataFrame(
        matriz,
        index=np.round(waccs, 4),
        columns=np.round(perpetuidades, 4),
    )


def grade_sensibilidade_ddm(
    p: PremissasDDM,
    delta_ke: float = 0.02,
    g_max: float = 0.04,
    passo: float = 0.005,
) -> pd.DataFrame:
    """Preco por acao para cada combinacao de Ke e g no DDM."""
    kes = np.arange(p.ke - delta_ke, p.ke + delta_ke + 1e-9, passo)
    perpetuidades = np.arange(0.0, g_max + 1e-9, passo)

    matriz: list[list[float]] = []
    for ke in kes:
        linha: list[float] = []
        for g in perpetuidades:
            cenario = p.model_copy(update={"ke": float(ke), "g_perpetuidade": float(g)})
            try:
                linha.append(avaliar_ddm(cenario).preco)
            except ErroValidacao:
                linha.append(float("nan"))
        matriz.append(linha)

    return pd.DataFrame(
        matriz,
        index=np.round(kes, 4),
        columns=np.round(perpetuidades, 4),
    )


def faixa_preco(grade: pd.DataFrame) -> tuple[float, float, float]:
    """Percentis 25, 50 e 75 dos cenarios validos."""
    return _percentis(grade.to_numpy(dtype=float))


__all__ = [
    "faixa_preco",
    "grade_sensibilidade",
    "grade_sensibilidade_ddm",
]
