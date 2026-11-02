"""Premissas de entrada, validadas na fronteira do dominio.

Regras de faixa ficam aqui (Pydantic). Regras semanticas que dependem de mais de
um campo (``g < WACC``, ``Ke > g``) ficam nas funcoes de calculo, para produzirem
um ``Status`` especifico em vez de um erro de parsing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PremissasWACC(BaseModel):
    """Entradas do custo medio ponderado de capital."""

    rf: float = Field(gt=0.0, lt=0.5, description="taxa livre de risco nominal a.a.")
    erp: float = Field(gt=0.0, lt=0.3, description="premio de risco de mercado + pais")
    beta_u: float = Field(gt=0.0, le=3.0, description="beta desalavancado")
    divida: float = Field(ge=0.0, description="divida bruta")
    patrimonio: float = Field(ge=0.0, description="valor de mercado do equity")
    aliquota: float = Field(ge=0.0, le=0.45, description="aliquota marginal efetiva")
    kd: float = Field(ge=0.0, lt=1.0, description="custo da divida antes do imposto")
    alavancar_beta: bool = Field(
        default=True,
        description="aplica Hamada; desligado em bancos, onde depositos nao sao alavancagem",
    )


class PremissasDCF(BaseModel):
    """Entradas do fluxo de caixa livre para a firma (FCFF)."""

    receita_base: float = Field(gt=0)
    crescimento_receita: float = Field(gt=-1.0, lt=1.0)
    margem_ebit: float = Field(ge=0.0, lt=1.0)
    aliquota: float = Field(ge=0.0, le=0.45)
    da_receita: float = Field(ge=0.0, lt=1.0, description="D&A / receita")
    capex_receita: float = Field(ge=0.0, lt=1.0, description="CAPEX / receita")
    nwc_receita: float = Field(ge=-1.0, lt=1.0, description="capital de giro / receita")
    wacc: float = Field(gt=0.0, lt=0.5)
    g_perpetuidade: float = Field(ge=0.0, lt=0.20)
    anos: int = Field(default=5, ge=1, le=15)
    nwc_base: float | None = Field(default=None, description="NWC do ultimo balanco")
    divida_liquida: float = Field(default=0.0, description="divida bruta - caixa")
    ativos_nao_operacionais: float = Field(default=0.0)
    num_acoes: float = Field(ge=0.0)
    meio_ano: bool = Field(default=False, description="convencao de meio de ano")


class PremissasDDM(BaseModel):
    """Entradas do modelo de dividendos descontados em dois estagios."""

    dps_base: float = Field(ge=0.0, description="dividendo por acao do ultimo ano cheio")
    g1: float = Field(gt=-1.0, lt=1.0, description="crescimento do primeiro estagio")
    anos_g1: int = Field(default=5, ge=1, le=15)
    g_perpetuidade: float = Field(ge=0.0, lt=0.20)
    ke: float = Field(gt=0.0, lt=1.0)


__all__ = ["PremissasDCF", "PremissasDDM", "PremissasWACC"]
