"""CLI e orquestracao da coleta de valuation.

Uso:
    python -m valuation.pipeline.run
    python -m valuation.pipeline.run --tickers PETR4,VALE3 -v
    python -m valuation.pipeline.run --offline --limite 10
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from ..data.ibge import carregar_indice_ipca
from ..data.moeda import detectar_fator_cambio
from ..data.provider import YFinanceProvider
from ..data.snapshot import SnapshotFinanceiro
from ..data.universo import carregar_universo, eh_financeiro
from ..domain.dcf import avaliar_dcf
from ..domain.ddm import avaliar_ddm
from ..domain.erros import ErroDados, ErroValidacao, Status
from ..domain.premissas import PremissasWACC
from ..domain.sensibilidade import (
    faixa_preco,
    grade_sensibilidade,
    grade_sensibilidade_ddm,
)
from ..domain.wacc import calcular_wacc, custo_divida
from .config import Config, carregar_config
from .indicadores import (
    Indicadores,
    montar_indicadores,
    premissas_dcf,
    premissas_ddm,
)
from .relatorio import atualizar_readme, salvar_csv
from .validacoes import MODELO_DCF, MODELO_DDM, recomendacao, validar_resultado

RAIZ = Path(__file__).resolve().parents[2]
log = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Argumentos de linha de comando."""
    parser = argparse.ArgumentParser(description="Valuation de empresas brasileiras")
    parser.add_argument("--tickers", help="lista separada por virgula (default: universo)")
    parser.add_argument("--limite", type=int, help="processa apenas os N primeiros")
    parser.add_argument("--universo", type=Path, default=RAIZ / "dados" / "setor.csv")
    parser.add_argument("--config", type=Path, default=RAIZ / "config.yaml")
    parser.add_argument(
        "--saida", type=Path, default=RAIZ / "dados" / "valores_valuations_acoes.csv"
    )
    parser.add_argument("--cache", type=Path, default=RAIZ / "dados" / "cache")
    parser.add_argument("--readme", type=Path, default=RAIZ / "README.md")
    parser.add_argument("--offline", action="store_true", help="usa apenas o cache")
    parser.add_argument("--sem-readme", action="store_true", help="nao atualiza o README")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _dias_uteis_desde(data: date | None, hoje: date) -> int:
    if data is None:
        return 999
    return int(np.busday_count(data.isoformat(), hoje.isoformat()))


def _market_cap(snapshot: SnapshotFinanceiro, indicadores: Indicadores) -> float:
    valor = snapshot.info.get("marketCap")
    try:
        numero = float(valor) if valor is not None else float("nan")
    except (TypeError, ValueError):
        numero = float("nan")
    if math.isfinite(numero) and numero > 0:
        return numero
    return indicadores.preco_atual * indicadores.num_acoes


def _linha_base(
    acao: str,
    setor: str,
    segmento: str,
    snapshot: SnapshotFinanceiro,
    config: Config,
) -> dict[str, object]:
    return {
        "acao": acao,
        "setor": setor,
        "segmento": segmento,
        "as_of": snapshot.as_of.isoformat(),
        "data_coleta": date.today().isoformat(),
        "premissas_hash": config.hash_premissas(),
        "margem_seguranca": config.margem_seguranca,
        "rf": config.rf,
        "erp": config.erp,
        "g_perpetuidade": config.g_perpetuidade,
    }


