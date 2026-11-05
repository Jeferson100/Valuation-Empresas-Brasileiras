"""Testes do fluxo de caixa descontado."""

from __future__ import annotations

import pytest

from valuation.domain.dcf import avaliar_dcf
from valuation.domain.erros import ErroValidacao, Status
from valuation.domain.premissas import PremissasDCF


def _premissas(**overrides) -> PremissasDCF:
    dados = dict(
        receita_base=1000.0,
        crescimento_receita=0.0,
        margem_ebit=0.20,
        aliquota=0.34,
        da_receita=0.05,
        capex_receita=0.05,
        nwc_receita=0.0,
        wacc=0.12,
        g_perpetuidade=0.0,
        anos=1,
        num_acoes=100.0,
    )
    dados.update(overrides)
    return PremissasDCF(**dados)


def test_fcff_identidade() -> None:
    linha = avaliar_dcf(_premissas()).tabela.iloc[0]
    esperado = linha["nopat"] + linha["da"] - linha["capex"] - linha["dnwc"]
    assert linha["fcff"] == pytest.approx(esperado)


def test_g_zero_forma_fechada() -> None:
    """FCFF = 1000*0.20*0.66 + 50 - 50 = 132; com g=0, EV = FCFF/WACC."""
    resultado = avaliar_dcf(_premissas())
    assert resultado.ev == pytest.approx(132.0 / 0.12, rel=1e-9)


def test_valor_terminal_usa_g_perpetuidade() -> None:
    """Regressao: o TV crescia pela receita historica (30% ao ano, para sempre)."""
    base = avaliar_dcf(_premissas(crescimento_receita=0.0, g_perpetuidade=0.03, anos=5))
    acelerado = avaliar_dcf(_premissas(crescimento_receita=0.30, g_perpetuidade=0.03, anos=5))
    assert acelerado.ev / base.ev < 6


def test_ponte_equity_sem_dupla_subtracao() -> None:
    resultado = avaliar_dcf(_premissas(divida_liquida=100.0, ativos_nao_operacionais=50.0))
    assert resultado.equity == pytest.approx(resultado.ev - 100.0 + 50.0)


def test_capital_de_giro_entra_como_variacao() -> None:
    primeiro = avaliar_dcf(_premissas(nwc_receita=0.10, nwc_base=100.0, anos=1)).tabela.iloc[0]
    assert primeiro["dnwc"] == pytest.approx(0.0)

    segundo = avaliar_dcf(
        _premissas(
            crescimento_receita=0.10,
            g_perpetuidade=0.10,
            nwc_receita=0.10,
            nwc_base=100.0,
            anos=2,
        )
    ).tabela.iloc[1]
    assert segundo["dnwc"] == pytest.approx(11.0)


def test_crescimento_faz_fade_ate_a_perpetuidade() -> None:
    """Sem o fade, um pico ciclico (-10% a.a.) seria projetado por 5 anos."""
    tabela = avaliar_dcf(_premissas(crescimento_receita=0.20, g_perpetuidade=0.03, anos=5)).tabela
    receitas = tabela["receita"].tolist()

    assert receitas[0] / 1000.0 - 1.0 == pytest.approx(0.20)
    assert receitas[4] / receitas[3] - 1.0 == pytest.approx(0.03)


def test_g_maior_que_wacc_levanta() -> None:
    with pytest.raises(ErroValidacao) as exc:
        avaliar_dcf(_premissas(g_perpetuidade=0.12))
    assert exc.value.status is Status.G_MAIOR_QUE_WACC


def test_numero_de_acoes_invalido_levanta() -> None:
    with pytest.raises(ErroValidacao) as exc:
        avaliar_dcf(_premissas(num_acoes=0.0))
    assert exc.value.status is Status.DADOS_INSUFICIENTES


def test_meio_ano_reduz_exposicao() -> None:
    cheio = avaliar_dcf(_premissas(anos=5, g_perpetuidade=0.02))
    meio = avaliar_dcf(_premissas(anos=5, g_perpetuidade=0.02, meio_ano=True))
    assert meio.ev > cheio.ev


def test_capex_acima_da_depreciacao_nao_penaliza_a_perpetuidade() -> None:
    """No estado estacionario CAPEX = D&A; so o periodo explicito muda."""
    base = avaliar_dcf(_premissas(anos=5, g_perpetuidade=0.03))
    investidor = avaliar_dcf(_premissas(anos=5, g_perpetuidade=0.03, capex_receita=0.20))
    assert investidor.vp_valor_terminal == pytest.approx(base.vp_valor_terminal)
    assert investidor.ev < base.ev


def test_preco_por_acao_dividido_pelo_numero_de_acoes() -> None:
    resultado = avaliar_dcf(_premissas())
    assert resultado.preco_por_acao == pytest.approx(resultado.equity / 100.0)


def test_crescimento_por_ano_substitui_o_fade() -> None:
    """Cenario de receita projetada: cada ano usa o valor do vetor."""
    tabela = avaliar_dcf(
        _premissas(
            crescimento_receita=0.20,
            crescimento_por_ano=(0.10, 0.05, 0.02),
            g_perpetuidade=0.02,
            anos=3,
        )
    ).tabela
    receitas = tabela["receita"].tolist()

    assert receitas[0] == pytest.approx(1100.0)
    assert receitas[1] == pytest.approx(1100.0 * 1.05)
    assert receitas[2] == pytest.approx(1100.0 * 1.05 * 1.02)


def test_crescimento_por_ano_incompleto_levanta() -> None:
    with pytest.raises(ErroValidacao) as exc:
        avaliar_dcf(_premissas(crescimento_por_ano=(0.05, 0.04), anos=3))
    assert exc.value.status is Status.DADOS_INSUFICIENTES


def test_crescimento_por_ano_menor_que_menos_cem_por_cento_levanta() -> None:
    with pytest.raises(ErroValidacao) as exc:
        avaliar_dcf(_premissas(crescimento_por_ano=(-1.5,), anos=1))
    assert exc.value.status is Status.NAO_AVALIAVEL
