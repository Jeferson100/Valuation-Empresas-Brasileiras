"""Geracao do CSV e atualizacao do README.

O README passa a mostrar os 20 melhores casos com ``status=ok`` e a contagem por
status, em vez de 163 linhas com um dicionario serializado dentro de uma celula.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pandas as pd

from ..domain.erros import Status

log = logging.getLogger(__name__)

INICIO = "<!-- VALUATION:START -->"
FIM = "<!-- VALUATION:END -->"

COLUNAS_SAIDA = [
    "acao",
    "setor",
    "segmento",
    "as_of",
    "data_coleta",
    "premissas_hash",
    "modelo",
    "status",
    "flags",
    "preco_atual",
    "preco_dcf",
    "preco_ddm",
    "preco_alvo_p25",
    "preco_alvo_p50",
    "preco_alvo_p75",
    "upside_p50",
    "margem_seguranca",
    "recomendacao",
    "wacc",
    "ke",
    "kd",
    "beta_l",
    "rf",
    "erp",
    "g_perpetuidade",
    "g_receita",
    "margem_ebit",
    "capex_receita",
    "da_receita",
    "nwc_receita",
    "aliquota",
    "receita_base",
    "ev",
    "divida_bruta",
    "caixa",
    "divida_liquida",
    "ativos_nao_operacionais",
    "equity_value",
    "num_acoes",
    "fator_cambio",
]

COLUNAS_README = [
    "acao",
    "setor",
    "preco_atual",
    "preco_alvo_p25",
    "preco_alvo_p50",
    "preco_alvo_p75",
    "upside_p50",
    "margem_seguranca",
    "recomendacao",
    "wacc",
    "g_perpetuidade",
]


def salvar_csv(df: pd.DataFrame, destino: Path | str) -> Path:
    """Grava o CSV com colunas estaveis e ordenacao por upside."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)

    saida = df.copy()
    for coluna in COLUNAS_SAIDA:
        if coluna not in saida.columns:
            saida[coluna] = pd.NA
    saida = saida[COLUNAS_SAIDA]

    ordenacao = saida["upside_p50"].fillna(float("-inf"))
    saida = saida.assign(_ordem=ordenacao).sort_values("_ordem", ascending=False)
    saida = saida.drop(columns="_ordem")

    saida.to_csv(destino, index=False, encoding="utf-8")
    return destino


def resumo_status(df: pd.DataFrame) -> str:
    """Tabela markdown com a contagem de cada status."""
    contagem = df["status"].value_counts()
    linhas = [f"| `{status}` | {quantidade} |" for status, quantidade in contagem.items()]
    return "| status | tickers |\n|---|---:|\n" + "\n".join(linhas)


def tabela_top(df: pd.DataFrame, top: int = 20) -> str:
    """Tabela markdown dos melhores casos avaliados."""
    ok = df[(df["status"] == Status.OK.value) & df["preco_alvo_p50"].notna()]
    if ok.empty:
        return "_Nenhum ticker passou nos portoes de sanidade nesta execucao._"

    recorte = ok.nlargest(top, "upside_p50")[COLUNAS_README].copy()
    recorte["upside_p50"] = recorte["upside_p50"] * 100.0
    recorte["margem_seguranca"] = recorte["margem_seguranca"] * 100.0
    return recorte.to_markdown(index=False, floatfmt=".2f")


def montar_bloco(df: pd.DataFrame, top: int = 20) -> str:
    """Bloco completo que substitui a secao de resultados do README."""
    avaliados = int((df["status"] == Status.OK.value).sum())
    return (
        f"{INICIO}\n"
        f"### Top {top} por upside potencial (status `ok`)\n\n"
        f"{tabela_top(df, top)}\n\n"
        f"**Cobertura:** {len(df)} tickers no universo, {avaliados} com `status=ok`.\n"
        "Preços-alvo em R$; `upside` e `margem de segurança` em %.\n\n"
        f"{resumo_status(df)}\n\n"
        "Resultado completo: "
        "[dados/valores_valuations_acoes.csv](dados/valores_valuations_acoes.csv) · "
        "Metodologia: [METODOLOGIA.md](METODOLOGIA.md)\n"
        f"{FIM}"
    )


def atualizar_readme(caminho: Path | str, df: pd.DataFrame, top: int = 20) -> None:
    """Substitui o bloco delimitado por marcadores HTML.

    Os marcadores precisam estar em linhas proprias: assim uma mencao aos
    marcadores no meio de um paragrafo nao e confundida com o bloco.
    """
    caminho = Path(caminho)
    bloco = montar_bloco(df, top)
    texto = caminho.read_text(encoding="utf-8")

    padrao = re.compile(
        r"^" + re.escape(INICIO) + r"$.*?^" + re.escape(FIM) + r"$",
        re.S | re.M,
    )
    if padrao.search(texto):
        texto = padrao.sub(lambda _: bloco, texto, count=1)
    else:
        texto = texto.rstrip() + "\n\n" + bloco + "\n"

    caminho.write_text(texto, encoding="utf-8")
    log.info("README atualizado: %s", caminho)


__all__ = [
    "COLUNAS_README",
    "COLUNAS_SAIDA",
    "FIM",
    "INICIO",
    "atualizar_readme",
    "montar_bloco",
    "resumo_status",
    "salvar_csv",
    "tabela_top",
]
