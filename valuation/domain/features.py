"""Features do painel de receita: colunas dos modelos e enriquecimento.

As colunas ficam neste modulo, e nao em ``previsao``, para que ``modelos_ml``
possa usa-las sem importar ``previsao`` -- o que criaria um ciclo, ja que
``previsao`` chama os modelos de machine learning.

As features extras (:data:`COLUNAS_EXTRA`) usam apenas informacao disponivel
ate ``t-1``: defasagens do crescimento, momento da margem, tamanho do ativo,
alavancagem, idade da serie, media e volatilidade historicas. Nenhuma delas
enxerga o ano-alvo, entao o backtest rolling-origin continua honesto.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

COLUNAS_FUNDAMENTOS = ("log_receita_lag", "margem_lag", "roa_lag", "giro_lag")
COLUNAS_MACRO = (
    "d_ibc_br",
    "ipca",
    "d_cambio",
    "ipca_exp",
    "pib_exp",
    "selic_exp",
    "d_cambio_exp",
)
COLUNAS_EXTRA = (
    "g_lag2",
    "margem_lag2",
    "log_ativo_lag",
    "alavancagem_lag",
    "idade_empresa",
    "crescimento_medio_3",
    "vol_crescimento",
    "d_margem",
)
COLUNAS_ML = (*COLUNAS_FUNDAMENTOS, *COLUNAS_MACRO, *COLUNAS_EXTRA)


def enriquecer(painel: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta as features extras ao painel, de forma idempotente.

    A funcao ordena por ``ticker``/``ano`` (o painel ja chega assim de
    :func:`valuation.pipeline.receita.montar_painel`, mas o backtest pode
    receber um recorte) e calcula tudo dentro do grupo da empresa, para que a
    primeira observacao de cada ticker nao herde o crescimento do anterior.
    """
    if set(COLUNAS_EXTRA).issubset(painel.columns):
        return painel

    dados = painel.sort_values(["ticker", "ano"], kind="stable").copy()
    grupo = dados.groupby("ticker", sort=False)

    dados["g_lag2"] = grupo["g"].shift(2)
    dados["margem_lag2"] = grupo["margem_lag"].shift(1)
    # Numero de exercicios ja observados da empresa: proxy de maturidade da
    # serie e do peso que o encolhimento vai dar a ela.
    dados["idade_empresa"] = grupo.cumcount().astype(float)

    ativo = dados.get("ativo_total_real_lag")
    if ativo is None:
        dados["log_ativo_lag"] = np.nan
        dados["alavancagem_lag"] = np.nan
    else:
        ativo_positivo = ativo.where(ativo > 0)
        dados["log_ativo_lag"] = np.log(ativo_positivo)
        patrimonio = dados.get("patrimonio_liquido_real_lag")
        dados["alavancagem_lag"] = patrimonio / ativo_positivo if patrimonio is not None else np.nan

    crescimento = dados.groupby("ticker", sort=False)["g"]
    dados["crescimento_medio_3"] = crescimento.transform(
        lambda serie: serie.shift(1).rolling(3, min_periods=1).mean()
    )
    dados["vol_crescimento"] = crescimento.transform(
        lambda serie: serie.shift(1).rolling(4, min_periods=2).std()
    )
    dados["d_margem"] = dados["margem_lag"] - dados["margem_lag2"]

    return dados


__all__ = [
    "COLUNAS_EXTRA",
    "COLUNAS_FUNDAMENTOS",
    "COLUNAS_MACRO",
    "COLUNAS_ML",
    "enriquecer",
]
