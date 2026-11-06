"""Testes da leitura das series do BCB, com cache local (sem rede)."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from valuation.data.macro import (
    _baixar_intervalo,
    baixar_focus,
    baixar_sgs,
    carregar_macro,
)
from valuation.domain.erros import ErroDados


def _cache(cache: Path, codigo: int, valores: list[tuple[str, str]]) -> None:
    pasta = cache / "macro"
    pasta.mkdir(parents=True, exist_ok=True)
    texto = json.dumps([{"data": data, "valor": valor} for data, valor in valores])
    (pasta / f"sgs{codigo}.json").write_text(texto, encoding="utf-8")


def _series_anuais(cache: Path) -> None:
    _cache(
        cache,
        433,
        [("01/01/2023", "0,50"), ("01/02/2023", "0,50"), ("01/01/2024", "1,00")],
    )
    _cache(
        cache,
        24364,
        [("01/01/2023", "100"), ("01/07/2023", "110"), ("01/01/2024", "121")],
    )
    _cache(
        cache,
        3695,
        [("01/01/2023", "5,00"), ("01/01/2024", "5,50")],
    )
    _cache(
        cache,
        432,
        [("01/01/2023", "1,00"), ("01/01/2024", "1,00")],
    )


def test_sgs_parseia_virgula_decimal(tmp_path: Path) -> None:
    _cache(tmp_path, 433, [("01/01/2024", "0,25"), ("01/02/2024", "0,75")])
    serie = baixar_sgs(433, tmp_path, offline=True)
    assert list(serie) == pytest.approx([0.25, 0.75])


def test_offline_sem_cache_levanta(tmp_path: Path) -> None:
    with pytest.raises(ErroDados):
        baixar_sgs(433, tmp_path, offline=True)


def test_carregar_macro_anualiza(tmp_path: Path) -> None:
    _series_anuais(tmp_path)
    macro = carregar_macro(tmp_path, offline=True)

    assert macro.loc[2023, "ipca"] == pytest.approx(1.005 * 1.005 - 1.0)
    assert macro.loc[2023, "ibc_br"] == pytest.approx(105.0)
    assert macro.loc[2023, "cambio"] == pytest.approx(5.0)
    assert math.isnan(macro.loc[2023, "d_ibc_br"])  # primeira diferenca nao existe
    assert macro.loc[2024, "d_ibc_br"] == pytest.approx(math.log(121.0 / 105.0))


def test_carregar_macro_sem_ipca_retorna_vazio(tmp_path: Path) -> None:
    """Sem IPCA nao ha deflator: a macro inteira fica indisponivel."""
    _cache(tmp_path, 24364, [("01/01/2024", "100")])
    assert carregar_macro(tmp_path, offline=True).empty


def test_carregar_macro_sem_serie_secundaria_segue_com_ipca(tmp_path: Path) -> None:
    """IBC-Br/cambio/selic sao opcionais; so o IPCA e essencial."""
    _cache(tmp_path, 433, [("01/01/2024", "0,50")])
    macro = carregar_macro(tmp_path, offline=True)

    assert not macro.empty
    assert macro.loc[2024, "ipca"] == pytest.approx(0.005)
    assert "ibc_br" not in macro.columns


def test_baixar_intervalo_quebra_em_janelas(monkeypatch) -> None:
    """O SGS recusa intervalos longos; o download vai em blocos de 5 anos."""
    chamadas: list[str] = []

    class Resposta:
        def read(self) -> bytes:
            return b"[]"

    def urlopen(requisicao, timeout=60):
        chamadas.append(requisicao.full_url)
        return Resposta()

    monkeypatch.setattr("valuation.data.macro.urllib.request.urlopen", urlopen)
    texto = _baixar_intervalo(432, "01/01/2008", "31/12/2025")

    assert texto == "[]"
    assert len(chamadas) == 4
    assert "dataInicial=01/01/2008" in chamadas[0]
    assert "dataFinal=31/12/2025" in chamadas[-1]


def _cache_focus(cache: Path, codigo: int, valores: list[tuple[str, str]]) -> None:
    pasta = cache / "macro"
    pasta.mkdir(parents=True, exist_ok=True)
    texto = json.dumps([{"data": data, "valor": valor} for data, valor in valores])
    (pasta / f"focus{codigo}.json").write_text(texto, encoding="utf-8")


def test_baixar_focus_parseia_virgula_decimal(tmp_path: Path) -> None:
    _cache_focus(tmp_path, 117706, [("01/01/2024", "0,40"), ("01/02/2024", "0,45")])
    serie = baixar_focus(117706, tmp_path, offline=True)
    assert list(serie) == pytest.approx([0.40, 0.45])


def test_carregar_macro_com_focus_inclui_expectativas(tmp_path: Path) -> None:
    """Sem Focus as colunas *_exp nao devem aparecer."""
    _cache(tmp_path, 433, [("01/01/2024", "0,50")])
    _cache_focus(
        tmp_path,
        117706,
        [("01/01/2024", "0,40"), ("01/07/2024", "0,45")],
    )
    _cache_focus(
        tmp_path,
        117709,
        [("01/01/2024", "2,0"), ("01/07/2024", "2,1")],
    )

    macro = carregar_macro(tmp_path, offline=True, usar_focus=True)

    assert not macro.empty
    assert "ipca_exp" in macro.columns
    assert "pib_exp" in macro.columns
    assert macro.loc[2024, "ipca_exp"] == pytest.approx(0.425)


def test_carregar_macro_sem_focus_nao_inclui_expectativas(tmp_path: Path) -> None:
    """Quando usar_focus=False, as colunas *_exp ficam de fora."""
    _cache(tmp_path, 433, [("01/01/2024", "0,50")])
    _cache_focus(
        tmp_path,
        117706,
        [("01/01/2024", "0,40")],
    )

    macro = carregar_macro(tmp_path, offline=True, usar_focus=False)

    assert not macro.empty
    assert "ipca_exp" not in macro.columns
    assert "pib_exp" not in macro.columns


def test_baixar_focus_offline_sem_cache_levanta(tmp_path: Path) -> None:
    with pytest.raises(ErroDados):
        baixar_focus(117706, tmp_path, offline=True)
