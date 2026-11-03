"""Erros de negocio e status de resultado.

Um ticker nunca "desaparece": ou entra no CSV com um ``Status``, ou entra em
``dados/erros.csv`` com a excecao que o derrubou.
"""

from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    """Estado de uma avaliacao. Sempre presente na saida."""

    OK = "ok"
    WACC_INVALIDO = "wacc_invalido"
    G_MAIOR_QUE_WACC = "g_maior_que_wacc"
    SETOR_INCOMPATIVEL = "setor_incompativel"
    DADOS_INSUFICIENTES = "dados_insuficientes"
    NAO_AVALIAVEL = "nao_avaliavel"
    SEM_DIVIDENDOS = "sem_dividendos"
    PRECO_DESATUALIZADO = "preco_desatualizado"
    RESULTADO_ABSURDO = "resultado_absurdo"


class ErroValidacao(Exception):
    """Erro de negocio esperado: vira uma linha com ``status`` no CSV."""

    def __init__(self, status: Status, detalhe: str) -> None:
        self.status = status
        self.detalhe = detalhe
        super().__init__(f"{status.value}: {detalhe}")


class ErroDados(Exception):
    """Falha de coleta (rede, ticker inexistente, demonstracoes vazias)."""


__all__ = ["ErroDados", "ErroValidacao", "Status"]