def avaliar_acao(
    acao: str,
    setor: str,
    segmento: str,
    provider: YFinanceProvider,
    config: Config,
    indice_ipca: pd.Series | None,
) -> dict[str, object]:
    """Avalia um ticker e devolve a linha do CSV (sempre com status)."""
    snapshot = provider.obter(f"{acao}.SA")
    financeira = eh_financeiro(setor)
    modelo = MODELO_DDM if financeira else MODELO_DCF

    fator_cambio, origem_cambio = detectar_fator_cambio(snapshot, usar_heuristica=not financeira)
    if fator_cambio == 1.0 and "nao quantificado" in origem_cambio:
        raise ErroValidacao(Status.DADOS_INSUFICIENTES, origem_cambio)
    if fator_cambio != 1.0:
        log.info(
            "%s: demonstracoes convertidas para a moeda do preco (fator %.4f, %s)",
            acao,
            fator_cambio,
            origem_cambio,
        )
    indicadores = montar_indicadores(snapshot, setor, indice_ipca, config, fator_cambio)

    linha = _linha_base(acao, setor, segmento, snapshot, config)
    linha.update(
        {
            "preco_atual": indicadores.preco_atual,
            "fator_cambio": indicadores.fator_cambio,
            "g_receita": indicadores.crescimento_receita,
            "margem_ebit": indicadores.margem_ebit,
            "capex_receita": indicadores.capex_receita,
            "da_receita": indicadores.da_receita,
            "nwc_receita": indicadores.nwc_receita,
            "aliquota": indicadores.aliquota,
            "receita_base": indicadores.receita_base,
            "divida_bruta": indicadores.divida_bruta,
            "caixa": indicadores.caixa,
            "divida_liquida": indicadores.divida_liquida,
            "ativos_nao_operacionais": indicadores.ativos_nao_operacionais,
            "num_acoes": indicadores.num_acoes,
        }
    )

    try:
        kd = custo_divida(indicadores.despesa_juros, indicadores.divida_bruta, config.rf)
        resultado_wacc = calcular_wacc(
            PremissasWACC(
                rf=config.rf,
                erp=config.erp,
                beta_u=config.beta_do_setor(setor),
                divida=indicadores.divida_bruta,
                patrimonio=_market_cap(snapshot, indicadores),
                aliquota=indicadores.aliquota,
                kd=kd,
                alavancar_beta=not financeira,
            )
        )
        linha.update(
            {
                "wacc": resultado_wacc.wacc,
                "ke": resultado_wacc.ke,
                "kd": resultado_wacc.kd,
                "beta_l": resultado_wacc.beta_l,
            }
        )

        if financeira:
            ddm = premissas_ddm(indicadores, resultado_wacc.ke, config)
            preco_ddm = avaliar_ddm(ddm).preco
            grade = grade_sensibilidade_ddm(ddm)
            p25, p50, p75 = faixa_preco(grade)
            linha["preco_ddm"] = preco_ddm
        else:
            dcf = premissas_dcf(indicadores, resultado_wacc.wacc, config)
            resultado_dcf = avaliar_dcf(dcf)
            grade = grade_sensibilidade(dcf)
            p25, p50, p75 = faixa_preco(grade)
            linha["preco_dcf"] = resultado_dcf.preco_por_acao
            linha["ev"] = resultado_dcf.ev
            linha["equity_value"] = resultado_dcf.equity
    except ErroValidacao as exc:
        linha.update(
            {
                "modelo": modelo,
                "status": exc.status.value,
                "flags": exc.detalhe,
                "preco_alvo_p25": float("nan"),
                "preco_alvo_p50": float("nan"),
                "preco_alvo_p75": float("nan"),
                "recomendacao": "n/d",
            }
        )
        return linha

    # Modelo secundario: DDM para quem paga dividendos, sem afetar o status.
    if not financeira and indicadores.dps_base > 0:
        with contextlib.suppress(ErroValidacao):
            linha["preco_ddm"] = avaliar_ddm(
                premissas_ddm(indicadores, resultado_wacc.ke, config)
            ).preco

    dias = _dias_uteis_desde(snapshot.data_ultimo_pregao, date.today())
    status, flags = validar_resultado(
        preco_alvo_p50=p50,
        preco_atual=indicadores.preco_atual,
        dias_ultimo_pregao=dias,
        setor=setor,
        modelo=modelo,
        upside_max=config.upside_max,
    )

    linha.update(
        {
            "modelo": modelo,
            "status": status.value,
            "flags": "; ".join(flags),
            "preco_alvo_p25": p25,
            "preco_alvo_p50": p50,
            "preco_alvo_p75": p75,
            "upside_p50": p50 / indicadores.preco_atual - 1.0,
            "recomendacao": recomendacao(p25, indicadores.preco_atual, config.margem_seguranca),
        }
    )
    return linha


