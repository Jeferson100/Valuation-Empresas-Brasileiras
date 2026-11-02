"""Fabrica de dados sinteticos para testes (sem rede)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from valuation.data.snapshot import SnapshotFinanceiro


def _datas(anos: list[int]) -> pd.DatetimeIndex:
    return pd.DatetimeIndex([pd.Timestamp(f"{ano}-12-31") for ano in anos])


def criar_financials() -> pd.DataFrame:
    """Demonstracoes estaveis: receita +10% a.a., margem EBIT 20%."""
    datas = _datas([2021, 2022, 2023, 2024])
    receita = [1000.0, 1100.0, 1210.0, 1331.0]
    ebit = [valor * 0.20 for valor in receita]
    antes_imposto = [valor * 0.80 for valor in ebit]
    depreciacao = [50.0, 55.0, 60.0, 66.0]
    juros = [40.0, 44.0, 48.0, 53.0]

    return pd.DataFrame(
        {
            datas[0]: [
                receita[0],
                ebit[0],
                antes_imposto[0] * 0.34,
                antes_imposto[0],
                depreciacao[0],
                juros[0],
            ],
            datas[1]: [
                receita[1],
                ebit[1],
                antes_imposto[1] * 0.34,
                antes_imposto[1],
                depreciacao[1],
                juros[1],
            ],
            datas[2]: [
                receita[2],
                ebit[2],
                antes_imposto[2] * 0.34,
                antes_imposto[2],
                depreciacao[2],
                juros[2],
            ],
            datas[3]: [
                receita[3],
                ebit[3],
                antes_imposto[3] * 0.34,
                antes_imposto[3],
                depreciacao[3],
                juros[3],
            ],
        },
        index=[
            "Total Revenue",
            "EBIT",
            "Tax Provision",
            "Pretax Income",
            "Depreciation And Amortization",
            "Interest Expense",
        ],
    )


def criar_balance() -> pd.DataFrame:
    """Balanco com divida bruta 500 -> 560 e caixa 200 -> 230."""
    datas = _datas([2021, 2022, 2023, 2024])
    return pd.DataFrame(
        {
            datas[0]: [100.0, 50.0, 20.0, 80.0, 30.0, 500.0, 200.0, 40.0],
            datas[1]: [110.0, 55.0, 22.0, 88.0, 33.0, 520.0, 210.0, 42.0],
            datas[2]: [121.0, 60.0, 24.0, 97.0, 36.0, 540.0, 220.0, 44.0],
            datas[3]: [133.0, 66.0, 26.0, 107.0, 40.0, 560.0, 230.0, 46.0],
        },
        index=[
            "Accounts Receivable",
            "Inventory",
            "Other Current Assets",
            "Accounts Payable",
            "Other Current Liabilities",
            "Total Debt",
            "Cash And Cash Equivalents",
            "Investments And Advances",
        ],
    )


def criar_cashflow() -> pd.DataFrame:
    """CAPEX de 5% da receita."""
    datas = _datas([2021, 2022, 2023, 2024])
    return pd.DataFrame(
        {
            datas[0]: [-50.0],
            datas[1]: [-55.0],
            datas[2]: [-60.5],
            datas[3]: [-66.55],
        },
        index=["Capital Expenditure"],
    )


def criar_snapshot(preco_final: float = 1.20) -> SnapshotFinanceiro:
    """Snapshot completo de uma empresa ficticia saudavel."""
    datas = pd.date_range(end=pd.Timestamp.today().normalize(), periods=250, freq="B")
    historico = pd.Series(
        [1.0 + (preco_final - 1.0) * i / (len(datas) - 1) for i in range(len(datas))],
        index=datas,
    )

    ano = pd.Timestamp.today().year
    dividendos = pd.Series(
        [0.40, 0.45, 0.50, 0.55],
        index=_datas([ano - 5, ano - 4, ano - 3, ano - 2]),
    )

    return SnapshotFinanceiro(
        ticker="TEST3.SA",
        as_of=date.today(),
        info={
            "marketCap": preco_final * 1000.0,
            "impliedSharesOutstanding": 1000.0,
            "payoutRatio": 0.5,
            "returnOnEquity": 0.15,
            "totalDebt": 560.0,
            "totalCash": 230.0,
        },
        financials=criar_financials(),
        balance=criar_balance(),
        cashflow=criar_cashflow(),
        history=historico,
        dividends=dividendos,
    )


__all__ = [
    "criar_balance",
    "criar_cashflow",
    "criar_financials",
    "criar_snapshot",
]
