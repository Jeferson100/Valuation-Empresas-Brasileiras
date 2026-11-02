"""IPCA via SIDRA/IBGE, com cache em disco.

Antes: ``sidrapy`` era chamado a cada ticker, a linha de cabecalho era descartada
por posicao (``iloc[1:]``) e o alinhamento era feito com ``isin(...).values``, que
pode desalinhar silenciosamente quando falta um ano.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from ..domain.series import indice_ipca_anual

log = logging.getLogger(__name__)

TABELA_IPCA = "1737"
VARIACAO_MENSAL = "69"


def carregar_ipca_mensal(cache_dir: Path | str, offline: bool = False) -> pd.Series:
    """Serie mensal do IPCA (variacao % no mes), indexada por data."""
    cache = Path(cache_dir) / "ipca_mensal.parquet"

    if cache.exists():
        return pd.read_parquet(cache)["ipca"]

    if offline:
        log.warning("modo offline e sem cache de IPCA")
        return pd.Series(dtype=float)

    try:
        import sidrapy

        bruto = sidrapy.get_table(
            table_code=TABELA_IPCA,
            territorial_level="1",
            ibge_territorial_code="all",
            variable=VARIACAO_MENSAL,
            period="last%20360",
        )
    except Exception as exc:  # pragma: no cover - depende da rede
        log.warning("nao foi possivel baixar o IPCA: %s", exc)
        return pd.Series(dtype=float)

    if bruto is None or len(bruto) == 0:
        log.warning("IPCA retornou vazio")
        return pd.Series(dtype=float)

    dados = pd.DataFrame(bruto) if not isinstance(bruto, pd.DataFrame) else bruto

    if "D2C" not in dados.columns or "V" not in dados.columns:
        log.warning("IPCA sem as colunas D2C/V: %s", list(dados.columns))
        return pd.Series(dtype=float)

    # Descarta a linha de cabecalho por conteudo, nao por posicao.
    dados = dados[dados["D2C"].astype(str).str.fullmatch(r"\d{6}")]

    indice = pd.to_datetime(dados["D2C"].astype(str), format="%Y%m", errors="coerce")
    valores = pd.to_numeric(dados["V"], errors="coerce")
    serie = pd.Series(valores.to_numpy(), index=indice).dropna().sort_index()
    serie.name = "ipca"

    cache.parent.mkdir(parents=True, exist_ok=True)
    serie.to_frame().to_parquet(cache)
    return serie


def carregar_indice_ipca(cache_dir: Path | str, offline: bool = False) -> pd.Series | None:
    """Indice acumulado anual do IPCA, ou ``None`` se indisponivel."""
    mensal = carregar_ipca_mensal(cache_dir, offline=offline)
    if mensal.empty:
        return None
    return indice_ipca_anual(mensal)


__all__ = ["carregar_indice_ipca", "carregar_ipca_mensal"]
