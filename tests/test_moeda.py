"""Testes da deteccao de moeda das demonstracoes."""

from __future__ import annotations

from dataclasses import replace

import pytest

from valuation.data.moeda import detectar_fator_cambio
from valuation.pipeline.config import Config
from valuation.pipeline.indicadores import montar_indicadores


def test_mesma_moeda_nao_converte(snapshot) -> None:
    info = {
        **snapshot.info,
        "totalDebt": 560.0,
        "totalCash": 230.0,
        "totalRevenue": 1331.0,
    }
    fator, _ = detectar_fator_cambio(replace(snapshot, info=info))
    assert fator == pytest.approx(1.0)


def test_demonstracoes_em_dolar_sao_convertidas(snapshot) -> None:
    """Regressao: Petrobras e Vale reportam em USD e o preco e em BRL."""
    cambio = 5.4
    info = {
        **snapshot.info,
        "totalDebt": 560.0 * cambio,
        "totalCash": 230.0 * cambio,
        "totalRevenue": 1331.0 * cambio,
    }
    fator, origem = detectar_fator_cambio(replace(snapshot, info=info))

    assert fator == pytest.approx(cambio)
    assert "escala" in origem


def test_diferenca_de_definicao_nao_e_tratada_como_cambio(snapshot) -> None:
    """Banco: o 'totalDebt' do info inclui depositos, mas a moeda e a mesma."""
    info = {
        **snapshot.info,
        "totalDebt": 1120.0,  # 2x o balanco, sem cambio
        "totalCash": 460.0,
        "totalRevenue": 1160.0,
    }
    fator, _ = detectar_fator_cambio(replace(snapshot, info=info))
    assert fator == pytest.approx(1.0)


def test_razoes_inconsistentes_nao_convertem(snapshot) -> None:
    """BBAS3: a divida do info e 6,6x o balanco, mas a receita esta na mesma escala."""
    info = {
        **snapshot.info,
        "totalDebt": 560.0 * 6.58,
        "totalCash": 230.0 * 1.47,
        "totalRevenue": 1331.0 * 0.51,
    }
    fator, origem = detectar_fator_cambio(replace(snapshot, info=info))

    assert fator == pytest.approx(1.0)
    assert "inconsistente" in origem


def test_heuristica_pode_ser_desligada(snapshot) -> None:
    info = {**snapshot.info, "totalDebt": 560.0 * 5.4}
    fator, origem = detectar_fator_cambio(replace(snapshot, info=info), usar_heuristica=False)
    assert fator == pytest.approx(1.0)
    assert origem == "mesma moeda"


def test_metadado_de_moeda_tem_prioridade_na_origem(snapshot) -> None:
    info = {
        **snapshot.info,
        "financialCurrency": "USD",
        "currency": "BRL",
        "totalDebt": 560.0 * 5.0,
        "totalCash": 230.0 * 5.0,
        "totalRevenue": 1331.0 * 5.0,
    }
    fator, origem = detectar_fator_cambio(replace(snapshot, info=info))
    assert fator == pytest.approx(5.0)
    assert "USD->BRL" in origem


def test_indicadores_aplicam_o_fator_nos_valores_monetarios(snapshot) -> None:
    sem_cambio = montar_indicadores(snapshot, "Materiais Basicos", None, Config())
    com_cambio = montar_indicadores(snapshot, "Materiais Basicos", None, Config(), fator_cambio=5.0)

    assert com_cambio.receita_base == pytest.approx(sem_cambio.receita_base * 5.0)
    assert com_cambio.divida_bruta == pytest.approx(sem_cambio.divida_bruta * 5.0)
    assert com_cambio.caixa == pytest.approx(sem_cambio.caixa * 5.0)
    assert com_cambio.ativos_nao_operacionais == pytest.approx(
        sem_cambio.ativos_nao_operacionais * 5.0
    )
    # Razoes e preco nao mudam.
    assert com_cambio.margem_ebit == pytest.approx(sem_cambio.margem_ebit)
    assert com_cambio.nwc_receita == pytest.approx(sem_cambio.nwc_receita)
    assert com_cambio.preco_atual == pytest.approx(sem_cambio.preco_atual)
    assert com_cambio.fator_cambio == pytest.approx(5.0)
