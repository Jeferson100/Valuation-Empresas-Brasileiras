"""Testes da matematica de previsao de receita, sem rede e sem disco."""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from valuation.domain.previsao import (
    ajustar_fundamentos,
    ajustar_macro,
    amortecer,
    backtest,
    encolher,
    estimar_proximo_ano,
    projetar,
    resumir,
    selecionar_por_setor,
)


def test_encolher_peso_empirical_bayes() -> None:
    g, peso = encolher(0.10, 4, 0.05, k=3.0)
    assert peso == pytest.approx(4 / 7)
    assert g == pytest.approx(0.10 * 4 / 7 + 0.05 * 3 / 7)


def test_encolher_sem_serie_usa_setor() -> None:
    g, peso = encolher(float("nan"), 0, 0.05)
    assert g == pytest.approx(0.05)
    assert peso == 0.0


def test_amortecer_converge_para_perpetuidade() -> None:
    serie = amortecer(0.15, 0.03, anos=5, phi=0.85)
    assert len(serie) == 5
    assert serie[0] == pytest.approx(0.15)
    assert serie[-1] == pytest.approx(0.03 + 0.12 * 0.85**4)
    assert all(a > b for a, b in itertools.pairwise(serie))


def test_amortecer_na_perpetuidade_fica_constante() -> None:
    serie = amortecer(0.03, 0.03, anos=3)
    assert serie == pytest.approx((0.03, 0.03, 0.03))


def test_projetar_compoe_em_cascata() -> None:
    valores = projetar(100.0, (0.10, 0.05))
    assert valores == pytest.approx((110.0, 115.5))


def test_fundamentos_recupera_coeficiente_com_efeito_de_ano() -> None:
    """Regressao: sem intercepto, o ano de referencia contaminava os betas.

    O painel e balanceado e a margem e sorteada independente do ano. O unico
    efeito de ano nao nulo cai justamente no ano de referencia (2010), que o
    ``drop_first`` deixa de fora: sem uma coluna constante esse efeito vaza
    para as features e enviesa o coeficiente da margem.
    """
    rng = np.random.default_rng(5)
    linhas = []
    for empresa in range(40):
        for ano in range(2010, 2020):
            margem = float(rng.uniform(0.02, 0.20))
            efeito_ano = 0.08 if ano == 2010 else 0.0
            linhas.append(
                {
                    "ticker": f"T{empresa}",
                    "setor": "Setor A" if empresa % 2 else "Setor B",
                    "ano": ano,
                    "receita_real": 100.0,
                    "receita_real_lag": 100.0,
                    "g": 0.02 + 0.5 * margem + efeito_ano,
                    "g_ant": 0.0,
                    "log_receita_lag": float(rng.normal(0.0, 1.0)),
                    "margem_lag": margem,
                    "roa_lag": float(rng.normal(0.05, 0.02)),
                    "giro_lag": float(rng.normal(1.0, 0.2)),
                    "d_ibc_br": 0.0,
                    "ipca": 0.0,
                    "d_cambio": 0.0,
                }
            )

    modelo = ajustar_fundamentos(pd.DataFrame(linhas))
    posicao = modelo.colunas.index("margem_lag")

    assert "_const" in modelo.colunas
    assert modelo.beta[posicao] == pytest.approx(0.5, abs=0.02)


def test_macro_recupera_coeficientes() -> None:
    rng = np.random.default_rng(7)
    anos = np.arange(2010, 2021)
    macro = pd.DataFrame(
        {
            "d_ibc_br": rng.normal(0.02, 0.01, len(anos)),
            "ipca": rng.normal(0.04, 0.005, len(anos)),
            "d_cambio": rng.normal(0.0, 0.03, len(anos)),
        },
        index=anos,
    )

    linhas = []
    for empresa in range(40):
        alfa = rng.normal(0.0, 0.01)
        for ano in anos:
            x = macro.loc[ano]
            g = alfa + 0.8 * x["d_ibc_br"] - 0.5 * x["ipca"] + rng.normal(0, 1e-4)
            linhas.append({"ticker": f"E{empresa}", "ano": ano, "g": g, **x.to_dict()})

    modelo = ajustar_macro(pd.DataFrame(linhas))
    assert modelo.beta[0] == pytest.approx(0.8, abs=0.02)
    assert modelo.beta[1] == pytest.approx(-0.5, abs=0.05)
    assert modelo.beta[2] == pytest.approx(0.0, abs=0.05)
    assert modelo.r2 > 0.9


def test_backtest_respeita_origem_minima() -> None:
    painel = _painel_sintetico(anos=range(2010, 2021))
    historico = backtest(painel, anos_minimo=2015, minimo_treino=40)
    assert historico["ano"].min() >= 2015
    assert set(historico["modelo"]) == {"fundamentos", "macro", "AR", "setor"}


def test_backtest_clipa_crescimento_extremo() -> None:
    painel = _painel_sintetico(anos=range(2010, 2021))
    painel.loc[painel["ano"] == 2020, "g_ant"] = 5.0
    historico = backtest(painel, anos_minimo=2015, minimo_treino=40)
    ar = historico[(historico["ano"] == 2020) & (historico["modelo"] == "AR")]
    assert not ar.empty
    assert ar["g_previsto"].max() <= 0.35


