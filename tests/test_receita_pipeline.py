"""Testes do painel analitico de receitas, sem rede."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from tests.fabricas import criar_snapshot
from valuation.pipeline.receita import atualizar_com_snapshots, montar_painel


def _receitas(anos: list[int], valores: list[float], ticker: str = "TEST3") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": [ticker] * len(anos),
            "ano": anos,
            "receita": valores,
            "ebit": [valor * 0.15 for valor in valores],
            "lucro_liquido": [valor * 0.08 for valor in valores],
            "ativo_total": [valor * 1.2 for valor in valores],
            "patrimonio_liquido": [valor * 0.6 for valor in valores],
            "origem": ["cvm"] * len(anos),
        }
    )


def _macro() -> pd.DataFrame:
    macro = pd.DataFrame(
        {
            "ipca": [0.05, 0.05, 0.05],
            "ibc_br": [100.0, 102.0, 104.0],
            "cambio": [5.0, 5.1, 5.2],
        },
        index=pd.Index([2022, 2023, 2024], name="ano"),
    )
    macro["d_ibc_br"] = [float("nan"), 0.0198, 0.0194]
    macro["d_cambio"] = [float("nan"), 0.0198, 0.0194]
    return macro


def _universo() -> pd.DataFrame:
    return pd.DataFrame({"acao": ["TEST3"], "setor": ["Materiais Basicos"]})


def test_montar_painel_deflaciona_e_calcula_crescimento() -> None:
    painel = montar_painel(
        _receitas([2022, 2023, 2024], [100.0, 110.0, 121.0]),
        _macro(),
        _universo(),
    )

    assert len(painel) == 3
    assert math.isnan(painel["g"].iloc[0])  # primeira observacao
    # Crescimento real: nominal de 10% contra IPCA de 5%.
    assert painel["g"].iloc[1] == pytest.approx(math.log(1.10 / 1.05))
    assert painel["g_ant"].iloc[2] == pytest.approx(painel["g"].iloc[1])
    assert painel["log_receita_lag"].iloc[1] == pytest.approx(
        math.log(painel["receita_real"].iloc[0])
    )
    assert painel["receita_real"].iloc[0] > painel["receita"].iloc[0]


def test_montar_painel_sem_macro_usa_preco_corrente() -> None:
    painel = montar_painel(
        _receitas([2022, 2023, 2024], [100.0, 110.0, 121.0]),
        pd.DataFrame(),
        _universo(),
    )

    assert (painel["fator_preco"] == 1.0).all()
    assert painel["g"].iloc[1] == pytest.approx(math.log(1.10))
    assert "d_ibc_br" in painel.columns
    assert painel["d_ibc_br"].isna().all()


def test_montar_painel_nao_trata_lacuna_como_um_ano() -> None:
    """Sem o ano intermediario, o diff nao pode virar crescimento de 1 ano."""
    painel = montar_painel(
        _receitas([2020, 2021, 2023], [100.0, 110.0, 133.1]),
        _macro(),
        _universo(),
    )
    linha = painel[painel["ano"] == 2023].iloc[0]

    assert math.isnan(linha["g"])
    assert math.isnan(linha["receita_real_lag"])


def test_atualizar_com_snapshots_antes_do_painel_gera_crescimento() -> None:
    """O ano do yfinance precisa entrar cru para ganhar receita real e g."""
    receitas = _receitas([2021, 2022, 2023], [1000.0, 1100.0, 1210.0])
    atualizado = atualizar_com_snapshots(receitas, {"TEST3": criar_snapshot()})

    assert 2024 in set(atualizado["ano"])
    assert atualizado.loc[atualizado["ano"] == 2024, "origem"].iloc[0] == "yfinance"

    painel = montar_painel(atualizado, pd.DataFrame(), _universo())
    linha = painel[painel["ano"] == 2024].iloc[0]
    assert math.isfinite(linha["g"])
    assert math.isfinite(linha["receita_real"])


def test_atualizar_com_snapshots_nao_duplica_ano_existente() -> None:
    receitas = _receitas([2021, 2022, 2023, 2024], [1000.0, 1100.0, 1210.0, 1331.0])
    atualizado = atualizar_com_snapshots(receitas, {"TEST3": criar_snapshot()})

    assert len(atualizado) == 4
    assert not (atualizado["origem"] == "yfinance").any()
