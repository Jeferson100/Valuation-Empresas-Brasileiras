"""Camada de dados: coleta, cache e normalizacao."""

from __future__ import annotations

from .snapshot import SnapshotFinanceiro
from .universo import carregar_universo

__all__ = ["SnapshotFinanceiro", "carregar_universo"]
