"""Traducao de demonstracoes contabeis em premissas de valuation.

Toda a extracao passa por ``linha``/``serie``/``mediana_robusta``, que tratam
campos ausentes e infinitos de forma uniforme.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..data.snapshot import SnapshotFinanceiro
from ..domain.erros import ErroValidacao, Status
from ..domain.premissas import PremissasDCF, PremissasDDM
from ..domain.series import (
    anos_do_indice,
    crescimento_log,
    deflacionar,
    linha,
    mediana_robusta,
    razao,
    serie,
)
from .config import Config

COMPONENTES_NWC_ATIVO = (
    "Accounts Receivable",
    "AccountsReceivable",
    "Inventory",
    "Other Current Assets",
    "OtherCurrentAssets",
)
COMPONENTES_NWC_PASSIVO = (
    "Accounts Payable",
    "AccountsPayable",
    "PayablesAndAccruedExpenses",
    "Other Current Liabilities",
    "OtherCurrentLiabilities",
)
ATIVOS_NAO_OPERACIONAIS = (
    "Investments And Advances",
    "Long Term Equity Investment",
    "Other Investments",
)


@dataclass(frozen=True)
class Indicadores:
    """Indicadores normalizados de um ticker."""

    receita_base: float
    crescimento_receita: float
    margem_ebit: float
    aliquota: float
    da_receita: float
    capex_receita: float
    nwc_receita: float
    nwc_base: float
    divida_bruta: float
    caixa: float
    ativos_nao_operacionais: float
    despesa_juros: float
    num_acoes: float
    preco_atual: float
    dps_base: float
    payout: float
    roe: float
    fator_cambio: float = 1.0

    @property
    def divida_liquida(self) -> float:
        """Divida bruta menos caixa e equivalentes."""
        return self.divida_bruta - self.caixa


def _soma_componentes(df: pd.DataFrame, nomes: tuple[str, ...]) -> pd.Series:
    """Soma os componentes disponiveis, exigindo ao menos um."""
    partes = {}
    for nome in nomes:
        valores = serie(df, nome)
        if not valores.empty:
            partes[nome] = valores
    if not partes:
        return pd.Series(dtype=float)
    return pd.DataFrame(partes).sum(axis=1, min_count=1)


def aliquota_efetiva(financials: pd.DataFrame, setor: str) -> float:
    """Aliquota efetiva historica, restrita a anos com lucro antes do imposto.

    Antes a conta era ``Tax Provision / EBIT`` sem corte, o que produzia
    aliquotas de 3.796% (PCAR3) e 593% (MGLU3).
    """
    teto = 0.45 if setor == "Financeiro" else 0.34
    dados = pd.DataFrame(
        {
            "imposto": serie(financials, "Tax Provision"),
            "antes_imposto": serie(financials, "Pretax Income"),
        }
    ).dropna()
    dados = dados[dados["antes_imposto"] > 0]

    if dados.empty:
        return teto

    taxa = (dados["imposto"] / dados["antes_imposto"]).clip(0.0, teto).median()
    return float(np.clip(taxa, 0.0, teto))


def num_acoes(snapshot: SnapshotFinanceiro) -> float:
    """Acoes em circulacao, com fallbacks em ordem de confiabilidade."""
    info = snapshot.info
    for chave in ("impliedSharesOutstanding", "sharesOutstanding"):
        valor = info.get(chave)
        try:
            numero = float(valor) if valor is not None else float("nan")
        except (TypeError, ValueError):
            continue
        if math.isfinite(numero) and numero > 0:
            return numero

    market_cap = info.get("marketCap")
    preco = snapshot.preco_atual
    try:
        market_cap_num = float(market_cap) if market_cap is not None else float("nan")
    except (TypeError, ValueError):
        market_cap_num = float("nan")

    if math.isfinite(market_cap_num) and market_cap_num > 0 and preco > 0:
        return market_cap_num / preco

    raise ErroValidacao(Status.DADOS_INSUFICIENTES, "numero de acoes indisponivel")


def dps_base(dividendos: pd.Series) -> float:
    """Mediana dos dividendos anuais dos ultimos tres anos completos.

    Tres anos (em vez de cinco) reduzem o atraso em empresas com dividendo
    crescente, sem herdar um ano atipico isolado.
    """
    if dividendos is None or dividendos.empty:
        return 0.0

    anual = dividendos.groupby(anos_do_indice(dividendos.index)).sum()
    ano_corrente = pd.Timestamp.today().year
    completos = anual[anual.index < ano_corrente]
    if completos.empty:
        return 0.0
    return float(completos.tail(3).median())


def montar_indicadores(
    snapshot: SnapshotFinanceiro,
    setor: str,
    indice_ipca: pd.Series | None,
    config: Config,
    fator_cambio: float = 1.0,
) -> Indicadores:
    """Extrai e normaliza os indicadores usados pelos modelos.

    ``fator_cambio`` converte os valores monetarios das demonstracoes para a
    moeda do preco (ver :func:`valuation.data.moeda.detectar_fator_cambio`).
    Razoes e percentuais nao sao afetados.
    """
    financials = snapshot.financials
    balance = snapshot.balance
    cashflow = snapshot.cashflow

    receita = serie(financials, "Total Revenue").sort_index()
    if receita.empty:
        raise ErroValidacao(Status.DADOS_INSUFICIENTES, "Total Revenue ausente")

    ebit = serie(financials, "EBIT", "Operating Income", "Pretax Income").sort_index()
    margem_ebit = mediana_robusta(razao(ebit, receita), padrao=0.0, clip=(0.0, 0.60))
    if margem_ebit <= 0:
        raise ErroValidacao(Status.NAO_AVALIAVEL, f"margem EBIT mediana <= 0 ({margem_ebit:.4f})")

    receita_ultima = float(receita.iloc[-1])
    if not math.isfinite(receita_ultima) or receita_ultima <= 0:
        raise ErroValidacao(Status.NAO_AVALIAVEL, f"receita base <= 0 ({receita_ultima:.4f})")

    depreciacao = serie(
        financials, "Depreciation And Amortization", "Reconciled Depreciation"
    ).abs()
    capex = serie(cashflow, "Capital Expenditure").abs()

    ativos_giro = _soma_componentes(balance, COMPONENTES_NWC_ATIVO)
    passivos_giro = _soma_componentes(balance, COMPONENTES_NWC_PASSIVO)
    if ativos_giro.empty and passivos_giro.empty:
        nwc = pd.Series(dtype=float)
    elif ativos_giro.empty:
        nwc = -passivos_giro
    elif passivos_giro.empty:
        nwc = ativos_giro
    else:
        nwc = ativos_giro.sub(passivos_giro, fill_value=0.0)

    divida_bruta = linha(balance, "Total Debt", "TotalDebt", padrao=float("nan"))
    if not math.isfinite(divida_bruta):
        divida_bruta = float(snapshot.info.get("totalDebt") or 0.0)

    caixa = linha(
        balance,
        "Cash And Cash Equivalents",
        "CashCashEquivalentsAndShortTermInvestments",
        "Cash",
        padrao=float("nan"),
    )
    if not math.isfinite(caixa):
        caixa = float(snapshot.info.get("totalCash") or 0.0)

    ativos_nao_operacionais = float(
        max(
            (max(linha(balance, nome, padrao=0.0), 0.0) for nome in ATIVOS_NAO_OPERACIONAIS),
            default=0.0,
        )
    )

    if indice_ipca is not None and len(receita) >= 3:
        crescimento = crescimento_log(deflacionar(receita, indice_ipca))
    else:
        crescimento = crescimento_log(receita)

    despesa_juros = linha(financials, "Interest Expense", "InterestExpense")
    payout = snapshot.info.get("payoutRatio")
    try:
        payout_num = float(payout) if payout is not None else float("nan")
    except (TypeError, ValueError):
        payout_num = float("nan")

    roe = snapshot.info.get("returnOnEquity")
    try:
        roe_num = float(roe) if roe is not None else float("nan")
    except (TypeError, ValueError):
        roe_num = float("nan")

    preco = snapshot.preco_atual
    if not math.isfinite(preco) or preco <= 0:
        raise ErroValidacao(Status.PRECO_DESATUALIZADO, "preco atual invalido")

    return Indicadores(
        receita_base=float(receita.iloc[-1]) * fator_cambio,
        crescimento_receita=crescimento,
        margem_ebit=margem_ebit,
        aliquota=aliquota_efetiva(financials, setor),
        da_receita=mediana_robusta(razao(depreciacao, receita), padrao=0.05, clip=(0.0, 0.50)),
        capex_receita=mediana_robusta(razao(capex, receita), padrao=0.05, clip=(0.0, 0.50)),
        nwc_receita=mediana_robusta(razao(nwc, receita), padrao=0.0, clip=(-0.50, 0.50)),
        nwc_base=(
            float(nwc.iloc[-1]) * fator_cambio
            if not nwc.empty and math.isfinite(nwc.iloc[-1])
            else 0.0
        ),
        divida_bruta=divida_bruta * fator_cambio,
        caixa=caixa * fator_cambio,
        ativos_nao_operacionais=ativos_nao_operacionais * fator_cambio,
        despesa_juros=despesa_juros * fator_cambio,
        num_acoes=num_acoes(snapshot),
        preco_atual=preco,
        dps_base=dps_base(snapshot.dividends),
        payout=payout_num,
        roe=roe_num,
        fator_cambio=fator_cambio,
    )


def premissas_dcf(
    indicadores: Indicadores,
    wacc: float,
    config: Config,
    crescimento_por_ano: tuple[float, ...] | None = None,
) -> PremissasDCF:
    """Monta as premissas do FCFF a partir dos indicadores.

    ``crescimento_por_ano`` e opcional: quando ausente, o DCF usa o fade linear
    sobre o crescimento historico (valuation oficial).
    """
    return PremissasDCF(
        receita_base=indicadores.receita_base,
        crescimento_receita=indicadores.crescimento_receita,
        crescimento_por_ano=crescimento_por_ano,
        margem_ebit=indicadores.margem_ebit,
        aliquota=indicadores.aliquota,
        da_receita=indicadores.da_receita,
        capex_receita=indicadores.capex_receita,
        nwc_receita=indicadores.nwc_receita,
        nwc_base=indicadores.nwc_base,
        wacc=wacc,
        g_perpetuidade=config.g_perpetuidade,
        anos=config.anos_projecao,
        divida_liquida=indicadores.divida_liquida,
        ativos_nao_operacionais=indicadores.ativos_nao_operacionais,
        num_acoes=indicadores.num_acoes,
        meio_ano=config.meio_ano,
    )


def premissas_ddm(indicadores: Indicadores, ke: float, config: Config) -> PremissasDDM:
    """Monta as premissas do DDM de dois estagios."""
    if indicadores.dps_base <= 0:
        raise ErroValidacao(Status.SEM_DIVIDENDOS, "sem dividendo anual identificado")

    payout = indicadores.payout
    if not math.isfinite(payout) or not (0.0 <= payout <= 1.0):
        payout = 0.5

    roe = indicadores.roe if math.isfinite(indicadores.roe) else 0.10
    g_sustentavel = float(np.clip(roe * (1.0 - payout), 0.0, 0.15))

    return PremissasDDM(
        dps_base=indicadores.dps_base,
        g1=g_sustentavel,
        anos_g1=config.anos_projecao,
        g_perpetuidade=config.g_perpetuidade,
        ke=ke,
    )


__all__ = [
    "Indicadores",
    "aliquota_efetiva",
    "dps_base",
    "montar_indicadores",
    "num_acoes",
    "premissas_dcf",
    "premissas_ddm",
]
