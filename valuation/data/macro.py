"""Series macroeconomicas anuais do Banco Central (API SGS).

Sem dependencia nova: ``urllib`` da stdlib. A API SGS e mais previsivel que a
busca por nome de serie do ipeadatapy, que devolve vazio para "cambio".

Series usadas:
    24364  IBC-Br (indice de atividade, 2022 = 100)
    433    IPCA (variacao % mensal)
    3695   cambio USD/BRL (media mensal)
    432    Selic (taxa anualizada, % a.a.)

O SGS recusa (HTTP 406) intervalos longos em series diarias como a Selic. Por
isso o download vai em janelas de cinco anos. Cada serie falha de forma
independente: sem IPCA nao ha deflator e a macro inteira fica indisponivel; sem
as demais o painel segue com o que existir.
"""

from __future__ import annotations

import json
import logging
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..domain.erros import ErroDados

log = logging.getLogger(__name__)

URL_SGS = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
    "?formato=json&dataInicial={inicio}&dataFinal={fim}"
)

SERIES = {"ibc_br": 24364, "ipca": 433, "cambio": 3695, "selic": 432}

ANOS_POR_JANELA = 5


def _fresco(caminho: Path, ttl_dias: int) -> bool:
    idade = datetime.now() - datetime.fromtimestamp(caminho.stat().st_mtime)
    return idade < timedelta(days=ttl_dias)


def _baixar_intervalo(
    codigo: int,
    inicio: str,
    fim: str,
    anos_por_janela: int = ANOS_POR_JANELA,
) -> str:
    """Baixa o intervalo em janelas e devolve o JSON concatenado."""
    inicio_dt = datetime.strptime(inicio, "%d/%m/%Y")
    fim_dt = datetime.strptime(fim, "%d/%m/%Y")
    if inicio_dt > fim_dt:
        return "[]"

    registros: list[dict[str, str]] = []
    for ano_inicio in range(inicio_dt.year, fim_dt.year + 1, anos_por_janela):
        ano_fim = min(ano_inicio + anos_por_janela - 1, fim_dt.year)
        de = inicio_dt if ano_inicio == inicio_dt.year else datetime(ano_inicio, 1, 1)
        ate = fim_dt if ano_fim == fim_dt.year else datetime(ano_fim, 12, 31)

        url = URL_SGS.format(
            codigo=codigo,
            inicio=de.strftime("%d/%m/%Y"),
            fim=ate.strftime("%d/%m/%Y"),
        )
        requisicao = urllib.request.Request(url, headers={"User-Agent": "valuation-br/1.0"})
        bruto = urllib.request.urlopen(requisicao, timeout=60).read().decode("utf-8")
        registros.extend(json.loads(bruto))

    return json.dumps(registros)


def baixar_sgs(
    codigo: int,
    cache_dir: Path | str,
    inicio: str = "01/01/2008",
    fim: str | None = None,
    ttl_dias: int = 30,
    offline: bool = False,
) -> pd.Series:
    """Serie mensal do SGS, indexada por data."""
    fim = fim or datetime.now().strftime("%d/%m/%Y")
    cache = Path(cache_dir) / "macro" / f"sgs{codigo}.json"

    if cache.exists() and (offline or _fresco(cache, ttl_dias)):
        texto = cache.read_text(encoding="utf-8")
    elif offline:
        raise ErroDados(f"modo offline e sem cache da serie SGS {codigo}")
    else:
        try:
            texto = _baixar_intervalo(codigo, inicio, fim)
        except Exception as exc:
            if cache.exists():
                log.warning("SGS %s indisponivel, usando cache anterior: %s", codigo, exc)
                texto = cache.read_text(encoding="utf-8")
            else:
                raise ErroDados(f"falha ao baixar a serie SGS {codigo}: {exc}") from exc
        else:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                cache.write_text(texto, encoding="utf-8")
            except Exception as exc:  # cache e otimizacao, nao requisito
                log.warning("nao foi possivel gravar o cache da serie %s: %s", codigo, exc)

    dados = pd.DataFrame(json.loads(texto))
    if dados.empty or "data" not in dados.columns or "valor" not in dados.columns:
        log.warning("serie SGS %s retornou vazia", codigo)
        return pd.Series(dtype=float, name=f"sgs{codigo}")

    dados["data"] = pd.to_datetime(dados["data"], format="%d/%m/%Y", errors="coerce")
    dados["valor"] = pd.to_numeric(
        dados["valor"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
    dados = dados.dropna(subset=["data", "valor"]).drop_duplicates("data")
    serie = dados.set_index("data")["valor"].sort_index()
    serie.name = f"sgs{codigo}"
    return serie


def _anual_ipca(serie: pd.Series) -> pd.Series:
    """IPCA acumulado no ano."""
    return (1.0 + serie / 100.0).groupby(pd.DatetimeIndex(serie.index).year).prod() - 1.0


def _anual_media(serie: pd.Series) -> pd.Series:
    return serie.groupby(pd.DatetimeIndex(serie.index).year).mean()


def carregar_macro(
    cache_dir: Path | str,
    offline: bool = False,
    inicio: str = "01/01/2008",
) -> pd.DataFrame:
    """DataFrame anual indexado por ano; vazio quando o BCB esta fora.

    A falha nao derruba o run mensal: sem macro o Modelo B fica indisponivel e
    a selecao cai no AR ou na mediana setorial.
    """

    def tentar(nome: str) -> pd.Series:
        try:
            return baixar_sgs(SERIES[nome], cache_dir, inicio, offline=offline)
        except ErroDados as exc:
            log.warning("serie macro %s indisponivel: %s", nome, exc)
            return pd.Series(dtype=float)

    ipca = tentar("ipca")
    if ipca.empty:
        log.warning("IPCA indisponivel: sem deflator para a receita real")
        return pd.DataFrame()

    ibc = tentar("ibc_br")
    cambio = tentar("cambio")
    selic = tentar("selic")

    colunas: dict[str, pd.Series] = {"ipca": _anual_ipca(ipca)}
    if not ibc.empty:
        colunas["ibc_br"] = _anual_media(ibc)
    if not cambio.empty:
        colunas["cambio"] = _anual_media(cambio)
    if not selic.empty:
        # A Selic do SGS 432 ja vem anualizada (% a.a.); media, nao composicao.
        colunas["selic"] = _anual_media(selic)

    macro = pd.DataFrame(colunas)
    macro.index.name = "ano"
    if "ibc_br" in macro.columns:
        macro["d_ibc_br"] = np.log(macro["ibc_br"]).diff()
    if "cambio" in macro.columns:
        macro["d_cambio"] = np.log(macro["cambio"]).diff()
    return macro


__all__ = ["SERIES", "baixar_sgs", "carregar_macro"]
