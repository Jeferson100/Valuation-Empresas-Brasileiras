"""Testes do CSV e da atualizacao idempotente do README."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from valuation.pipeline.relatorio import (
    COLUNAS_SAIDA,
    FIM,
    INICIO,
    atualizar_readme,
    montar_bloco,
    salvar_csv,
)


def _df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "acao": "TEST3",
                "setor": "Materiais Basicos",
                "preco_atual": 10.0,
                "preco_alvo_p25": 12.0,
                "preco_alvo_p50": 15.0,
                "preco_alvo_p75": 18.0,
                "upside_p50": 0.5,
                "margem_seguranca": 0.25,
                "recomendacao": "compra",
                "wacc": 0.16,
                "g_perpetuidade": 0.03,
                "status": "ok",
            },
            {
                "acao": "BAD3",
                "setor": "Financeiro",
                "preco_atual": 5.0,
                "status": "setor_incompativel",
                "flags": "financeira avaliada por FCFF",
            },
        ]
    )


def test_salvar_csv_tem_schema_estavel(tmp_path: Path) -> None:
    destino = salvar_csv(_df(), tmp_path / "saida.csv")
    lido = pd.read_csv(destino)

    assert list(lido.columns) == COLUNAS_SAIDA
    assert len(lido) == 2
    assert lido.iloc[0]["acao"] == "TEST3"


def test_bloco_readme_mostra_apenas_status_ok() -> None:
    bloco = montar_bloco(_df(), top=20)
    assert "TEST3" in bloco
    assert "BAD3" not in bloco
    assert "setor_incompativel" in bloco


def test_readme_idempotente(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# Projeto\n\nTexto.\n", encoding="utf-8")

    atualizar_readme(readme, _df())
    atualizar_readme(readme, _df())

    texto = readme.read_text(encoding="utf-8")
    assert texto.count(INICIO) == 1
    assert texto.count(FIM) == 1
    assert texto.startswith("# Projeto")


def test_readme_substitui_bloco_antigo(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        f"# Projeto\n\n{INICIO}\nconteudo velho\n{FIM}\n\nRodape.\n",
        encoding="utf-8",
    )

    atualizar_readme(readme, _df())
    texto = readme.read_text(encoding="utf-8")

    assert "conteudo velho" not in texto
    assert "Rodape." in texto


def test_mencao_aos_marcadores_no_texto_nao_e_substituida(tmp_path: Path) -> None:
    """Regressao: documentar os marcadores no README quebrava a atualizacao."""
    readme = tmp_path / "README.md"
    readme.write_text(
        f"# Projeto\n\nUse os marcadores `{INICIO}` e `{FIM}`.\n\n"
        f"{INICIO}\nconteudo velho\n{FIM}\n",
        encoding="utf-8",
    )

    atualizar_readme(readme, _df())
    texto = readme.read_text(encoding="utf-8")

    assert "Use os marcadores" in texto
    assert "conteudo velho" not in texto
    assert texto.count(INICIO) == 2  # a mencao inline + o bloco real


def test_readme_e_gravado_com_lf(tmp_path: Path) -> None:
    """Regressao: no Windows, write_text trocava o README inteiro para CRLF."""
    readme = tmp_path / "README.md"
    readme.write_bytes(b"# Projeto\n\nTexto.\n")

    atualizar_readme(readme, _df())

    assert b"\r\n" not in readme.read_bytes()


def test_salvar_csv_usa_lf(tmp_path: Path) -> None:
    destino = tmp_path / "saida.csv"

    salvar_csv(_df(), destino)

    assert b"\r\n" not in destino.read_bytes()
