"""Previsao de receita: painel, modelos e artefatos.

Le o painel versionado da CVM, combina com a macro do BCB e com o exercicio mais
recente de cada snapshot, roda o backtest e devolve o crescimento ano a ano que
alimenta o segundo DCF (cenario de receita projetada).
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ..data.macro import carregar_macro
from ..data.snapshot import SnapshotFinanceiro
from ..domain.erros import ErroDados
from ..domain.previsao import (
    COLUNAS_MACRO,
    backtest,
    estimar_proximo_ano,
    resumir,
    selecionar_por_setor,
)
from ..domain.series import linha
from .config import Config

log = logging.getLogger(__name__)

COLUNAS_NUMERICAS = (
    "receita",
    "ebit",
    "lucro_liquido",
    "ativo_total",
    "patrimonio_liquido",
)


def carregar_receitas(caminho: Path | str) -> pd.DataFrame:
    """Le o painel historico e valida as colunas minimas."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroDados(f"painel de receitas ausente: {caminho}")

    dados = pd.read_csv(caminho)
    faltando = {"ticker", "ano", "receita"} - set(dados.columns)
    if faltando:
        raise ErroDados(f"painel sem colunas obrigatorias: {sorted(faltando)}")

    dados["ticker"] = dados["ticker"].astype(str).str.upper().str.strip()
    dados["ano"] = pd.to_numeric(dados["ano"], errors="coerce")
    dados = dados.dropna(subset=["ticker", "ano"])
    dados["ano"] = dados["ano"].astype(int)
    return dados


def montar_painel(
    receitas: pd.DataFrame,
    macro: pd.DataFrame,
    universo: pd.DataFrame,
) -> pd.DataFrame:
    """Monta o painel analitico: receita real, crescimento e defasagens."""
    dados = receitas.copy()
    dados["ticker"] = dados["ticker"].astype(str).str.upper().str.strip()
    dados["ano"] = pd.to_numeric(dados["ano"], errors="coerce")
    dados = dados.dropna(subset=["ticker", "ano", "receita"])
    dados["ano"] = dados["ano"].astype(int)

    if "setor" not in dados.columns:
        dados = dados.merge(
            universo[["acao", "setor"]],
            left_on="ticker",
            right_on="acao",
            how="left",
        ).drop(columns=["acao"])

    for coluna in COLUNAS_NUMERICAS:
        if coluna not in dados.columns:
            dados[coluna] = np.nan

    # Deflator: receita em precos do ultimo ano do painel.
    if not macro.empty and "ipca" in macro.columns:
        indice = (1.0 + macro["ipca"].fillna(0.0)).cumprod()
        fator = indice.max() / indice
        dados["fator_preco"] = dados["ano"].map(fator)
        # Anos ainda sem IPCA publicado usam o ultimo deflator disponivel.
        dados["fator_preco"] = dados["fator_preco"].fillna(float(fator.iloc[-1]))
        dados = dados.merge(macro.reset_index(), on="ano", how="left")
    else:
        dados["fator_preco"] = 1.0

    for coluna in COLUNAS_MACRO:
        if coluna not in dados.columns:
            dados[coluna] = np.nan

    for coluna in COLUNAS_NUMERICAS:
        dados[coluna + "_real"] = dados[coluna] * dados["fator_preco"]

    dados = (
        dados.sort_values(["ticker", "ano"])
        .drop_duplicates(["ticker", "ano"], keep="last")
        .reset_index(drop=True)
    )

    dados["log_receita"] = np.log(dados["receita_real"].where(dados["receita_real"] > 0))
    dados["g"] = dados.groupby("ticker", sort=False)["log_receita"].diff()
    dados["g_ant"] = dados.groupby("ticker", sort=False)["g"].shift(1)
    dados["log_receita_lag"] = dados.groupby("ticker", sort=False)["log_receita"].shift(1)
    dados["margem"] = (dados["ebit_real"] / dados["receita_real"]).replace(
        [np.inf, -np.inf], np.nan
    )
    dados["roa"] = (dados["lucro_liquido_real"] / dados["ativo_total_real"]).replace(
        [np.inf, -np.inf], np.nan
    )
    dados["giro"] = (dados["receita_real"] / dados["ativo_total_real"]).replace(
        [np.inf, -np.inf], np.nan
    )
    for coluna in ("margem", "roa", "giro", "receita_real"):
        dados[coluna + "_lag"] = dados.groupby("ticker", sort=False)[coluna].shift(1)

    # Empresa com ano faltando (ou receita zero) nao tem "ano anterior": sem
    # isso, o diff entre 2009 e 2011 viraria um crescimento de um ano so.
    ano_anterior = dados.groupby("ticker", sort=False)["ano"].shift(1)
    consecutivo = (dados["ano"] - ano_anterior) == 1
    defasagens = [
        "g",
        "g_ant",
        "log_receita_lag",
        "receita_real_lag",
        "margem_lag",
        "roa_lag",
        "giro_lag",
    ]
    dados[defasagens] = dados[defasagens].where(consecutivo, other=np.nan)

    return dados


