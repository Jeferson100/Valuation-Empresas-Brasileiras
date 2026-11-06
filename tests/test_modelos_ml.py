"""Testes dos modelos de machine learning e das features extras, sem rede."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from valuation.domain.features import COLUNAS_EXTRA, enriquecer
from valuation.domain.modelos_ml import (
    DEPENDENCIA,
    MODELOS_ML,
    OpcoesML,
    ajustar_e_prever,
    disponivel,
)
from valuation.domain.previsao import backtest, estimar_proximo_ano, resumir

RAPIDO = OpcoesML(n_estimadores=60, epocas=15)


def test_enriquecer_usa_apenas_informacao_passada() -> None:
    painel = _painel(empresas=4, anos=range(2010, 2017), ruido=0.02)
    dados = enriquecer(painel)
    firma = dados[dados["ticker"] == "T0"].sort_values("ano").reset_index(drop=True)

    assert firma["idade_empresa"].tolist() == [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert firma["g_lag2"].iloc[:2].isna().all()
    assert firma["g_lag2"].iloc[2] == pytest.approx(firma["g"].iloc[0])
    assert firma["crescimento_medio_3"].iloc[3] == pytest.approx(firma["g"].iloc[0:3].mean())
    assert firma["d_margem"].notna().sum() >= 5


def test_enriquecer_nao_usa_o_ano_alvo() -> None:
    """Mexer no crescimento do ultimo ano nao pode mudar as features dele."""
    painel = _painel(empresas=4, anos=range(2010, 2017), ruido=0.02)
    base = enriquecer(painel)

    alterado = painel.copy()
    ultimo = int(alterado["ano"].max())
    alterado.loc[alterado["ano"] == ultimo, "g"] *= 10.0
    novo = enriquecer(alterado)

    colunas = [*COLUNAS_EXTRA]
    pd.testing.assert_frame_equal(
        base.loc[base["ano"] == ultimo, colunas].reset_index(drop=True),
        novo.loc[novo["ano"] == ultimo, colunas].reset_index(drop=True),
    )


def test_enriquecer_e_idempotente() -> None:
    painel = _painel(empresas=3, anos=range(2010, 2016), ruido=0.01)
    uma_vez = enriquecer(painel)
    duas_vezes = enriquecer(uma_vez)
    pd.testing.assert_frame_equal(uma_vez, duas_vezes)


def test_modelo_desconhecido_levanta_erro() -> None:
    painel = _painel(empresas=10, anos=range(2010, 2016))
    with pytest.raises(ValueError):
        ajustar_e_prever("nao_existe", painel, painel)


def test_disponivel_reflete_instalacao() -> None:
    pytest.importorskip("xgboost")
    assert disponivel("nao_existe") is False
    assert disponivel("xgboost") is True


@pytest.mark.parametrize("nome", MODELOS_ML)
def test_modelos_prevem_com_tamanho_correto(nome: str) -> None:
    pytest.importorskip(DEPENDENCIA[nome])
    painel = _painel(empresas=40, anos=range(2010, 2020), ruido=0.05)
    treino = painel[painel["ano"] < 2019]
    teste = painel[painel["ano"] == 2019]

    previsao = ajustar_e_prever(nome, treino, teste, RAPIDO)

    assert previsao.shape == (len(teste),)
    assert np.isfinite(previsao).all()


def test_previsao_e_deterministica() -> None:
    pytest.importorskip("xgboost")
    painel = _painel(empresas=30, anos=range(2010, 2019), ruido=0.05)
    treino = painel[painel["ano"] < 2018]
    teste = painel[painel["ano"] == 2018]

    primeira = ajustar_e_prever("xgboost", treino, teste, RAPIDO)
    segunda = ajustar_e_prever("xgboost", treino, teste, RAPIDO)

    np.testing.assert_allclose(primeira, segunda)


@pytest.mark.parametrize("nome", ["lstm", "gru"])
def test_rede_preserva_a_ordem_das_linhas(nome: str) -> None:
    """A previsao de cada ticker nao pode depender da ordem do DataFrame."""
    pytest.importorskip("torch")
    painel = _painel(empresas=12, anos=range(2010, 2016), ruido=0.05)
    treino = painel[painel["ano"] < 2015]
    teste = painel[painel["ano"] == 2015]

    normal = ajustar_e_prever(nome, treino, teste, RAPIDO)
    invertida = ajustar_e_prever(nome, treino, teste.iloc[::-1], RAPIDO)

    np.testing.assert_allclose(normal, invertida[::-1], rtol=1e-6, atol=1e-6)


def test_backtest_ignora_modelo_indisponivel() -> None:
    painel = _painel(empresas=20, anos=range(2010, 2016), ruido=0.02)
    historico = backtest(
        painel,
        anos_minimo=2013,
        minimo_treino=40,
        modelos_ml=("nao_existe",),
    )
    assert set(historico["modelo"]) == {"fundamentos", "macro", "AR", "setor"}


def test_backtest_inclui_modelos_ml() -> None:
    pytest.importorskip("xgboost")
    painel = _painel(empresas=30, anos=range(2010, 2017), ruido=0.02)
    historico = backtest(
        painel,
        anos_minimo=2013,
        minimo_treino=40,
        modelos_ml=("xgboost",),
        opcoes_ml=RAPIDO,
    )
    assert "xgboost" in set(historico["modelo"])


def test_ml_bate_ar_quando_relacao_e_nao_linear() -> None:
    """O sinal e um degrau na margem: o OLS linear nao alcanca, a arvore sim."""
    pytest.importorskip("xgboost")
    painel = _painel(empresas=60, anos=range(2010, 2019), ruido=0.08)
    historico = backtest(
        painel,
        anos_minimo=2013,
        minimo_treino=40,
        modelos_ml=("xgboost",),
        opcoes_ml=OpcoesML(n_estimadores=120),
    )
    mape = resumir(historico).set_index("modelo")["mape"]

    assert mape["xgboost"] < 0.9 * mape["AR"]


def test_estimar_proximo_ano_com_modelo_ml() -> None:
    pytest.importorskip("xgboost")
    painel = _painel(empresas=30, anos=range(2010, 2019), ruido=0.05)
    projecao = estimar_proximo_ano(
        painel,
        {"Setor A": "xgboost", "Setor B": "xgboost"},
        g_perpetuidade=0.03,
        inflacao_esperada=0.04,
        anos=5,
        modelos_ml=("xgboost",),
        opcoes_ml=RAPIDO,
    )

    assert (projecao["modelo_receita"] == "xgboost").all()
    assert np.isfinite(projecao["g_modelo_real"]).all()
    assert (projecao["crescimento_por_ano"].map(len) == 5).all()


def _painel(
    empresas: int = 40,
    anos: range = range(2010, 2020),
    ruido: float = 0.01,
) -> pd.DataFrame:
    """Painel sintetico com relacao nao linear entre margem e crescimento."""
    rng = np.random.default_rng(3)
    linhas = []
    for empresa in range(empresas):
        setor = "Setor A" if empresa % 2 else "Setor B"
        margem = float(rng.uniform(0.0, 0.30))
        receita = 100.0 * (1 + empresa % 5)
        crescimento_anterior = 0.0
        for ano in anos:
            if margem > 0.15:
                degrau = 0.25
            elif margem < 0.05:
                degrau = -0.15
            else:
                degrau = 0.0
            g = 0.02 + degrau + float(rng.normal(0.0, ruido))
            receita_nova = receita * float(np.exp(g))
            linhas.append(
                {
                    "ticker": f"T{empresa}",
                    "setor": setor,
                    "ano": ano,
                    "receita_real": receita_nova,
                    "receita_real_lag": receita,
                    "ativo_total_real_lag": receita * 2.0,
                    "patrimonio_liquido_real_lag": receita * 0.8,
                    "g": g,
                    "g_ant": crescimento_anterior,
                    "log_receita_lag": float(np.log(receita)),
                    "margem_lag": margem,
                    "roa_lag": 0.05 + 0.01 * margem,
                    "giro_lag": 0.8 + margem,
                    "d_ibc_br": 0.02,
                    "ipca": 0.04,
                    "d_cambio": 0.0,
                    "ipca_exp": 0.04,
                    "pib_exp": 0.02,
                    "selic_exp": 0.11,
                    "d_cambio_exp": 0.0,
                }
            )
            receita = receita_nova
            crescimento_anterior = g
    return pd.DataFrame(linhas)
