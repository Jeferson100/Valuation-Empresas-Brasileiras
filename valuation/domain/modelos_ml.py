"""Modelos de machine learning para a previsao de crescimento da receita.

Todos seguem o mesmo contrato dos modelos de :mod:`valuation.domain.previsao`:
recebem o painel de treino (ano < alvo) e o de teste (ano alvo) e devolvem o
vetor de crescimento previsto, em log. A comparacao com o OLS e de "solucao
completa": o ML pode usar features extras (:data:`COLUNAS_EXTRA`) alem das
variaveis dos modelos A/B, e o setor entra como categorica.

As bibliotecas pesadas sao importadas sob demanda. Sem ``xgboost``,
``lightgbm``, ``catboost`` ou ``torch`` instalados, o modelo correspondente e
apenas ignorado (com aviso no log) e o pipeline continua rodando com o OLS,
o AR e a mediana setorial.

Hiperparametros foram fixados de forma conservadora -- poucas arvores, pouca
profundidade e regularizacao -- porque o painel tem ~2 mil linhas e ~150
empresas: qualquer coisa maior decora os anos de treino.
"""

from __future__ import annotations

import importlib.util
import logging
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .features import COLUNAS_ML

log = logging.getLogger(__name__)

MODELOS_ML = ("xgboost", "lightgbm", "catboost", "mlp", "lstm", "gru")
DEPENDENCIA = {
    "xgboost": "xgboost",
    "lightgbm": "lightgbm",
    "catboost": "catboost",
    "mlp": "sklearn",
    "lstm": "torch",
    "gru": "torch",
}
MINIMO_LINHAS = 40


@dataclass(frozen=True)
class OpcoesML:
    """Hiperparametros comuns; os modelos usam apenas os que lhes cabem."""

    semente: int = 7
    n_estimadores: int = 300
    profundidade: int = 3
    taxa: float = 0.05
    janela: int = 3
    epocas: int = 80


def disponivel(nome: str) -> bool:
    """Diz se a biblioteca necessaria para o modelo esta instalada."""
    modulo = DEPENDENCIA.get(nome)
    if modulo is None:
        return False
    return importlib.util.find_spec(modulo) is not None


def ajustar_e_prever(
    nome: str,
    treino: pd.DataFrame,
    teste: pd.DataFrame,
    opcoes: OpcoesML | None = None,
) -> np.ndarray:
    """Ajusta o modelo no treino e devolve a previsao para as linhas do teste.

    Levanta ``ValueError`` para nome desconhecido e ``ImportError`` quando a
    biblioteca nao esta instalada; quem chama decide se ignora o modelo.
    """
    funcao = _FUNCOES.get(nome)
    if funcao is None:
        raise ValueError(f"modelo de ML desconhecido: {nome}")
    if not disponivel(nome):
        raise ImportError(f"biblioteca de {nome} nao instalada ({DEPENDENCIA[nome]})")
    if len(treino) < MINIMO_LINHAS:
        raise ValueError(f"amostra insuficiente para {nome}: {len(treino)} linhas")
    if teste.empty:
        return np.empty(0, dtype=float)

    previsao = funcao(treino, teste, opcoes or OpcoesML())
    return np.asarray(previsao, dtype=float)


