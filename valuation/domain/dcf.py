"""Fluxo de caixa livre para a firma (FCFF) com valor terminal.

Correcoes em relacao a implementacao anterior:

1. O valor terminal cresce a ``g_perpetuidade``, nunca ao crescimento historico de
   receita. Era a causa dos precos de R$ 5.674 (PCAR3) e R$ 482 (GOAU4).
2. A ponte para o equity subtrai apenas a divida liquida. O codigo antigo subtraia
   tambem ``passivo total - divida``, o que gerava 41 precos negativos.
3. O capital de giro entra como variacao (``delta NWC``), nao como nivel.
4. No valor terminal, o CAPEX de manutencao se iguala a D&A e o capital de giro
   cresce apenas com ``g``. Antes, uma empresa que investe acima da depreciacao
   (Vale, Petrobras) era penalizada para sempre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from .erros import ErroValidacao, Status
from .premissas import PremissasDCF

COLUNAS = [
    "ano",
    "receita",
    "ebit",
    "nopat",
    "da",
    "capex",
    "nwc",
    "dnwc",
    "fcff",
    "vp_fcff",
]


@dataclass(frozen=True)
class ResultadoDCF:
    """Resultado completo, com a projecao ano a ano para auditoria."""

    tabela: pd.DataFrame
    ev: float
    vp_explicito: float
    valor_terminal: float
    vp_valor_terminal: float
    equity: float
    preco_por_acao: float


def avaliar_dcf(p: PremissasDCF) -> ResultadoDCF:
    """Projeta o FCFF, desconta e monta o valor por acao."""
    if p.g_perpetuidade >= p.wacc - 0.01:
        raise ErroValidacao(
            Status.G_MAIOR_QUE_WACC,
            f"g={p.g_perpetuidade:.4f} vs WACC={p.wacc:.4f}",
        )
    if p.num_acoes <= 0:
        raise ErroValidacao(Status.DADOS_INSUFICIENTES, "numero de acoes <= 0")

    linhas: list[dict[str, float]] = []
    receita_anterior = p.receita_base
    nwc_anterior = p.nwc_base if p.nwc_base is not None else p.receita_base * p.nwc_receita
    g = p.g_perpetuidade

    for ano in range(1, p.anos + 1):
        if p.crescimento_por_ano is not None:
            # Cenario de receita projetada: usa o vetor estimado pelo modelo.
            if len(p.crescimento_por_ano) < p.anos:
                raise ErroValidacao(
                    Status.DADOS_INSUFICIENTES,
                    f"crescimento_por_ano tem {len(p.crescimento_por_ano)} anos, esperado {p.anos}",
                )
            crescimento = float(p.crescimento_por_ano[ano - 1])
        else:
            # Fade linear: o crescimento historico vale no ano 1 e converge para
            # a perpetuidade no ultimo ano do horizonte. Sem isso, uma empresa
            # que veio de um pico ciclico (-10% a.a.) seria projetada em queda
            # por todo o horizonte explicito e depois cresceria 3% para sempre.
            peso = (ano - 1) / (p.anos - 1) if p.anos > 1 else 1.0
            crescimento = p.crescimento_receita + (g - p.crescimento_receita) * peso

        if crescimento <= -1.0:
            raise ErroValidacao(Status.NAO_AVALIAVEL, "crescimento <= -100%")

        receita = receita_anterior * (1.0 + crescimento)
        ebit = receita * p.margem_ebit
        nopat = ebit * (1.0 - p.aliquota)
        depreciacao = receita * p.da_receita
        capex = receita * p.capex_receita
        nwc = receita * p.nwc_receita
        delta_nwc = nwc - nwc_anterior
        fcff = nopat + depreciacao - capex - delta_nwc

        expoente = ano - 0.5 if p.meio_ano else ano
        valor_presente = fcff / (1.0 + p.wacc) ** expoente

        linhas.append(
            {
                "ano": float(ano),
                "receita": receita,
                "ebit": ebit,
                "nopat": nopat,
                "da": depreciacao,
                "capex": capex,
                "nwc": nwc,
                "dnwc": delta_nwc,
                "fcff": fcff,
                "vp_fcff": valor_presente,
            }
        )
        receita_anterior = receita
        nwc_anterior = nwc

    ultimo = linhas[-1]
    # Estado estacionario: o CAPEX de manutencao se iguala a D&A e o capital de
    # giro cresce apenas com a perpetuidade. Sem isso, uma empresa que investe
    # acima da depreciacao seria penalizada para sempre no valor terminal.
    fcff_terminal = ultimo["nopat"] * (1.0 + g) - g * ultimo["nwc"]
    if fcff_terminal <= 0:
        raise ErroValidacao(Status.NAO_AVALIAVEL, "FCFF terminal <= 0")
    valor_terminal = fcff_terminal / (p.wacc - g)
    expoente_terminal = p.anos - 0.5 if p.meio_ano else p.anos
    vp_valor_terminal = valor_terminal / (1.0 + p.wacc) ** expoente_terminal

    vp_explicito = sum(item["vp_fcff"] for item in linhas)
    ev = vp_explicito + vp_valor_terminal
    equity = ev - p.divida_liquida + p.ativos_nao_operacionais
    preco = equity / p.num_acoes

    if not all(math.isfinite(valor) for valor in (ev, equity, preco)):
        raise ErroValidacao(Status.NAO_AVALIAVEL, "resultado nao finito")

    return ResultadoDCF(
        tabela=pd.DataFrame(linhas, columns=COLUNAS),
        ev=ev,
        vp_explicito=vp_explicito,
        valor_terminal=valor_terminal,
        vp_valor_terminal=vp_valor_terminal,
        equity=equity,
        preco_por_acao=preco,
    )


__all__ = ["COLUNAS", "ResultadoDCF", "avaliar_dcf"]
