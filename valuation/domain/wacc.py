"""Custo medio ponderado de capital.

Correcoes em relacao a implementacao anterior:

1. CAPM usa ``Ke = Rf + beta * (Rm - Rf)``. O codigo antigo somava ``beta * Rm``,
   inflando o custo de capital em ``beta * Rf`` (cerca de 15 p.p. com beta 1).
2. Os pesos usam ``E = market cap`` e ``D = divida bruta``, com ``V = E + D``.
   O codigo antigo caia para ``V = 1`` quando a divida liquida era nula, gerando
   WACCs de bilhoes (CRFB3, IGTI11).
3. Nao existe fallback silencioso: WACC fora de (0; 50%) levanta ``ErroValidacao``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .erros import ErroValidacao, Status
from .premissas import PremissasWACC

#: Beta alavancado acima disso indica estrutura de capital degenerada (market
#: cap minusculo contra divida enorme), nao risco sistematico. Sem o limite, um
#: caso como AGXY3 produziria ``Ke`` de 1.681% e derrubaria o pipeline.
BETA_MAX = 5.0


@dataclass(frozen=True)
class ResultadoWACC:
    """Saida detalhada do calculo, para auditoria no CSV."""

    wacc: float
    ke: float
    kd: float
    beta_l: float
    peso_equity: float
    peso_divida: float


def beta_alavancado(beta_u: float, divida: float, patrimonio: float, aliquota: float) -> float:
    """Equacao de Hamada: ``beta_l = beta_u * (1 + (1 - t) * D/E)``."""
    if patrimonio <= 0:
        raise ErroValidacao(Status.WACC_INVALIDO, "patrimonio <= 0 para alavancar beta")
    return beta_u * (1.0 + (1.0 - aliquota) * divida / patrimonio)


def custo_divida(
    despesa_juros: float,
    divida_media: float,
    rf: float,
    teto_spread: float = 0.10,
) -> float:
    """``Kd = |juros| / divida media``, limitado a ``[rf, rf + teto_spread]``."""
    if divida_media <= 0 or not math.isfinite(despesa_juros):
        return rf + 0.02
    kd = abs(despesa_juros) / divida_media
    return min(max(kd, rf), rf + teto_spread)


def calcular_wacc(p: PremissasWACC) -> ResultadoWACC:
    """Calcula o WACC e valida o resultado."""
    if p.patrimonio <= 0:
        raise ErroValidacao(Status.WACC_INVALIDO, "patrimonio de mercado <= 0")

    valor_total = p.patrimonio + p.divida
    if valor_total <= 0:
        raise ErroValidacao(Status.WACC_INVALIDO, "E + D <= 0")

    beta_l = (
        beta_alavancado(p.beta_u, p.divida, p.patrimonio, p.aliquota)
        if p.alavancar_beta
        else p.beta_u
    )
    if not math.isfinite(beta_l) or beta_l > BETA_MAX:
        raise ErroValidacao(
            Status.WACC_INVALIDO,
            f"beta alavancado degenerado ({beta_l:.1f} > {BETA_MAX:.0f}): "
            f"D/E = {p.divida / p.patrimonio:.0f}",
        )

    ke = p.rf + beta_l * p.erp
    if not math.isfinite(ke) or not (0.0 < ke < 1.0):
        raise ErroValidacao(Status.WACC_INVALIDO, f"Ke fora de (0; 100%): {ke:.4f}")
    peso_equity = p.patrimonio / valor_total
    peso_divida = p.divida / valor_total

    wacc = peso_equity * ke + peso_divida * p.kd * (1.0 - p.aliquota)

    if not math.isfinite(wacc) or not (0.0 < wacc < 0.5):
        raise ErroValidacao(Status.WACC_INVALIDO, f"WACC fora de (0; 50%): {wacc:.4f}")

    return ResultadoWACC(
        wacc=wacc,
        ke=ke,
        kd=p.kd,
        beta_l=beta_l,
        peso_equity=peso_equity,
        peso_divida=peso_divida,
    )


__all__ = ["BETA_MAX", "ResultadoWACC", "beta_alavancado", "calcular_wacc", "custo_divida"]