def main(argv: list[str] | None = None) -> int:
    """Executa a coleta completa e grava CSV, erros e README."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = carregar_config(args.config)
    universo = carregar_universo(args.universo)

    if args.tickers:
        desejados = {t.strip().upper() for t in args.tickers.split(",") if t.strip()}
        universo = universo[universo["acao"].isin(desejados)]
    if args.limite:
        universo = universo.head(args.limite)

    if universo.empty:
        log.error("universo vazio apos os filtros")
        return 2

    provider = YFinanceProvider(
        cache_dir=args.cache,
        ttl_dias=config.ttl_cache_dias,
        offline=args.offline,
    )
    indice_ipca = carregar_indice_ipca(args.cache, offline=args.offline)
    if indice_ipca is None:
        log.warning("IPCA indisponivel: crescimento de receita sera nominal")

    linhas: list[dict[str, object]] = []
    erros: list[dict[str, object]] = []
    total = len(universo)

    for posicao, registro in enumerate(universo.itertuples(index=False), start=1):
        acao = str(registro.acao)
        try:
            linhas.append(
                avaliar_acao(
                    acao=acao,
                    setor=str(registro.setor),
                    segmento=str(getattr(registro, "segmento", "") or ""),
                    provider=provider,
                    config=config,
                    indice_ipca=indice_ipca,
                )
            )
        except ErroValidacao as exc:
            linhas.append(
                {
                    "acao": acao,
                    "setor": str(registro.setor),
                    "segmento": str(getattr(registro, "segmento", "") or ""),
                    "as_of": date.today().isoformat(),
                    "data_coleta": date.today().isoformat(),
                    "premissas_hash": config.hash_premissas(),
                    "modelo": MODELO_DDM if eh_financeiro(str(registro.setor)) else MODELO_DCF,
                    "status": exc.status.value,
                    "flags": exc.detalhe,
                    "recomendacao": "n/d",
                }
            )
            log.info("[%d/%d] %s: %s", posicao, total, acao, exc)
        except ErroDados as exc:
            erros.append(
                {
                    "acao": acao,
                    "etapa": "coleta",
                    "excecao": str(exc),
                    "data_coleta": date.today().isoformat(),
                }
            )
            log.error("[%d/%d] %s: %s", posicao, total, acao, exc)
        except Exception as exc:  # bug inesperado: registra e segue
            erros.append(
                {
                    "acao": acao,
                    "etapa": "calculo",
                    "excecao": repr(exc),
                    "data_coleta": date.today().isoformat(),
                }
            )
            log.exception("[%d/%d] %s: erro inesperado", posicao, total, acao)

        if posicao % 25 == 0:
            salvar_csv(pd.DataFrame(linhas), args.saida)
            log.info("checkpoint: %d/%d processados", posicao, total)

    resultado = pd.DataFrame(linhas)
    salvar_csv(resultado, args.saida)

    if erros:
        caminho_erros = args.saida.parent / "erros.csv"
        pd.DataFrame(erros).to_csv(caminho_erros, index=False, encoding="utf-8")
        log.warning("%d tickers falharam na coleta: %s", len(erros), caminho_erros)

    if not args.sem_readme:
        atualizar_readme(args.readme, resultado, top=config.top_readme)

    avaliados = int((resultado["status"] == Status.OK.value).sum()) if not resultado.empty else 0
    log.info(
        "concluido: %d linhas, %d ok, %d erros de coleta",
        len(resultado),
        avaliados,
        len(erros),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
