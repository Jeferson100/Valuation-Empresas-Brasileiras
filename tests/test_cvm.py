"""Testes do parser da CVM, com ZIPs sinteticos (sem rede)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from valuation.data.cvm import expandir_units, extrair_ano, montar_painel

CNPJ = "00.000.000/0001-00"

COLUNAS = [
    "CNPJ_CIA",
    "DT_REFER",
    "VERSAO",
    "DENOM_CIA",
    "CD_CVM",
    "GRUPO_DFP",
    "MOEDA",
    "ESCALA_MOEDA",
    "ORDEM_EXERC",
    "DT_INI_EXERC",
    "DT_FIM_EXERC",
    "CD_CONTA",
    "DS_CONTA",
    "VL_CONTA",
    "ST_CONTA_FIXA",
]


def _registro(
    ano: int,
    conta: str,
    valor: float,
    *,
    ordem: str = "ULTIMO",
    escala: str = "MIL",
    versao: str = "1",
) -> dict[str, str]:
    return {
        "CNPJ_CIA": CNPJ,
        "DT_REFER": f"{ano}-12-31",
        "VERSAO": versao,
        "DENOM_CIA": "EMPRESA TESTE",
        "CD_CVM": "1",
        "GRUPO_DFP": "DF Consolidado",
        "MOEDA": "REAL",
        "ESCALA_MOEDA": escala,
        "ORDEM_EXERC": ordem,
        "DT_INI_EXERC": f"{ano}-01-01",
        "DT_FIM_EXERC": f"{ano}-12-31",
        "CD_CONTA": conta,
        "DS_CONTA": conta,
        "VL_CONTA": str(valor),
        "ST_CONTA_FIXA": "S",
    }


def _csv(registros: list[dict[str, str]]) -> str:
    return pd.DataFrame(registros, columns=COLUNAS).to_csv(sep=";", index=False)


def _pacote(cache: Path, ano: int, arquivos: dict[str, list[dict[str, str]]]) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(cache / f"dfp{ano}.zip", "w") as pacote:
        for nome, registros in arquivos.items():
            pacote.writestr(nome, _csv(registros))


def _fca(cache: Path, ano: int, tickers: list[str]) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    dados = pd.DataFrame(
        {
            "CNPJ_Companhia": [CNPJ] * len(tickers),
            "Codigo_Negociacao": tickers,
        }
    )
    with zipfile.ZipFile(cache / f"fca{ano}.zip", "w") as pacote:
        pacote.writestr(
            f"fca_cia_aberta_valor_mobiliario_{ano}.csv",
            dados.to_csv(sep=";", index=False),
        )


def test_escala_mil_multiplica_por_mil(tmp_path: Path) -> None:
    _pacote(
        tmp_path,
        2024,
        {"dfp_cia_aberta_DRE_con_2024.csv": [_registro(2024, "3.01", 1000.0)]},
    )
    painel = extrair_ano(2024, tmp_path)
    assert painel.loc[painel["campo"] == "receita", "valor"].iloc[0] == 1_000_000.0


def test_ordem_exerc_ignora_comparativo(tmp_path: Path) -> None:
    _pacote(
        tmp_path,
        2024,
        {
            "dfp_cia_aberta_DRE_con_2024.csv": [
                _registro(2024, "3.01", 1000.0, ordem="ULTIMO"),
                _registro(2024, "3.01", 999.0, ordem="PENULTIMO"),
            ]
        },
    )
    painel = extrair_ano(2024, tmp_path)
    assert painel.loc[painel["campo"] == "receita", "valor"].iloc[0] == 1_000_000.0


def test_consolidado_vence_individual(tmp_path: Path) -> None:
    _pacote(
        tmp_path,
        2024,
        {
            "dfp_cia_aberta_DRE_con_2024.csv": [_registro(2024, "3.01", 1000.0)],
            "dfp_cia_aberta_DRE_ind_2024.csv": [_registro(2024, "3.01", 500.0)],
        },
    )
    painel = extrair_ano(2024, tmp_path)
    assert painel.loc[painel["campo"] == "receita", "valor"].iloc[0] == 1_000_000.0


def test_reafirmacao_mais_recente_vence(tmp_path: Path) -> None:
    _pacote(
        tmp_path,
        2023,
        {"dfp_cia_aberta_DRE_con_2023.csv": [_registro(2023, "3.01", 1000.0)]},
    )
    _pacote(
        tmp_path,
        2024,
        {"dfp_cia_aberta_DRE_con_2024.csv": [_registro(2023, "3.01", 1200.0)]},
    )
    _fca(tmp_path, 2024, ["ABCD3"])

    painel = montar_painel([2023, 2024], tmp_path, {"ABCD3"})
    linha = painel[(painel["ano"] == 2023) & (painel["ticker"] == "ABCD3")]
    assert linha["receita"].iloc[0] == 1_200_000.0


def test_expandir_units_mapeia_ticker_para_unit(tmp_path: Path) -> None:
    mapa = pd.DataFrame({"cnpj": [CNPJ], "ticker": ["KLBN11"]})
    expandido = expandir_units(mapa, {"KLBN3", "KLBN4"})
    assert set(expandido["ticker"]) == {"KLBN11", "KLBN3", "KLBN4"}


def test_montar_painel_sem_pacote_levanta(tmp_path: Path) -> None:
    from valuation.domain.erros import ErroDados

    with pytest.raises(ErroDados):
        montar_painel([2024], tmp_path, {"ABCD3"})
