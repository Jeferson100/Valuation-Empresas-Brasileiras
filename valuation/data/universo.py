"""Universo de tickers.

Usa o ``dados/setor.csv`` versionado no proprio repositorio. Antes o script
baixava a lista de outro repositorio, o que acoplava o projeto a um caminho
externo e impedia o uso do setor na escolha do modelo.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pandas as pd

COLUNAS_OBRIGATORIAS = {"acao", "setor"}

RENOMEAR = {
    "tic": "acao",
    "Setor": "setor",
    "Segmento": "segmento",
    "Segmento de Listagem": "segmento_listagem",
}


def normalizar_texto(valor: str) -> str:
    """Remove acentos e espacos extras, para comparacao robusta de setores."""
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    texto = texto.replace("\u00ad", "")
    return " ".join(texto.split())


def limpar_texto(valor: str) -> str:
    """Remove hifens suaves e espacos extras, preservando acentos para exibicao."""
    texto = str(valor).replace("\u00ad", "")
    return " ".join(texto.split())


def eh_financeiro(setor: str) -> bool:
    """Setor financeiro (banco, seguradora, bolsa) nao se avalia por FCFF."""
    return normalizar_texto(setor).lower() == "financeiro"


def _ler_csv(caminho: Path) -> pd.DataFrame:
    """Le o CSV tentando UTF-8 e caindo para latin-1 (arquivos antigos da B3)."""
    for codificacao in ("utf-8", "latin-1"):
        try:
            return pd.read_csv(caminho, encoding=codificacao)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(caminho, encoding="utf-8", encoding_errors="replace")


def carregar_universo(caminho: Path | str) -> pd.DataFrame:
    """Le o CSV de setores e devolve ``acao``, ``setor`` e ``segmento``."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise FileNotFoundError(f"universo nao encontrado: {caminho}")

    dados = _ler_csv(caminho).rename(columns=RENOMEAR)
    faltando = COLUNAS_OBRIGATORIAS - set(dados.columns)
    if faltando:
        raise ValueError(f"universo sem colunas obrigatorias: {sorted(faltando)}")

    if "segmento" not in dados.columns:
        dados["segmento"] = ""

    universo = dados[["acao", "setor", "segmento"]].copy()
    universo["acao"] = universo["acao"].astype(str).str.strip().str.upper()
    universo["setor"] = universo["setor"].map(limpar_texto)
    universo["segmento"] = universo["segmento"].fillna("").map(limpar_texto)
    universo = universo.dropna(subset=["acao"]).drop_duplicates(subset=["acao"])
    return universo.sort_values("acao").reset_index(drop=True)


__all__ = ["carregar_universo", "eh_financeiro", "normalizar_texto"]
