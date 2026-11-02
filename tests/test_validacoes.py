"""Testes dos portoes de sanidade e da recomendacao."""

from __future__ import annotations

from valuation.domain.erros import Status
from valuation.pipeline.validacoes import recomendacao, validar_resultado


def test_caso_valido() -> None:
    status, flags = validar_resultado(12.0, 10.0, 1, "Materiais Basicos", "dcf")
    assert status is Status.OK
    assert flags == []


def test_financeira_por_fcff_e_incompativel() -> None:
    status, _ = validar_resultado(12.0, 10.0, 1, "Financeiro", "dcf")
    assert status is Status.SETOR_INCOMPATIVEL


def test_financeira_por_ddm_e_valida() -> None:
    status, _ = validar_resultado(12.0, 10.0, 1, "Financeiro", "ddm")
    assert status is Status.OK


def test_preco_desatualizado() -> None:
    status, flags = validar_resultado(12.0, 10.0, 30, "Saude", "dcf")
    assert status is Status.PRECO_DESATUALIZADO
    assert flags


def test_preco_alvo_invalido() -> None:
    status, _ = validar_resultado(float("nan"), 10.0, 1, "Saude", "dcf")
    assert status is Status.NAO_AVALIAVEL


def test_preco_atual_invalido() -> None:
    status, _ = validar_resultado(12.0, 0.0, 1, "Saude", "dcf")
    assert status is Status.PRECO_DESATUALIZADO


def test_resultado_absurdo() -> None:
    """PCAR3 a R$ 5.674 contra R$ 3,12 precisa sair do ranking."""
    status, flags = validar_resultado(5674.0, 3.12, 1, "Consumo Cilico", "dcf")
    assert status is Status.RESULTADO_ABSURDO
    assert "upside" in flags[0]


def test_recomendacao_com_margem_de_seguranca() -> None:
    assert recomendacao(20.0, 10.0, 0.25) == "compra"  # 15,00 > 10,00
    assert recomendacao(12.0, 10.0, 0.25) == "neutro"  # 9,00 < 10,00, mas 12 > 10
    assert recomendacao(12.0, 10.0, 0.00) == "compra"  # sem margem, 12 > 10
    assert recomendacao(8.0, 10.0, 0.25) == "caro"
    assert recomendacao(float("nan"), 10.0, 0.25) == "n/d"
