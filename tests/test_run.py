"""Teste de integracao do pipeline, sem rede."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tests.fabricas import criar_snapshot
from valuation.data.provider import YFinanceProvider
from valuation.domain.erros import ErroDados
from valuation.pipeline import run


def _universo(tmp_path: Path, setor: str = "Materiais Basicos") -> Path:
    caminho = tmp_path / "setor.csv"
    pd.DataFrame({"tic": ["TEST3"], "Setor": [setor], "Segmento": ["Teste"]}).to_csv(
        caminho, index=False
    )
    return caminho


def _executar(
    tmp_path: Path,
    monkeypatch,
    setor: str = "Materiais Basicos",
    snapshot=None,
) -> pd.DataFrame:
    snapshot = snapshot or criar_snapshot()
    monkeypatch.setattr(YFinanceProvider, "obter", lambda self, ticker: snapshot)

    saida = tmp_path / "saida.csv"
    codigo = run.main(
        [
            "--tickers",
            "TEST3",
            "--universo",
            str(_universo(tmp_path, setor)),
            "--saida",
            str(saida),
            "--cache",
            str(tmp_path / "cache"),
            "--sem-readme",
            "--offline",
        ]
    )

    assert codigo == 0
    return pd.read_csv(saida)


def test_pipeline_completo_sem_rede(tmp_path: Path, monkeypatch) -> None:
    resultado = _executar(tmp_path, monkeypatch)

    assert len(resultado) == 1
    linha = resultado.iloc[0]
    assert linha["acao"] == "TEST3"
    assert linha["modelo"] == "dcf"
    assert linha["status"] == "ok"
    assert linha["preco_alvo_p25"] <= linha["preco_alvo_p50"] <= linha["preco_alvo_p75"]
    assert linha["preco_dcf"] > 0
    assert 0.0 < linha["wacc"] < 0.5
    assert linha["aliquota"] <= 0.34
    assert not (tmp_path / "erros.csv").exists()


def test_pipeline_financeira_usa_ddm(tmp_path: Path, monkeypatch) -> None:
    resultado = _executar(tmp_path, monkeypatch, setor="Financeiro")
    linha = resultado.iloc[0]

    assert linha["modelo"] == "ddm"
    assert linha["status"] != "setor_incompativel"
    assert linha["aliquota"] <= 0.45


def test_pipeline_marca_wacc_degenerado(tmp_path: Path, monkeypatch) -> None:
    """Market cap minusculo contra divida enorme: status, nao excecao."""
    resultado = _executar(tmp_path, monkeypatch, snapshot=criar_snapshot(preco_final=0.001))
    linha = resultado.iloc[0]

    assert linha["status"] == "wacc_invalido"
    assert linha["preco_atual"] == pytest.approx(0.001)
    assert pd.isna(linha["preco_alvo_p50"])
    assert linha["recomendacao"] == "n/d"


def test_pipeline_registra_falha_de_coleta(tmp_path: Path, monkeypatch) -> None:
    def falhar(self, ticker):
        raise ErroDados("timeout simulado")

    monkeypatch.setattr(YFinanceProvider, "obter", falhar)

    codigo = run.main(
        [
            "--tickers",
            "TEST3",
            "--universo",
            str(_universo(tmp_path)),
            "--saida",
            str(tmp_path / "saida.csv"),
            "--cache",
            str(tmp_path / "cache"),
            "--sem-readme",
            "--offline",
        ]
    )

    assert codigo == 0
    erros = pd.read_csv(tmp_path / "erros.csv")
    assert erros.iloc[0]["acao"] == "TEST3"
    assert "timeout simulado" in erros.iloc[0]["excecao"]


def test_pipeline_universo_vazio(tmp_path: Path) -> None:
    caminho = tmp_path / "vazio.csv"
    pd.DataFrame({"tic": [], "Setor": []}).to_csv(caminho, index=False)
    assert run.main(["--universo", str(caminho), "--offline", "--sem-readme"]) == 2
