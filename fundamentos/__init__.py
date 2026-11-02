"""Implementacao legada do valuation (mantida apenas por compatibilidade).

.. deprecated::
    Este pacote esta congelado. Ele contem os bugs corrigidos no pacote
    :mod:`valuation` (CAPM somando ``beta * Rm`` em vez de ``beta * (Rm - Rf)``,
    valor terminal crescendo pelo crescimento historico de receita, ponte para o
    equity subtraindo o passivo total, entre outros). Nenhum script do
    repositorio o utiliza mais.

    Use :mod:`valuation.domain` para a matematica e
    :mod:`valuation.pipeline` para a coleta e os relatorios::

        from valuation.pipeline.run import main
        main(["--tickers", "PETR4,VALE3"])

``ValuationGordon`` e um alias de ``ValuationModoloGordon`` (o nome original
tinha um erro de digitacao) para quem ja importava o nome antigo.
"""

from __future__ import annotations

import warnings

from .calculo_wacc import CalculoWACC
from .indicadores_financeiros import IndicadoresFinanceiros
from .necessidade_capital_giro import NecessidadeCapitalGiro
from .outros_ativos_nao_operecionais import OutrosAtivosNaoOperacionais
from .passivos_menos_divida import PassivoTotalMenosDivida
from .variacao_receita import VariacaoReceita
from .valuation_fluxo_caixa_descontado import ValuationFluxoCaixaDescontado
from .valuation_metodo_gordon import ValuationModoloGordon

#: Alias com a grafia correta do modelo de Gordon.
ValuationGordon = ValuationModoloGordon

warnings.warn(
    "O pacote 'fundamentos' esta obsoleto e contem bugs conhecidos. "
    "Use 'valuation.domain' e 'valuation.pipeline'.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "IndicadoresFinanceiros",
    "CalculoWACC",
    "VariacaoReceita",
    "OutrosAtivosNaoOperacionais",
    "PassivoTotalMenosDivida",
    "NecessidadeCapitalGiro",
    "ValuationFluxoCaixaDescontado",
    "ValuationModoloGordon",
    "ValuationGordon",
]
