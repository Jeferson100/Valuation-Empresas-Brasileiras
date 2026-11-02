"""Utilitarios de series temporais e acesso defensivo a demonstracoes.

Concentra o que antes estava repetido em ~200 linhas de ``if isinstance(...):
df.loc[...][0]`` espalhadas por cinco modulos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def anos_do_indice(indice: pd.Index) -> pd.Index:
    """Extrai o ano de um ``DatetimeIndex`` ou repassa um indice inteiro."""
    if isinstance(indice, pd.DatetimeIndex):
        return pd.Index(indice.year)
    return pd.Index(indice).astype(int)


def indice_ipca_anual(ipca_mensal: pd.Series) -> pd.Series:
    """Converte IPCA mensal (em %) em indice acumulado anual com base 1."""
    fator = 1.0 + pd.to_numeric(ipca_mensal, errors="coerce").dropna() / 100.0
    anos = anos_do_indice(fator.index)
    anual = fator.groupby(anos).prod()
    return anual.cumprod()


def deflacionar(receita: pd.Series, indice: pd.Series) -> pd.Series:
    """Deflaciona dividindo pelo indice de precos.

    O codigo anterior multiplicava a receita pelo fator acumulado, o que inflava
    a serie em vez de traze-la a precos constantes.
    """
    if receita.empty or indice.empty:
        return receita.copy()

    anos = anos_do_indice(receita.index)
    fator = indice.reindex(anos).ffill().bfill()
    if fator.isna().any():
        return receita.copy()

    return receita / fator.to_numpy(dtype=float)


def crescimento_log(
    receita: pd.Series,
    clip: tuple[float, float] = (-0.10, 0.20),
) -> float:
    """Crescimento geometrico medio, com corte de prudencia."""
    serie = pd.to_numeric(receita, errors="coerce").dropna()
    serie = serie[serie > 0]
    if len(serie) < 3:
        return 0.0
    crescimento = float(np.exp(np.log(serie.iloc[-1] / serie.iloc[0]) / (len(serie) - 1)) - 1.0)
    return float(np.clip(crescimento, *clip))


def linha(df: pd.DataFrame | None, *nomes: str, padrao: float = float("nan")) -> float:
    """Retorna o campo mais recente existente e finito, com fallback.

    A coluna e escolhida pela data, nao pela posicao: o yfinance devolve as
    colunas em ordem decrescente, mas isso nao e garantido.
    """
    if df is None or df.empty:
        return padrao
    for nome in nomes:
        if nome in df.index:
            valores = df.loc[nome]
            if isinstance(valores, pd.DataFrame):
                valores = valores.iloc[:, 0]
            if isinstance(valores.index, pd.DatetimeIndex):
                valores = valores.sort_index()
            for candidato in reversed(valores.to_numpy().tolist()):
                try:
                    numero = float(candidato)
                except (TypeError, ValueError):
                    continue
                if np.isfinite(numero):
                    return numero
    return padrao


def serie(df: pd.DataFrame | None, *nomes: str) -> pd.Series:
    """Retorna a primeira serie temporal existente, como float."""
    if df is None or df.empty:
        return pd.Series(dtype=float)
    for nome in nomes:
        if nome in df.index:
            valores = df.loc[nome]
            if isinstance(valores, pd.DataFrame):
                valores = valores.iloc[:, 0]
            return pd.to_numeric(valores, errors="coerce").dropna()
    return pd.Series(dtype=float)


def mediana_robusta(
    valores: pd.Series,
    padrao: float,
    minimo: int = 2,
    clip: tuple[float, float] | None = None,
) -> float:
    """Mediana com numero minimo de observacoes, corte e fallback."""
    limpos = pd.to_numeric(valores, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(limpos) < minimo:
        return padrao
    resultado = float(limpos.median())
    if clip is not None:
        resultado = float(np.clip(resultado, *clip))
    return resultado


def razao(serie_a: pd.Series, serie_b: pd.Series) -> pd.Series:
    """Divisao alinhada por indice, descartando infinitos."""
    a, b = serie_a.align(serie_b, join="inner")
    b = b.replace(0.0, np.nan)
    return (a / b).replace([np.inf, -np.inf], np.nan).dropna()


__all__ = [
    "anos_do_indice",
    "crescimento_log",
    "deflacionar",
    "indice_ipca_anual",
    "linha",
    "mediana_robusta",
    "razao",
    "serie",
]
