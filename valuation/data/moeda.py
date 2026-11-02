"""Deteccao de moeda das demonstracoes contabeis.

O Yahoo Finance devolve as demonstracoes na moeda de reporte da companhia, mas o
preco e o market cap na moeda de negociacao. Para a maioria das empresas da B3
as duas coincidem; para companhias que reportam em dolar (Petrobras, Vale), nao.
Sem conversao, um FCFF em USD e descontado e dividido por um preco em BRL, o que
produz precos-alvo cerca de cinco vezes menores que o mercado.

O campo ``info["financialCurrency"]`` deveria resolver isso, mas o proprio Yahoo
as vezes o preenche com a moeda do preco. Por isso a deteccao combina o metadado
com uma verificacao de escala: razoes entre valores do ``info`` (ja na moeda do
preco) e do balanco (na moeda de reporte) proximas de 1 indicam mesma moeda;
razoes acima de 3 indicam conversao cambial.
"""

from __future__ import annotations

import math

from ..domain.series import linha
from .snapshot import SnapshotFinanceiro

#: Razao minima para tratar a diferenca como cambio, e nao como definicao
#: contabil distinta (ex.: divida de banco incluindo depositos).
RAZAO_MINIMA = 3.0
#: Razao maxima aceitavel. Acima disso o dado e inconsistente e nada e aplicado.
RAZAO_MAXIMA = 20.0
#: Diferenca relativa maxima entre duas metricas para confirmar o cambio.
TOLERANCIA = 0.35


def _numero(valor: object) -> float:
    """Converte para float, devolvendo NaN quando nao for possivel."""
    if valor is None:
        return float("nan")
    try:
        numero = float(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")
    return numero


def _razao(numerador: float, denominador: float) -> float | None:
    """Razao positiva e finita entre duas metricas, ou ``None``."""
    if not math.isfinite(numerador) or not math.isfinite(denominador) or denominador <= 0:
        return None
    if numerador <= 0:
        return None
    return numerador / denominador


def detectar_fator_cambio(
    snapshot: SnapshotFinanceiro,
    usar_heuristica: bool = True,
) -> tuple[float, str]:
    """Fator multiplicativo para levar as demonstracoes a moeda do preco.

    Retorna ``(fator, origem)``. ``fator == 1.0`` significa que nenhuma conversao
    e necessaria (ou que nao foi possivel detecta-la com seguranca).

    ``usar_heuristica=False`` desliga a verificacao de escala. Use em setores em
    que a definicao de divida do ``info`` difere muito do balanco (bancos), onde
    a razao entre os dois nao tem relacao com cambio.
    """
    info = snapshot.info
    moeda_financeira = str(info.get("financialCurrency") or "")
    moeda_preco = str(info.get("currency") or "")

    if not usar_heuristica:
        if moeda_financeira and moeda_preco and moeda_financeira != moeda_preco:
            return 1.0, f"cambio {moeda_financeira}->{moeda_preco} nao quantificado"
        return 1.0, "mesma moeda"

    candidatos: list[tuple[str, float]] = []

    # Divida bruta: o item mais comparavel entre info e balanco.
    divida_info = _numero(info.get("totalDebt"))
    divida_balanco = linha(snapshot.balance, "Total Debt", "TotalDebt")
    razao = _razao(divida_info, divida_balanco)
    if razao is not None:
        candidatos.append(("divida", razao))

    # Receita: TTM do info contra o ultimo ano fechado do demonstrativo.
    receita_info = _numero(info.get("totalRevenue"))
    receita_balanco = linha(snapshot.financials, "Total Revenue", "Operating Revenue")
    razao = _razao(receita_info, receita_balanco)
    if razao is not None:
        candidatos.append(("receita", razao))

    # Caixa: mais ruidoso (o info as vezes agrega aplicacoes financeiras).
    caixa_info = _numero(info.get("totalCash"))
    caixa_balanco = linha(
        snapshot.balance, "Cash And Cash Equivalents", "CashCashEquivalentsAndShortTermInvestments"
    )
    razao = _razao(caixa_info, caixa_balanco)
    if razao is not None:
        candidatos.append(("caixa", razao))

    if not candidatos:
        return 1.0, "sem evidencia"

    # Prioridade: divida (ponto no tempo, mesma origem nos dois lados), depois
    # receita e caixa. A mediana entre eles misturaria definicoes diferentes
    # (ex.: caixa do info inclui aplicacoes de curto prazo).
    origem, fator = candidatos[0]

    # Sem uma razao claramente de cambio, as demonstracoes estao na moeda do preco.
    if not (RAZAO_MINIMA <= fator <= RAZAO_MAXIMA):
        return 1.0, "mesma moeda"

    # Confirmacao: outra metrica precisa concordar com a divida. Em bancos a
    # definicao de divida difere tanto do balanco que a razao nao e cambio.
    if len(candidatos) > 1 and not any(
        abs(valor / fator - 1.0) <= TOLERANCIA for _, valor in candidatos[1:]
    ):
        return 1.0, f"escala inconsistente ({origem})"

    if moeda_financeira and moeda_preco and moeda_financeira != moeda_preco:
        return fator, f"cambio {moeda_financeira}->{moeda_preco}"
    return fator, f"escala ({origem})"


__all__ = ["RAZAO_MAXIMA", "RAZAO_MINIMA", "TOLERANCIA", "detectar_fator_cambio"]