def _matrizes(treino: pd.DataFrame, teste: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Features numericas, descartando colunas vazias no treino.

    Colunas sem nenhum valor no treino (por exemplo as expectativas do Focus
    quando a API do BCB falha) nao podem ser usadas: entram como NaN e so
    atrapalham a arvore. O descarte e feito no treino e repetido no teste para
    manter as duas matrizes alinhadas.
    """
    colunas = [coluna for coluna in COLUNAS_ML if coluna in treino.columns]
    xtreino = treino.reindex(columns=colunas).astype(float)
    xteste = teste.reindex(columns=colunas).astype(float)
    manter = [coluna for coluna in colunas if xtreino[coluna].notna().any()]
    return xtreino[manter], xteste[manter]


def _setor(serie: pd.Series, categorias: list[str]) -> pd.Series:
    """Converte o setor em categorica, com um nivel proprio para ausente."""
    limpo = serie.astype(str).where(serie.notna(), "desconhecido")
    return pd.Series(pd.Categorical(limpo, categories=categorias), index=serie.index)


def _com_setor(treino: pd.DataFrame, teste: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Matrizes numericas + setor categorico para os modelos de arvore."""
    xtreino, xteste = _matrizes(treino, teste)
    categorias = sorted({*treino["setor"].dropna().astype(str), "desconhecido"})
    xtreino["setor"] = _setor(treino["setor"], categorias)
    xteste["setor"] = _setor(teste["setor"], categorias)
    return xtreino, xteste


def _prever_xgboost(treino: pd.DataFrame, teste: pd.DataFrame, opcoes: OpcoesML) -> np.ndarray:
    from xgboost import XGBRegressor

    xtreino, xteste = _com_setor(treino, teste)
    modelo = XGBRegressor(
        n_estimators=opcoes.n_estimadores,
        max_depth=opcoes.profundidade,
        learning_rate=opcoes.taxa,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5.0,
        reg_lambda=1.0,
        random_state=opcoes.semente,
        n_jobs=1,
        tree_method="hist",
        enable_categorical=True,
        verbosity=0,
    )
    modelo.fit(xtreino, treino["g"].to_numpy(float))
    return np.asarray(modelo.predict(xteste), dtype=float)


def _prever_lightgbm(treino: pd.DataFrame, teste: pd.DataFrame, opcoes: OpcoesML) -> np.ndarray:
    from lightgbm import LGBMRegressor

    xtreino, xteste = _com_setor(treino, teste)
    modelo = LGBMRegressor(
        n_estimators=opcoes.n_estimadores,
        max_depth=opcoes.profundidade,
        num_leaves=min(2**opcoes.profundidade, 8),
        learning_rate=opcoes.taxa,
        min_child_samples=20,
        subsample=0.8,
        subsample_freq=1,
        colsample_bytree=0.8,
        reg_lambda=1.0,
        random_state=opcoes.semente,
        n_jobs=1,
        deterministic=True,
        force_row_wise=True,
        verbose=-1,
    )
    modelo.fit(
        xtreino,
        treino["g"].to_numpy(float),
        categorical_feature=["setor"],
    )
    return np.asarray(modelo.predict(xteste), dtype=float)


def _prever_catboost(treino: pd.DataFrame, teste: pd.DataFrame, opcoes: OpcoesML) -> np.ndarray:
    from catboost import CatBoostRegressor

    xtreino, xteste = _matrizes(treino, teste)
    xtreino["setor"] = treino["setor"].fillna("desconhecido").astype(str).to_numpy()
    xteste["setor"] = teste["setor"].fillna("desconhecido").astype(str).to_numpy()
    modelo = CatBoostRegressor(
        iterations=opcoes.n_estimadores,
        depth=opcoes.profundidade,
        learning_rate=opcoes.taxa,
        l2_leaf_reg=3.0,
        random_seed=opcoes.semente,
        thread_count=1,
        verbose=0,
        allow_writing_files=False,
        cat_features=["setor"],
        # Setor tem poucas categorias: one-hot e muito mais rapido que o
        # target encoding (CTR) que o CatBoost usaria por padrao.
        one_hot_max_size=32,
        boosting_type="Plain",
        max_ctr_complexity=1,
    )
    modelo.fit(xtreino, treino["g"].to_numpy(float))
    return np.asarray(modelo.predict(xteste), dtype=float)


def _prever_mlp(treino: pd.DataFrame, teste: pd.DataFrame, opcoes: OpcoesML) -> np.ndarray:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    xtreino, xteste = _matrizes(treino, teste)
    numericas = list(xtreino.columns)
    xtreino["setor"] = treino["setor"].fillna("desconhecido").astype(str).to_numpy()
    xteste["setor"] = teste["setor"].fillna("desconhecido").astype(str).to_numpy()

    preparo = ColumnTransformer(
        [
            (
                "numericas",
                Pipeline(
                    [
                        ("imputar", SimpleImputer(strategy="median")),
                        ("escala", StandardScaler()),
                    ]
                ),
                numericas,
            ),
            ("setor", OneHotEncoder(handle_unknown="ignore"), ["setor"]),
        ]
    )
    modelo = Pipeline(
        [
            ("preparo", preparo),
            (
                "rede",
                MLPRegressor(
                    hidden_layer_sizes=(32, 16),
                    alpha=1e-3,
                    learning_rate_init=1e-3,
                    max_iter=600,
                    early_stopping=False,
                    random_state=opcoes.semente,
                ),
            ),
        ]
    )
    modelo.fit(xtreino, treino["g"].to_numpy(float))
    return np.asarray(modelo.predict(xteste), dtype=float)


def _sequencias(
    dados: pd.DataFrame, colunas: list[str], janela: int
) -> tuple[np.ndarray, np.ndarray]:
    """Monta janelas deslizantes por empresa.

    ``dados`` precisa estar ordenado por ``ticker``/``ano``. A posicao de cada
    linha dentro da empresa (``cumcount``) define quantas linhas anteriores
    existem; quando faltam anos, a primeira observacao e repetida.
    """
    valores = dados[colunas].to_numpy(float)
    alvo = dados["g"].to_numpy(float)
    posicao = dados.groupby("ticker", sort=False).cumcount().to_numpy()
    total, features = valores.shape
    janelas = np.zeros((total, janela, features), dtype=float)

    for indice in range(total):
        inicio = indice - min(int(posicao[indice]), janela - 1)
        bloco = valores[inicio : indice + 1]
        if len(bloco) < janela:
            repeticao = np.repeat(bloco[:1], janela - len(bloco), axis=0)
            bloco = np.vstack([repeticao, bloco])
        janelas[indice] = bloco

    return janelas, alvo


def _prever_rede(
    treino: pd.DataFrame, teste: pd.DataFrame, opcoes: OpcoesML, tipo: str
) -> np.ndarray:
    import torch
    from torch import nn

    treino = treino.reset_index(drop=True)
    teste = teste.reset_index(drop=True)
    xtreino, xteste = _matrizes(treino, teste)
    if xtreino.shape[1] == 0:
        raise ValueError("sem features numericas para a rede recorrente")

    # Imputacao e escala ajustadas so no treino; o teste usa as mesmas.
    mediana = xtreino.median()
    desvio = xtreino.std().replace(0.0, 1.0).fillna(1.0)
    xtreino = (xtreino.fillna(mediana) - mediana) / desvio
    xteste = (xteste.fillna(mediana) - mediana) / desvio

    # A rede precisa da historia da empresa; o teste e anexado ao treino para
    # que a primeira linha do ano-alvo enxergue os anos anteriores.
    treino_ordenado = treino.sort_values(["ticker", "ano"], kind="stable").copy()
    treino_ordenado["_origem"] = 0
    treino_ordenado["_ordem"] = -1
    teste_ordenado = teste.copy()
    teste_ordenado["_origem"] = 1
    # A ordem de saida e a ordem de entrada; o embaralhamento so acontece na
    # ordenacao por ticker/ano usada para montar as sequencias.
    teste_ordenado["_ordem"] = np.arange(len(teste_ordenado))
    teste_ordenado = teste_ordenado.sort_values(["ticker", "ano"], kind="stable")

    treino_ordenado[list(xtreino.columns)] = xtreino.loc[treino_ordenado.index].to_numpy()
    teste_ordenado[list(xteste.columns)] = xteste.loc[teste_ordenado.index].to_numpy()

    juntos = (
        pd.concat([treino_ordenado, teste_ordenado], ignore_index=True)
        .sort_values(["ticker", "ano"], kind="stable")
        .reset_index(drop=True)
    )
    janelas, alvo = _sequencias(juntos, list(xtreino.columns), opcoes.janela)

    mascara_treino = (juntos["_origem"] == 0).to_numpy() & np.isfinite(alvo)
    mascara_teste = juntos["_origem"] == 1
    if mascara_treino.sum() < MINIMO_LINHAS or not mascara_teste.any():
        raise ValueError("sequencias insuficientes para a rede recorrente")

    torch.manual_seed(opcoes.semente)
    gerador = torch.Generator().manual_seed(opcoes.semente)
    recorrente = nn.LSTM if tipo == "lstm" else nn.GRU
    # Uma thread: os tensores sao pequenos e o overhead de sincronizacao do
    # torch domina. Tambem deixa o treino reproduzivel entre maquinas.
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        modelo = recorrente(input_size=xtreino.shape[1], hidden_size=16, batch_first=True)
        saida = nn.Linear(16, 1)
        otimizador = torch.optim.Adam(
            [*modelo.parameters(), *saida.parameters()], lr=0.01, weight_decay=1e-4
        )
        perda = nn.MSELoss()

        x_treino = torch.tensor(janelas[mascara_treino], dtype=torch.float32)
        y_treino = torch.tensor(alvo[mascara_treino], dtype=torch.float32).unsqueeze(1)
        total = len(x_treino)

        for _ in range(opcoes.epocas):
            modelo.train()
            saida.train()
            ordem = torch.randperm(total, generator=gerador)
            for inicio in range(0, total, 256):
                lote = ordem[inicio : inicio + 256]
                otimizador.zero_grad()
                oculto = modelo(x_treino[lote])[0]
                erro = perda(saida(oculto[:, -1]), y_treino[lote])
                erro.backward()
                otimizador.step()

        modelo.eval()
        saida.eval()
        with torch.no_grad():
            oculto = modelo(torch.tensor(janelas[mascara_teste], dtype=torch.float32))[0]
            previsao = saida(oculto[:, -1]).squeeze(1).numpy()
    finally:
        torch.set_num_threads(threads)

    resultado = np.full(len(teste), np.nan, dtype=float)
    resultado[juntos.loc[mascara_teste, "_ordem"].to_numpy(int)] = previsao
    return resultado


_FUNCOES: dict[str, Callable[[pd.DataFrame, pd.DataFrame, OpcoesML], np.ndarray]] = {
    "xgboost": _prever_xgboost,
    "lightgbm": _prever_lightgbm,
    "catboost": _prever_catboost,
    "mlp": _prever_mlp,
    "lstm": lambda treino, teste, opcoes: _prever_rede(treino, teste, opcoes, "lstm"),
    "gru": lambda treino, teste, opcoes: _prever_rede(treino, teste, opcoes, "gru"),
}


__all__ = [
    "DEPENDENCIA",
    "MODELOS_ML",
    "OpcoesML",
    "ajustar_e_prever",
    "disponivel",
]
