"""Provedor de dados com cache em parquet e retry com backoff.

Antes: cada classe de calculo instanciava ``yf.Ticker`` e chamava
``get_balancesheet(freq="yearly")`` de 5 a 7 vezes. Eram ~35 requisicoes por acao
(~5.700 por execucao), o que causava lentidao, rate limit e perda silenciosa de
tickers. Agora e uma requisicao por ticker, reaproveitada do cache.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from ..domain.erros import ErroDados
from .snapshot import SnapshotFinanceiro

log = logging.getLogger(__name__)


class _DadosVazios(RuntimeError):
    """Resposta valida do provedor, porem sem dados: falha retentavel."""


class YFinanceProvider:
    """Coleta e cacheia snapshots financeiros."""

    def __init__(
        self,
        cache_dir: Path | str,
        ttl_dias: int = 1,
        offline: bool = False,
        tentativas: int = 3,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.ttl = timedelta(days=ttl_dias)
        self.offline = offline
        self.tentativas = tentativas

    def obter(self, ticker: str) -> SnapshotFinanceiro:
        """Retorna o snapshot, do cache quando fresco."""
        pasta = self.cache_dir / ticker
        if pasta.exists():
            snapshots = sorted(pasta.glob("*/snapshot.json"))
            if snapshots:
                caminho = snapshots[-1]
                if self._fresco(caminho):
                    return self._carregar(caminho.parent)

        if self.offline:
            raise ErroDados(f"modo offline e sem cache para {ticker}")

        return self._baixar(ticker)

    def _baixar(self, ticker: str) -> SnapshotFinanceiro:
        ultimo_erro: Exception | None = None

        for tentativa in range(1, self.tentativas + 1):
            try:
                ativo = yf.Ticker(ticker)
                info = self._info(ativo)
                financials = ativo.financials
                balance = ativo.balance_sheet
                cashflow = ativo.cashflow

                # Dados vazios quase sempre sao transitorios (throttling ou
                # payload incompleto), entao entram no mesmo retry da rede.
                if financials is None or financials.empty:
                    raise _DadosVazios(f"{ticker}: demonstracoes financeiras vazias")

                historico = ativo.history(period="5y", auto_adjust=True)
                if historico is None or historico.empty or "Close" not in historico:
                    raise _DadosVazios(f"{ticker}: historico de precos vazio")

                dividendos = ativo.dividends
                if dividendos is None:
                    dividendos = pd.Series(dtype=float)

                snapshot = SnapshotFinanceiro(
                    ticker=ticker,
                    as_of=date.today(),
                    info=info,
                    financials=financials,
                    balance=balance if balance is not None else pd.DataFrame(),
                    cashflow=cashflow if cashflow is not None else pd.DataFrame(),
                    history=historico["Close"].astype(float),
                    dividends=dividendos.astype(float),
                )
                self._salvar(snapshot)
                return snapshot

            except ErroDados:
                raise
            except Exception as exc:  # rede, rate limit, payload inesperado
                ultimo_erro = exc
                log.warning(
                    "%s: tentativa %d/%d falhou: %s",
                    ticker,
                    tentativa,
                    self.tentativas,
                    exc,
                )
                if tentativa < self.tentativas:
                    time.sleep(2**tentativa)

        raise ErroDados(f"{ticker}: falhou apos {self.tentativas} tentativas: {ultimo_erro}")

    @staticmethod
    def _info(ativo: yf.Ticker) -> dict[str, Any]:
        try:
            info = ativo.info
        except Exception as exc:  # pragma: no cover - depende da rede
            log.warning("%s: info indisponivel: %s", ativo.ticker, exc)
            return {}
        return dict(info or {})

    def _fresco(self, caminho: Path) -> bool:
        idade = datetime.now() - datetime.fromtimestamp(caminho.stat().st_mtime)
        return idade < self.ttl

    def _salvar(self, snapshot: SnapshotFinanceiro) -> None:
        destino = self.cache_dir / snapshot.ticker / snapshot.as_of.isoformat()
        destino.mkdir(parents=True, exist_ok=True)

        snapshot.financials.to_parquet(destino / "financials.parquet")
        snapshot.balance.to_parquet(destino / "balance.parquet")
        snapshot.cashflow.to_parquet(destino / "cashflow.parquet")
        snapshot.history.to_frame("close").to_parquet(destino / "history.parquet")
        snapshot.dividends.to_frame("dividend").to_parquet(destino / "dividends.parquet")

        meta = {"ticker": snapshot.ticker, "as_of": snapshot.as_of.isoformat()}
        (destino / "snapshot.json").write_text(json.dumps(meta), encoding="utf-8")
        (destino / "info.json").write_text(json.dumps(snapshot.info, default=str), encoding="utf-8")

    def _carregar(self, pasta: Path) -> SnapshotFinanceiro:
        meta = json.loads((pasta / "snapshot.json").read_text(encoding="utf-8"))
        info = json.loads((pasta / "info.json").read_text(encoding="utf-8"))

        return SnapshotFinanceiro(
            ticker=meta["ticker"],
            as_of=date.fromisoformat(meta["as_of"]),
            info=info,
            financials=pd.read_parquet(pasta / "financials.parquet"),
            balance=pd.read_parquet(pasta / "balance.parquet"),
            cashflow=pd.read_parquet(pasta / "cashflow.parquet"),
            history=pd.read_parquet(pasta / "history.parquet")["close"],
            dividends=pd.read_parquet(pasta / "dividends.parquet")["dividend"],
        )


__all__ = ["YFinanceProvider"]
