"""Testes do relatorio por email, sem rede (SMTP falso)."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pandas as pd
import pytest

from valuation.pipeline import email as modulo
from valuation.pipeline.email import Credenciais, enviar, montar_relatorio


@pytest.fixture
def resultado() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "acao": "PETR4",
                "setor": "Petroleo",
                "status": "ok",
                "preco_atual": 50.0,
                "preco_alvo_p50": 60.0,
                "upside_p50": 0.20,
                "margem_seguranca": 0.25,
                "recomendacao": "compra",
                "wacc": 0.155,
            },
            {
                "acao": "VALE3",
                "setor": "Mineracao",
                "status": "ok",
                "preco_atual": 60.0,
                "preco_alvo_p50": 54.0,
                "upside_p50": -0.10,
                "margem_seguranca": 0.25,
                "recomendacao": "caro",
                "wacc": 0.162,
            },
            {
                "acao": "ELET3",
                "setor": "Energia",
                "status": "nao_avaliavel",
                "preco_atual": None,
                "preco_alvo_p50": None,
                "upside_p50": None,
                "margem_seguranca": None,
                "recomendacao": "n/d",
                "wacc": None,
            },
        ]
    )


class _SMTPFalso:
    """Registra a conversa SMTP em vez de abrir conexao."""

    chamadas: ClassVar[dict[str, object]] = {}

    def __init__(self, host: str, porta: int, timeout: int | None = None) -> None:
        _SMTPFalso.chamadas = {"host": host, "porta": porta, "timeout": timeout}

    def __enter__(self) -> _SMTPFalso:
        return self

    def __exit__(self, *_args: object) -> bool:
        return False

    def starttls(self, context: object = None) -> None:
        _SMTPFalso.chamadas["tls"] = context is not None

    def login(self, usuario: str, senha: str) -> None:
        _SMTPFalso.chamadas["login"] = (usuario, senha)

    def send_message(self, mensagem: object) -> None:
        _SMTPFalso.chamadas["mensagem"] = mensagem


def test_assunto_traz_contagem_e_periodo(resultado: pd.DataFrame) -> None:
    assunto, corpo = montar_relatorio(resultado, periodo="2026-11")

    assert assunto == "Valuation 2026-11 - 2 ok / 3 tickers"
    assert "PETR4" in corpo
    assert "VALE3" in corpo


def test_top_ordena_por_upside(resultado: pd.DataFrame) -> None:
    _, corpo = montar_relatorio(resultado, top=1, periodo="2026-11")

    assert "PETR4" in corpo
    assert "VALE3" not in corpo


def test_percentuais_formatados_como_porcento(resultado: pd.DataFrame) -> None:
    _, corpo = montar_relatorio(resultado, top=1, periodo="2026-11")

    assert "20.0%" in corpo
    assert "15.5%" in corpo


def test_cobertura_por_status_aparece(resultado: pd.DataFrame) -> None:
    _, corpo = montar_relatorio(resultado, periodo="2026-11")

    assert "nao_avaliavel" in corpo


def test_sem_csv_vira_alerta_de_falha() -> None:
    assunto, corpo = montar_relatorio(None, periodo="2026-11")

    assert assunto == "[FALHA] Valuation 2026-11 - coleta nao gerou CSV"
    assert "sem gravar" in corpo


def test_falha_lista_os_erros_de_coleta() -> None:
    erros = pd.DataFrame([{"acao": "ELET3", "etapa": "coleta", "excecao": "404"}])

    assunto, corpo = montar_relatorio(None, erros, periodo="2026-11")

    assert assunto.startswith("[FALHA]")
    assert "ELET3" in corpo
    assert "404" in corpo


def test_sem_credenciais_nao_tenta_enviar(monkeypatch: pytest.MonkeyPatch) -> None:
    for variavel in ("SMTP_USUARIO", "SMTP_SENHA", "EMAIL_PARA"):
        monkeypatch.delenv(variavel, raising=False)

    assert Credenciais.do_ambiente() is None


def test_credenciais_vem_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_USUARIO", "eu@exemplo.com")
    monkeypatch.setenv("SMTP_SENHA", "senha-de-app")
    monkeypatch.setenv("EMAIL_PARA", "destino@exemplo.com")

    credenciais = Credenciais.do_ambiente()

    assert credenciais is not None
    assert credenciais.host == "smtp.gmail.com"
    assert credenciais.porta == 587
    assert credenciais.destinatario == "destino@exemplo.com"


def test_envio_monta_mensagem_com_anexo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo.smtplib, "SMTP", _SMTPFalso)

    anexo = tmp_path / "valores.csv"
    anexo.write_text("acao\nPETR4\n", encoding="utf-8")

    credenciais = Credenciais(
        host="smtp.gmail.com",
        porta=587,
        usuario="eu@exemplo.com",
        senha="senha",
        destinatario="destino@exemplo.com",
    )

    assert enviar(credenciais, "assunto", "<p>oi</p>", (anexo,)) is True

    mensagem = _SMTPFalso.chamadas["mensagem"]
    assert mensagem["To"] == "destino@exemplo.com"
    assert mensagem["Subject"] == "assunto"
    assert _SMTPFalso.chamadas["login"] == ("eu@exemplo.com", "senha")
    assert _SMTPFalso.chamadas["tls"] is True

    anexos = list(mensagem.iter_attachments())
    assert len(anexos) == 1
    assert anexos[0].get_filename() == "valores.csv"


def test_falha_de_smtp_nao_propaga(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class _SMTPQuebrado(_SMTPFalso):
        def login(self, usuario: str, senha: str) -> None:
            raise OSError("conexao recusada")

    monkeypatch.setattr(modulo.smtplib, "SMTP", _SMTPQuebrado)

    credenciais = Credenciais(
        host="smtp.gmail.com",
        porta=587,
        usuario="eu@exemplo.com",
        senha="senha",
        destinatario="destino@exemplo.com",
    )

    assert enviar(credenciais, "assunto", "<p>oi</p>") is False
