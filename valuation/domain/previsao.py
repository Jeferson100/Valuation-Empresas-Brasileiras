"""Previsao de receita com variaveis independentes (painel empresa-ano).

Modelo A (fundamentos) explora a variacao ENTRE empresas:
    g_it = a + b1*log(receita)_{i,t-1} + b2*margem_ebit_{i,t-1}
              + b3*ROA_{i,t-1} + b4*giro_{i,t-1}
              + efeito_fixo_ano + efeito_fixo_setor + erro

Modelo B (macro) explora a variacao NO TEMPO:
    g_it = alpha_i + b1*Dlog(IBC-Br)_t + b2*IPCA_t + b3*Dlog(cambio)_t
           + b4*ipca_exp_t + b5*pib_exp_t + b6*selic_exp_t + b7*d_cambio_exp_t + erro

As variaveis com sufixo _exp sao expectativas do Boletim Focus (SGS), usadas como
variaveis independentes ex-ante para o ano alvo.

Baselines: AR (repete o ultimo crescimento) e mediana setorial.

Modelos de machine learning (XGBoost, LightGBM, CatBoost, MLP e redes
recorrentes) entram como candidatos opcionais no mesmo backtest, com features
extras; veja :mod:`valuation.domain.modelos_ml`. O OLS continua sendo a
referencia e nao depende de nenhuma biblioteca alem de numpy.

O backtest rolling-origin decide, por setor, qual modelo entra no cenario de
receita projetada. Sem sklearn e sem statsmodels: OLS e ``numpy.linalg.lstsq``
e o efeito fixo de empresa e a transformacao within.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import cast

import numpy as np
import pandas as pd

from .features import COLUNAS_FUNDAMENTOS, COLUNAS_MACRO, enriquecer
from .modelos_ml import MODELOS_ML, OpcoesML, ajustar_e_prever, disponivel

log = logging.getLogger(__name__)

MODELOS = ("fundamentos", "macro", "AR", "setor")
MODELOS_TODOS = (*MODELOS, *MODELOS_ML)
CLIP_PADRAO = (-0.20, 0.35)


@dataclass(frozen=True)
class ModeloFundamentos:
    """Coeficientes do Modelo A, com os efeitos fixos estimados."""

    beta: tuple[float, ...]
    colunas: tuple[str, ...]
    efeito_ano: dict[str, float]
    efeito_setor: dict[str, float]
    r2: float


@dataclass(frozen=True)
class ModeloMacro:
    """Coeficientes do Modelo B, com o efeito fixo de cada empresa."""

    beta: tuple[float, ...]
    colunas: tuple[str, ...]
    alfa: dict[str, float]
    alfa_global: float
    r2: float


def _r2(y: np.ndarray, previsto: np.ndarray) -> float:
    residuo = float(np.sum((y - previsto) ** 2))
    total = float(np.sum((y - y.mean()) ** 2))
    return 0.0 if total <= 0 else 1.0 - residuo / total


def _dummies(serie: pd.Series, prefixo: str) -> pd.DataFrame:
    return pd.get_dummies(serie.astype(str), prefix=prefixo, drop_first=True, dtype=float)


def _matriz_treino(dados: pd.DataFrame) -> pd.DataFrame:
    base = dados[list(COLUNAS_FUNDAMENTOS)].astype(float).reset_index(drop=True)
    ano = _dummies(dados["ano"].reset_index(drop=True), "ano")
    setor = _dummies(dados["setor"].reset_index(drop=True), "setor")
    matriz = pd.concat([base, ano, setor], axis=1).fillna(0.0)
    # Sem intercepto explicito o ano/setor de referencia nao teria efeito
    # proprio; com ele, as dummies viram desvios da categoria base.
    matriz.insert(0, "_const", 1.0)
    return matriz


def _matriz_teste(dados: pd.DataFrame, colunas: tuple[str, ...]) -> pd.DataFrame:
    """Monta a matriz de teste alinhada as colunas do treino.

    O ano alvo nao tem dummy estimada (esta fora da amostra); o efeito do "ano
    tipico" e somado em :func:`prever_fundamentos`. O setor da empresa e
    observado e entra normalmente.
    """
    matriz = pd.DataFrame(0.0, index=range(len(dados)), columns=list(colunas))
    if "_const" in matriz.columns:
        matriz["_const"] = 1.0

    base = dados[list(COLUNAS_FUNDAMENTOS)].astype(float).reset_index(drop=True)
    matriz[list(COLUNAS_FUNDAMENTOS)] = base.to_numpy()

    for posicao, setor in enumerate(dados["setor"].astype(str)):
        coluna = f"setor_{setor}"
        if coluna in matriz.columns:
            matriz.at[posicao, coluna] = 1.0

    return matriz


def ajustar_fundamentos(treino: pd.DataFrame) -> ModeloFundamentos:
    """Estima o Modelo A por OLS com dummies de ano e de setor."""
    dados = treino.dropna(subset=[*COLUNAS_FUNDAMENTOS, "g", "setor"])
    if len(dados) < 40 or dados["setor"].nunique() < 2:
        raise ValueError("amostra insuficiente para o modelo de fundamentos")

    matriz = _matriz_treino(dados)
    x = matriz.to_numpy(float)
    y = dados["g"].to_numpy(float)
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)

    efeito_ano = {
        coluna: float(beta[i])
        for i, coluna in enumerate(matriz.columns)
        if coluna.startswith("ano_")
    }
    efeito_setor = {
        coluna: float(beta[i])
        for i, coluna in enumerate(matriz.columns)
        if coluna.startswith("setor_")
    }
    return ModeloFundamentos(
        beta=tuple(float(valor) for valor in beta),
        colunas=tuple(str(coluna) for coluna in matriz.columns),
        efeito_ano=efeito_ano,
        efeito_setor=efeito_setor,
        r2=_r2(y, x @ beta),
    )


def prever_fundamentos(modelo: ModeloFundamentos, teste: pd.DataFrame) -> np.ndarray:
    """Aplica o Modelo A; features ausentes viram NaN e caem no setor."""
    matriz = _matriz_teste(teste, modelo.colunas)
    base = matriz.to_numpy(float) @ np.asarray(modelo.beta)
    # Ano tipico: media dos efeitos estimados, com o ano de referencia valendo 0.
    efeito_ano = sum(modelo.efeito_ano.values()) / (len(modelo.efeito_ano) + 1)
    return np.asarray(base + efeito_ano, dtype=float)


def ajustar_macro(
    treino: pd.DataFrame,
    colunas: tuple[str, ...] = COLUNAS_MACRO,
) -> ModeloMacro:
    """Estima o Modelo B com efeito fixo de empresa (transformacao within).

    Colunas macro sem cobertura minima no treino sao descartadas: quando a API
    do BCB falha, as expectativas do Focus chegam todas vazias e derrubariam o
    modelo inteiro. Nesse caso o Modelo B roda com as tres variaveis realizadas.
    """
    colunas = tuple(
        coluna
        for coluna in colunas
        if coluna in treino.columns and treino[coluna].notna().mean() >= 0.5
    )
    if not colunas:
        raise ValueError("sem colunas macro com cobertura suficiente")
    dados = treino.dropna(subset=[*colunas, "g", "ticker"])
    if len(dados) < 40 or dados["ticker"].nunique() < 10:
        raise ValueError("amostra insuficiente para o modelo macro")

    x = dados[list(colunas)].to_numpy(float)
    y = dados["g"].to_numpy(float)
    firmes = dados["ticker"].astype(str).to_numpy()

    xbar = pd.DataFrame(x).groupby(firmes).transform("mean").to_numpy(float)
    ybar = pd.Series(y).groupby(firmes).transform("mean").to_numpy(float)
    beta, *_ = np.linalg.lstsq(x - xbar, y - ybar, rcond=None)

    residuo = y - x @ beta
    alfa = pd.Series(residuo).groupby(firmes).mean()
    previsto = x @ beta + pd.Series(firmes).map(alfa).to_numpy(float)

    return ModeloMacro(
        beta=tuple(float(valor) for valor in beta),
        colunas=tuple(colunas),
        alfa={str(chave): float(valor) for chave, valor in alfa.items()},
        alfa_global=float(residuo.mean()),
        r2=_r2(y, previsto),
    )


def prever_macro(modelo: ModeloMacro, teste: pd.DataFrame) -> np.ndarray:
    """Aplica o Modelo B; empresa nova usa o alfa medio."""
    x = teste[list(modelo.colunas)].to_numpy(float)
    alfa = teste["ticker"].astype(str).map(modelo.alfa).fillna(modelo.alfa_global).to_numpy(float)
    return alfa + x @ np.asarray(modelo.beta)


def _prever_setor(treino: pd.DataFrame, teste: pd.DataFrame) -> np.ndarray:
    mediana = treino.groupby("setor")["g"].median()
    geral = float(treino["g"].median())
    return teste["setor"].map(mediana).fillna(geral).to_numpy(float)


def encolher(
    g_empresa: float,
    n_anos: int,
    g_setor: float,
    k: float = 3.0,
) -> tuple[float, float]:
    """Encolhimento empirical Bayes: ``peso = n / (n + k)``.

    Empresa com serie longa confia na propria tendencia; empresa com poucos
    anos e puxada para a mediana do setor. Com n = 4 e k = 3, o peso da empresa
    e 0,57: metade do sinal ainda vem do setor.
    """
    if not math.isfinite(g_empresa) or n_anos <= 0:
        return float(g_setor), 0.0
    peso = n_anos / (n_anos + k)
    return float(peso * g_empresa + (1.0 - peso) * g_setor), float(peso)


def amortecer(
    g_inicial: float,
    g_perpetuidade: float,
    anos: int,
    phi: float = 0.85,
) -> tuple[float, ...]:
    """Convergencia exponencial (Holt amortecido) ate a perpetuidade."""
    return tuple(
        g_perpetuidade + (g_inicial - g_perpetuidade) * phi ** (t - 1) for t in range(1, anos + 1)
    )


def projetar(receita_base: float, crescimento_por_ano: tuple[float, ...]) -> tuple[float, ...]:
    """Aplica os crescimentos em cascata sobre a receita base."""
    valores: list[float] = []
    atual = float(receita_base)
    for crescimento in crescimento_por_ano:
        atual *= 1.0 + float(crescimento)
        valores.append(atual)
    return tuple(valores)


def backtest(
    painel: pd.DataFrame,
    anos_minimo: int = 2014,
    minimo_treino: int = 60,
    clip: tuple[float, float] = CLIP_PADRAO,
    modelos_ml: Sequence[str] = (),
    opcoes_ml: OpcoesML | None = None,
) -> pd.DataFrame:
    """Backtest rolling-origin: treina ate t-1, preve t, para cada ano.

    Nenhuma linha do ano alvo entra no ajuste. O Modelo B usa a macro realizada
    do ano alvo, o que e otimista por construcao e sera declarado no doc.

    ``modelos_ml`` acrescenta candidatos (veja :mod:`valuation.domain.modelos_ml`).
    Um modelo cuja biblioteca falte ou cujo ajuste quebre vira NaN e nao entra
    no resumo, sem interromper o backtest.
    """
    if modelos_ml:
        painel = enriquecer(painel)
        disponiveis = [nome for nome in modelos_ml if disponivel(nome)]
        ausentes = sorted(set(modelos_ml) - set(disponiveis))
        if ausentes:
            log.warning("modelos de ML sem biblioteca instalada: %s", ausentes)
        modelos_ml = disponiveis

    colunas = [
        "ano",
        "ticker",
        "setor",
        "modelo",
        "real",
        "previsto",
        "g_previsto",
        "g_real",
        "erro_g",
        "erro_rel",
        "acerto_sinal",
    ]
    registros: list[pd.DataFrame] = []

    for ano in sorted(int(a) for a in painel["ano"].dropna().unique()):
        if ano < anos_minimo:
            continue

        treino = painel[painel["ano"] < ano]
        teste = painel[painel["ano"] == ano].copy()
        if len(treino) < minimo_treino or teste.empty:
            continue

        previsoes: dict[str, np.ndarray] = {}
        try:
            previsoes["fundamentos"] = prever_fundamentos(ajustar_fundamentos(treino), teste)
        except (ValueError, KeyError):
            previsoes["fundamentos"] = np.full(len(teste), np.nan)

        try:
            previsoes["macro"] = prever_macro(ajustar_macro(treino), teste)
        except (ValueError, KeyError):
            previsoes["macro"] = np.full(len(teste), np.nan)

        previsoes["AR"] = teste["g_ant"].to_numpy(float)
        previsoes["setor"] = _prever_setor(treino, teste)

        for nome in modelos_ml:
            try:
                previsoes[nome] = ajustar_e_prever(nome, treino, teste, opcoes_ml)
            except Exception as exc:  # biblioteca ausente ou ajuste instavel
                log.warning("modelo %s falhou em %d: %s", nome, ano, exc)
                previsoes[nome] = np.full(len(teste), np.nan)

        for modelo, bruto in previsoes.items():
            g_previsto = np.clip(np.asarray(bruto, dtype=float), *clip)
            real = teste["receita_real"].to_numpy(float)
            anterior = teste["receita_real_lag"].to_numpy(float)
            valido = (
                np.isfinite(g_previsto)
                & np.isfinite(real)
                & np.isfinite(anterior)
                & (real > 0)
                & (anterior > 0)
            )
            if not valido.any():
                continue

            g = g_previsto[valido]
            r = real[valido]
            a = anterior[valido]
            previsto = a * np.exp(g)
            g_real = np.log(r / a)

            registros.append(
                pd.DataFrame(
                    {
                        "ano": ano,
                        "ticker": teste["ticker"].to_numpy()[valido],
                        "setor": teste["setor"].to_numpy()[valido],
                        "modelo": modelo,
                        "real": r,
                        "previsto": previsto,
                        "g_previsto": g,
                        "g_real": g_real,
                        "erro_g": g - g_real,
                        "erro_rel": np.abs(previsto - r) / r,
                        "acerto_sinal": np.sign(g) == np.sign(g_real),
                    }
                )
            )

    if not registros:
        return pd.DataFrame(columns=colunas)
    return pd.concat(registros, ignore_index=True)[colunas]


def resumir(historico: pd.DataFrame) -> pd.DataFrame:
    """MAPE, erro medio de crescimento e acerto de sinal por modelo."""
    colunas = [
        "modelo",
        "observacoes",
        "mape",
        "mape_mediano",
        "erro_g",
        "acerto_sinal",
    ]
    if historico.empty:
        return pd.DataFrame(columns=colunas)

    resumo = (
        historico.groupby("modelo")
        .agg(
            observacoes=("erro_rel", "size"),
            mape=("erro_rel", "mean"),
            mape_mediano=("erro_rel", "median"),
            erro_g=("erro_g", "mean"),
            acerto_sinal=("acerto_sinal", "mean"),
        )
        .sort_values("mape")
        .reset_index()
    )
    return resumo


def selecionar_por_setor(
    historico: pd.DataFrame,
    baseline: str = "AR",
    minimo_obs: int = 20,
    margem: float = 0.01,
    forcar: str = "auto",
) -> dict[str, str]:
    """Escolhe um modelo por setor, exigindo ganho minimo sobre o AR.

    ``margem`` evita trocar o baseline por uma diferenca que e ruido. Se nenhum
    modelo bater o AR por pelo menos 1 ponto percentual de MAPE, o setor fica
    no AR. Esse e o portao de aceite do projeto.
    """
    if forcar != "auto":
        return {str(setor): forcar for setor in historico["setor"].dropna().unique()}
    if historico.empty:
        return {}

    tabela = (
        historico.groupby(["setor", "modelo"])["erro_rel"]
        .agg(erro="mean", observacoes="size")
        .reset_index()
    )

    escolha: dict[str, str] = {}
    for setor, grupo in tabela.groupby("setor"):
        elegivel = grupo[grupo["observacoes"] >= minimo_obs]
        if elegivel.empty:
            escolha[str(setor)] = baseline
            continue

        base = elegivel[elegivel["modelo"] == baseline]
        melhor = elegivel.sort_values("erro").iloc[0]

        if base.empty or (
            melhor["modelo"] != baseline
            and float(melhor["erro"]) <= float(base["erro"].iloc[0]) - margem
        ):
            escolha[str(setor)] = str(melhor["modelo"])
        else:
            escolha[str(setor)] = baseline

    return escolha


def estimar_proximo_ano(
    painel: pd.DataFrame,
    escolha: dict[str, str],
    g_perpetuidade: float,
    inflacao_esperada: float,
    anos: int,
    phi: float = 0.85,
    k: float = 3.0,
    clip: tuple[float, float] = CLIP_PADRAO,
    macro_futuro: dict[str, float] | None = None,
    minimo_anos: int = 3,
    modelos_ml: Sequence[str] = (),
    opcoes_ml: OpcoesML | None = None,
) -> pd.DataFrame:
    """Projeta o crescimento do proximo ano para cada ticker.

    A tendencia e estimada em termos REAIS (receita deflacionada pelo IPCA) e
    convertida para nominal antes de entrar no DCF:

        g_nominal_t = (1 + g_real_t) * (1 + inflacao) - 1

    A perpetuidade real e derivada da nominal do ``config.yaml``, para que o
    ultimo ano explicito encontre o valor terminal sem salto.

    Modelos de ML (``modelos_ml``) usam as mesmas premissas macro do Modelo B
    para o ano a frente e as features extras do painel enriquecido.
    """
    if modelos_ml:
        painel = enriquecer(painel)
        disponiveis = [nome for nome in modelos_ml if disponivel(nome)]
        ausentes = sorted(set(modelos_ml) - set(disponiveis))
        if ausentes:
            log.warning("modelos de ML sem biblioteca instalada: %s", ausentes)
        modelos_ml = disponiveis

    treino = painel.dropna(subset=["g", "receita_real_lag"]).copy()
    # Ano-base: ultimo exercicio com receita positiva. Holdings sem receita na
    # DRE teriam 2025 zerado e cairiam num crescimento sem sentido.
    positiva = painel["receita"] if "receita" in painel.columns else painel["receita_real"]
    ultimo = painel[positiva > 0].sort_values("ano").groupby("ticker", sort=False).tail(1).copy()

    previsoes: dict[str, np.ndarray] = {}
    try:
        previsoes["fundamentos"] = prever_fundamentos(ajustar_fundamentos(treino), ultimo)
    except (ValueError, KeyError):
        previsoes["fundamentos"] = np.full(len(ultimo), np.nan)

    if macro_futuro is not None:
        try:
            modelo_macro = ajustar_macro(treino)
            teste_macro = ultimo.copy()
            for coluna, valor in macro_futuro.items():
                teste_macro[coluna] = valor
            previsoes["macro"] = prever_macro(modelo_macro, teste_macro)
        except (ValueError, KeyError):
            previsoes["macro"] = np.full(len(ultimo), np.nan)
    else:
        previsoes["macro"] = np.full(len(ultimo), np.nan)

    previsoes["AR"] = ultimo["g"].to_numpy(float)
    previsoes["setor"] = _prever_setor(treino, ultimo)

    for nome in modelos_ml:
        try:
            teste_ml = ultimo.copy()
            for coluna, valor in (macro_futuro or {}).items():
                teste_ml[coluna] = valor
            previsoes[nome] = ajustar_e_prever(nome, treino, teste_ml, opcoes_ml)
        except Exception as exc:  # biblioteca ausente ou ajuste instavel
            log.warning("modelo %s falhou na projecao: %s", nome, exc)
            previsoes[nome] = np.full(len(ultimo), np.nan)

    n_anos = treino.groupby("ticker")["g"].count()
    mediana_setor = treino.groupby("setor")["g"].median()

    g_perp_real = (1.0 + g_perpetuidade) / (1.0 + inflacao_esperada) - 1.0

    linhas: list[dict[str, object]] = []
    for posicao, linha in enumerate(ultimo.itertuples(index=False)):
        setor = str(linha.setor)
        modelo = escolha.get(setor, "AR")
        if modelo not in previsoes:
            modelo = "AR"

        g_empresa = float(previsoes[modelo][posicao])
        g_setor = float(mediana_setor.get(setor, 0.0))
        observacoes = int(n_anos.get(linha.ticker, 0))

        g_ajustado_real, peso = encolher(g_empresa, observacoes, g_setor, k)
        g_ajustado_real = float(np.clip(g_ajustado_real, *clip))

        serie_real = amortecer(g_ajustado_real, g_perp_real, anos, phi)
        serie_nominal = tuple((1.0 + g) * (1.0 + inflacao_esperada) - 1.0 for g in serie_real)

        receita_base = float(getattr(linha, "receita_real", float("nan")))
        fator_preco = float(getattr(linha, "fator_preco", 1.0))
        # receita_real esta a precos do ultimo ano do painel; desfaz o deflator
        # para projetar em reais correntes, na mesma unidade do crescimento
        # nominal que alimenta o DCF.
        receita_base_nominal = receita_base / fator_preco if fator_preco else float("nan")
        linhas.append(
            {
                "ticker": str(linha.ticker),
                "setor": setor,
                "ano_base": int(cast(int, linha.ano)),
                "modelo_receita": modelo,
                "g_modelo_real": g_empresa,
                "g_setor_real": g_setor,
                "n_anos": observacoes,
                "peso_empresa": peso,
                "g_ajustado_real": g_ajustado_real,
                "crescimento_receita_ajustado": serie_nominal[0],
                "crescimento_por_ano": serie_nominal,
                "receita_projetada_1": (
                    receita_base_nominal * (1.0 + serie_nominal[0])
                    if math.isfinite(receita_base_nominal)
                    else float("nan")
                ),
                "anos_suficientes": observacoes >= minimo_anos,
            }
        )

    return pd.DataFrame(linhas)


__all__ = [
    "CLIP_PADRAO",
    "COLUNAS_FUNDAMENTOS",
    "COLUNAS_MACRO",
    "MODELOS",
    "MODELOS_TODOS",
    "ModeloFundamentos",
    "ModeloMacro",
    "ajustar_fundamentos",
    "ajustar_macro",
    "amortecer",
    "backtest",
    "encolher",
    "estimar_proximo_ano",
    "prever_fundamentos",
    "prever_macro",
    "projetar",
    "resumir",
    "selecionar_por_setor",
]