def atualizar_com_snapshots(
    receitas: pd.DataFrame,
    snapshots: dict[str, SnapshotFinanceiro],
) -> pd.DataFrame:
    """Acrescenta o exercicio mais recente do yfinance, se for mais novo.

    O painel da CVM e atualizado uma vez por ano; o snapshot mantem o run
    mensal corrente sem precisar baixar 220 MB.

    Recebe as linhas CRUAS (ticker, ano, receita, ...), antes de
    ``montar_painel``: as colunas derivadas (receita real, crescimento,
    defasagens) precisam ser calculadas depois de anexar o ano novo.
    """
    novas: list[dict[str, object]] = []

    for ticker, snapshot in snapshots.items():
        try:
            ano = int(pd.Timestamp(snapshot.financials.columns.max()).year)
        except Exception:
            continue

        receita = linha(snapshot.financials, "Total Revenue", padrao=float("nan"))
        if not np.isfinite(receita) or receita <= 0:
            continue

        existente = receitas[(receitas["ticker"] == ticker) & (receitas["ano"] >= ano)]
        if not existente.empty:
            continue

        novas.append(
            {
                "ticker": ticker,
                "ano": ano,
                "receita": receita,
                "ebit": linha(snapshot.financials, "EBIT", "Operating Income", "Pretax Income"),
                "lucro_liquido": linha(snapshot.financials, "Net Income"),
                "ativo_total": linha(snapshot.balance, "Total Assets"),
                "patrimonio_liquido": linha(snapshot.balance, "Stockholders Equity"),
                "origem": "yfinance",
            }
        )

    if not novas:
        return receitas
    return pd.concat([receitas, pd.DataFrame(novas)], ignore_index=True)


def prever_receitas(
    painel: pd.DataFrame,
    config: Config,
    macro_futuro: dict[str, float] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Roda backtest, escolhe modelo por setor e projeta o proximo ano."""
    cfg = config.previsao_receita
    clip = (cfg.clip_min, cfg.clip_max)

    base = painel.dropna(subset=["g", "receita_real_lag"]).copy()
    base = base[base["g"].abs() < 1.5]

    historico = backtest(
        base,
        anos_minimo=cfg.anos_minimo_backtest,
        minimo_treino=cfg.minimo_treino,
        clip=clip,
    )
    resumo = resumir(historico)
    escolha = selecionar_por_setor(
        historico,
        baseline="AR",
        minimo_obs=cfg.minimo_obs_setor,
        margem=cfg.margem_minima,
        forcar=cfg.modelo,
    )

    projecoes = estimar_proximo_ano(
        painel,
        escolha,
        g_perpetuidade=config.g_perpetuidade,
        inflacao_esperada=cfg.ipca_esperado,
        anos=config.anos_projecao,
        phi=cfg.amortecimento,
        k=cfg.encolhimento_k,
        clip=clip,
        macro_futuro=macro_futuro,
        minimo_anos=cfg.minimo_anos,
    )
    return projecoes, historico, resumo, escolha


def gravar_artefatos(
    projecoes: pd.DataFrame,
    historico: pd.DataFrame,
    resumo: pd.DataFrame,
    pasta: Path | str,
) -> None:
    """Grava projecoes, backtest detalhado e resumo por modelo."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    saida = projecoes.copy()
    if "crescimento_por_ano" in saida.columns:
        saida["crescimento_por_ano"] = saida["crescimento_por_ano"].map(
            lambda valores: ";".join(f"{float(v):.6f}" for v in valores)
        )

    saida.to_csv(
        pasta / "projecoes_receita.csv", index=False, encoding="utf-8", lineterminator="\n"
    )
    historico.to_csv(
        pasta / "backtest_receita.csv", index=False, encoding="utf-8", lineterminator="\n"
    )
    resumo.to_csv(pasta / "backtest_resumo.csv", index=False, encoding="utf-8", lineterminator="\n")


__all__ = [
    "atualizar_com_snapshots",
    "carregar_macro",
    "carregar_receitas",
    "gravar_artefatos",
    "montar_painel",
    "prever_receitas",
]
