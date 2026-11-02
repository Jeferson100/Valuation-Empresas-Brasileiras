"""Testes da traducao de demonstracoes em indicadores."""

from __future__ import annotations

import pandas as pd
import pytest

from valuation.domain.erros import ErroValidacao, Status
from valuation.pipeline.config import Config
from valuation.pipeline.indicadores import (
    aliquota_efetiva,
    dps_base,
    montar_indicadores,
    num_acoes,
    premissas_dcf,
    premissas_ddm,
)


def test_aliquota_efetiva_respeita_teto(financials: pd.DataFrame) -> None:
    assert aliquota_efetiva(financials, "Materiais Basicos") == pytest.approx(0.34)


def test_aliquota_ignora_anos_de_prejuizo() -> None:
    """Regressao: dividir imposto por EBIT gerava aliquotas de 3.796%."""
    datas = pd.to_datetime(["2021-12-31", "2022-12-31"])
    dados = pd.DataFrame(
        {
            datas[0]: [100.0, 10.0],
            datas[1]: [-500.0, -50.0],
        },
        index=["Tax Provision", "Pretax Income"],
    )
    assert aliquota_efetiva(dados, "Consumo Cilico") == pytest.approx(0.34)


def test_aliquota_financeira_usa_teto_de_45() -> None:
    assert aliquota_efetiva(pd.DataFrame(), "Financeiro") == pytest.approx(0.45)


def test_dps_base_usa_mediana_dos_anos_completos() -> None:
    ano = pd.Timestamp.today().year
    datas = [pd.Timestamp(f"{ano - deslocamento}-06-01") for deslocamento in (5, 4, 3, 2, 0)]
    dividendos = pd.Series([0.10, 0.45, 0.50, 0.55, 0.99], index=datas)
    # Ultimos tres anos completos: 0,45 / 0,50 / 0,55 -> mediana 0,50.
    # O ano corrente (0,99) e o ano mais antigo (0,10) ficam fora.
    assert dps_base(dividendos) == pytest.approx(0.50)


def test_dps_base_sem_dividendos() -> None:
    assert dps_base(pd.Series(dtype=float)) == 0.0


def test_num_acoes_usa_info(snapshot) -> None:
    assert num_acoes(snapshot) == pytest.approx(1000.0)


def test_num_acoes_sem_info_levanta(snapshot) -> None:
    from dataclasses import replace

    sem_info = replace(snapshot, info={})
    with pytest.raises(ErroValidacao) as exc:
        num_acoes(sem_info)
    assert exc.value.status is Status.DADOS_INSUFICIENTES


def test_montar_indicadores(snapshot) -> None:
    indicadores = montar_indicadores(snapshot, "Materiais Basicos", None, Config())

    assert indicadores.receita_base == pytest.approx(1331.0)
    assert indicadores.margem_ebit == pytest.approx(0.20, abs=1e-3)
    assert indicadores.aliquota == pytest.approx(0.34, abs=1e-3)
    assert indicadores.divida_bruta == pytest.approx(560.0)
    assert indicadores.caixa == pytest.approx(230.0)
    assert indicadores.divida_liquida == pytest.approx(330.0)
    assert indicadores.crescimento_receita == pytest.approx(0.10, abs=1e-6)
    assert indicadores.dps_base > 0


def test_premissas_dcf_e_ddm(snapshot) -> None:
    config = Config()
    indicadores = montar_indicadores(snapshot, "Materiais Basicos", None, config)

    dcf = premissas_dcf(indicadores, 0.16, config)
    assert dcf.wacc == pytest.approx(0.16)
    assert dcf.g_perpetuidade == pytest.approx(config.g_perpetuidade)

    ddm = premissas_ddm(indicadores, 0.18, config)
    assert ddm.dps_base == pytest.approx(indicadores.dps_base)
    assert 0.0 <= ddm.g1 <= 0.15


def test_premissas_ddm_sem_dividendo(snapshot) -> None:
    from dataclasses import replace

    sem_dividendos = replace(snapshot, dividends=pd.Series(dtype=float))
    indicadores = montar_indicadores(sem_dividendos, "Materiais Basicos", None, Config())

    with pytest.raises(ErroValidacao) as exc:
        premissas_ddm(indicadores, 0.15, Config())
    assert exc.value.status is Status.SEM_DIVIDENDOS
