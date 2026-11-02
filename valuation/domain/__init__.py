"""Camada de dominio: matematica pura, sem rede e sem I/O."""

from __future__ import annotations

from .dcf import ResultadoDCF, avaliar_dcf
from .ddm import ResultadoDDM, avaliar_ddm
from .erros import ErroDados, ErroValidacao, Status
from .premissas import PremissasDCF, PremissasDDM, PremissasWACC
from .wacc import ResultadoWACC, calcular_wacc

__all__ = [
    "ErroDados",
    "ErroValidacao",
    "PremissasDCF",
    "PremissasDDM",
    "PremissasWACC",
    "ResultadoDCF",
    "ResultadoDDM",
    "ResultadoWACC",
    "Status",
    "avaliar_dcf",
    "avaliar_ddm",
    "calcular_wacc",
]