def test_selecionar_mantem_ar_quando_ganho_e_ruido() -> None:
    historico = _historico_falso({"AR": 0.10, "fundamentos": 0.099})
    escolha = selecionar_por_setor(historico, margem=0.01)
    assert escolha["Setor A"] == "AR"


def test_selecionar_troca_quando_ganho_e_relevante() -> None:
    historico = _historico_falso({"AR": 0.12, "fundamentos": 0.08})
    escolha = selecionar_por_setor(historico, margem=0.01)
    assert escolha["Setor A"] == "fundamentos"


def test_estimar_proximo_ano_converte_para_nominal() -> None:
    painel = _painel_sintetico(anos=range(2010, 2021), g_setor=0.05)
    projecao = estimar_proximo_ano(
        painel,
        {"Setor A": "AR", "Setor B": "AR"},
        g_perpetuidade=0.03,
        inflacao_esperada=0.04,
        anos=5,
        phi=0.85,
        k=3.0,
    )
    assert len(projecao) == painel["ticker"].nunique()
    assert (projecao["crescimento_por_ano"].map(len) == 5).all()

    # O crescimento converge: o ultimo ano esta mais perto da perpetuidade
    # nominal do que o primeiro.
    primeiro = projecao["crescimento_por_ano"].map(lambda serie: serie[0])
    ultimo = projecao["crescimento_por_ano"].map(lambda serie: serie[-1])
    assert (ultimo < primeiro).all()
    assert (ultimo - 0.03).abs().max() < (primeiro - 0.03).abs().max()

    # Horizonte longo: o ultimo ano encontra a perpetuidade nominal de 3%.
    longo = estimar_proximo_ano(
        painel,
        {"Setor A": "AR", "Setor B": "AR"},
        g_perpetuidade=0.03,
        inflacao_esperada=0.04,
        anos=60,
        phi=0.85,
        k=3.0,
    )
    final = longo["crescimento_por_ano"].map(lambda serie: serie[-1])
    assert (final - 0.03).abs().max() < 0.005


def test_estimar_proximo_ano_ignora_ano_sem_receita() -> None:
    """Holdings com receita zero na DRE usam o ultimo ano com receita > 0."""
    painel = _painel_sintetico(anos=range(2010, 2021))
    ultimo = painel[painel["ticker"] == "A0"].sort_values("ano").tail(1).copy()
    ultimo["ano"] = 2021
    ultimo["receita_real"] = 0.0
    ultimo["g"] = float("nan")
    painel = pd.concat([painel, ultimo], ignore_index=True)

    projecao = estimar_proximo_ano(
        painel,
        {"Setor A": "AR", "Setor B": "AR"},
        g_perpetuidade=0.03,
        inflacao_esperada=0.04,
        anos=5,
        phi=0.85,
        k=3.0,
    )
    linha = projecao[projecao["ticker"] == "A0"].iloc[0]

    assert linha["ano_base"] == 2020


def test_receita_projetada_1_desfaz_o_deflator() -> None:
    """A coluna informativa sai em reais correntes, como o crescimento nominal."""
    painel = _painel_sintetico(anos=range(2010, 2021))
    painel["fator_preco"] = 2.0
    projecao = estimar_proximo_ano(
        painel,
        {"Setor A": "AR", "Setor B": "AR"},
        g_perpetuidade=0.03,
        inflacao_esperada=0.04,
        anos=5,
        phi=0.85,
        k=3.0,
    )
    ultimo = painel.sort_values("ano").groupby("ticker", sort=False).tail(1)
    base = ultimo.set_index("ticker")["receita_real"] / 2.0

    for linha in projecao.itertuples(index=False):
        esperado = base[linha.ticker] * (1.0 + linha.crescimento_receita_ajustado)
        assert linha.receita_projetada_1 == pytest.approx(esperado)


def test_resumir_ordena_por_mape() -> None:
    historico = _historico_falso({"AR": 0.12, "fundamentos": 0.08})
    resumo = resumir(historico)
    assert resumo.iloc[0]["modelo"] == "fundamentos"


def _painel_sintetico(
    anos: range,
    g_setor: float = 0.05,
    empresas_por_setor: int = 20,
) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    linhas = []
    for setor in ("Setor A", "Setor B"):
        for empresa in range(empresas_por_setor):
            ticker = f"{setor[-1]}{empresa}"
            receita = 100.0
            for ano in anos:
                g = g_setor + rng.normal(0, 0.01)
                linhas.append(
                    {
                        "ticker": ticker,
                        "setor": setor,
                        "ano": ano,
                        "receita_real": receita,
                        "receita_real_lag": receita / (1 + g),
                        "g": g,
                        "g_ant": g,
                        "log_receita_lag": np.log(receita / (1 + g)),
                        "margem_lag": 0.10 + 0.01 * empresa,
                        "roa_lag": 0.05 + 0.001 * empresa,
                        "giro_lag": 0.8 + 0.01 * empresa,
                        "d_ibc_br": 0.02,
                        "ipca": 0.04,
                        "d_cambio": 0.0,
                    }
                )
                receita *= 1 + g
    return pd.DataFrame(linhas)


def _historico_falso(erros: dict[str, float]) -> pd.DataFrame:
    linhas = []
    for modelo, erro in erros.items():
        for _ in range(30):
            linhas.append(
                {
                    "setor": "Setor A",
                    "modelo": modelo,
                    "erro_rel": erro,
                    "erro_g": 0.0,
                    "acerto_sinal": True,
                }
            )
    return pd.DataFrame(linhas)
