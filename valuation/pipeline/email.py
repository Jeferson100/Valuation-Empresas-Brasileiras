"""Relatorio mensal por email (SMTP), com o CSV completo em anexo.

Duas regras guiam este modulo:

1. Sem credencial configurada o envio e um no-op com ``warning``. Assim rodar o
   pipeline localmente nunca depende de configurar SMTP.
2. A falta do CSV nao impede o alerta: se a coleta quebrou antes de gravar, o
   email sai como ``[FALHA]`` com o resumo de ``dados/erros.csv``.

O HTML usa CSS inline porque o Gmail descarta boa parte do que vem em
``<style>``.
"""

from __future__ import annotations

import argparse
import html as html_lib
import logging
import os
import smtplib
import ssl
from collections.abc import Hashable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path
from typing import Any

import pandas as pd

from ..domain.erros import Status

RAIZ = Path(__file__).resolve().parents[2]
log = logging.getLogger(__name__)

TOP_PADRAO = 20
ASSUNTO_OK = "Valuation {periodo} - {ok} ok / {total} tickers"
ASSUNTO_FALHA = "[FALHA] Valuation {periodo} - {motivo}"

COR_TEXTO = "#1f2328"
COR_SUAVE = "#57606a"
COR_BORDA = "#d0d7de"

#: Colunas do topo do email: (coluna no CSV, titulo exibido).
COLUNAS_TOP: tuple[tuple[str, str], ...] = (
    ("acao", "Acao"),
    ("setor", "Setor"),
    ("preco_atual", "Preco"),
    ("preco_alvo_p50", "Alvo P50"),
    ("upside_p50", "Upside"),
    ("margem_seguranca", "Margem"),
    ("recomendacao", "Recomendacao"),
    ("wacc", "WACC"),
)

#: Colunas formatadas como percentual.
COLUNAS_PERCENTUAL = frozenset({"upside_p50", "margem_seguranca", "wacc"})

#: Colunas formatadas como inteiro.
COLUNAS_INTEIRO = frozenset({"tickers"})


@dataclass(frozen=True)
class Credenciais:
    """Dados de conexao SMTP."""

    host: str
    porta: int
    usuario: str
    senha: str
    destinatario: str

    @classmethod
    def do_ambiente(cls, destinatario: str | None = None) -> Credenciais | None:
        """Le as credenciais do ambiente, ou ``None`` se faltar alguma."""
        usuario = (os.environ.get("SMTP_USUARIO") or "").strip()
        senha = (os.environ.get("SMTP_SENHA") or "").strip()
        destino = (destinatario or os.environ.get("EMAIL_PARA") or "").strip()

        faltando = [
            nome
            for nome, valor in (
                ("SMTP_USUARIO", usuario),
                ("SMTP_SENHA", senha),
                ("EMAIL_PARA", destino),
            )
            if not valor
        ]
        if faltando:
            log.warning("email desativado: faltam %s", ", ".join(faltando))
            return None

        host = (os.environ.get("SMTP_HOST") or "smtp.gmail.com").strip()
        porta = int(os.environ.get("SMTP_PORTA") or "587")
        return cls(host=host, porta=porta, usuario=usuario, senha=senha, destinatario=destino)


def _formatar(valor: object, coluna: str) -> str:
    """Formata um valor de celula para exibicao no email."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return "-"

    texto = str(valor).strip()
    if not texto or texto in {"<NA>", "nan", "None"}:
        return "-"

    if coluna in COLUNAS_PERCENTUAL:
        try:
            return f"{float(texto) * 100:.1f}%"
        except (TypeError, ValueError):
            return "-"

    if coluna in COLUNAS_INTEIRO:
        try:
            return f"{int(float(texto))}"
        except (TypeError, ValueError):
            return "-"

    try:
        numero = float(texto)
    except (TypeError, ValueError):
        return html_lib.escape(texto)

    return f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _tabela(registros: Sequence[Mapping[Any, Any]], colunas: tuple[tuple[str, str], ...]) -> str:
    """Tabela HTML com estilo inline."""
    estilo_th = (
        f"text-align:left;padding:6px 10px;border-bottom:2px solid {COR_BORDA};"
        f"font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:{COR_SUAVE};"
    )
    estilo_td = f"padding:6px 10px;border-bottom:1px solid {COR_BORDA};font-size:13px;"

    cabecalho = "".join(
        f'<th style="{estilo_th}">{html_lib.escape(titulo)}</th>' for _, titulo in colunas
    )
    corpo = []
    for registro in registros:
        celulas = "".join(
            f'<td style="{estilo_td}">{_formatar(registro.get(chave), chave)}</td>'
            for chave, _ in colunas
        )
        corpo.append(f"<tr>{celulas}</tr>")

    return (
        f'<table cellspacing="0" cellpadding="0" '
        f'style="border-collapse:collapse;width:100%;margin:8px 0 20px;">'
        f"<thead><tr>{cabecalho}</tr></thead><tbody>{''.join(corpo)}</tbody></table>"
    )


def _resumo_status(df: pd.DataFrame) -> str:
    contagem = df["status"].value_counts()
    registros = [
        {"status": status, "tickers": quantidade} for status, quantidade in contagem.items()
    ]
    return _tabela(registros, (("status", "Status"), ("tickers", "Tickers")))


def _top_por_upside(df: pd.DataFrame, top: int) -> list[dict[Hashable, Any]]:
    ok = df[(df["status"] == Status.OK.value) & df["preco_alvo_p50"].notna()]
    if ok.empty:
        return []
    colunas = [chave for chave, _ in COLUNAS_TOP]
    return ok.nlargest(top, "upside_p50")[colunas].to_dict(orient="records")


def _envelope(titulo: str, corpo: str) -> str:
    return (
        '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
        f'max-width:860px;color:{COR_TEXTO};">'
        f'<h2 style="margin:0 0 4px;font-size:20px;">{html_lib.escape(titulo)}</h2>'
        f'<p style="margin:0 0 18px;color:{COR_SUAVE};font-size:13px;">'
        f"Relatorio gerado em {date.today().strftime('%d/%m/%Y')}</p>"
        f"{corpo}"
        f'<p style="margin-top:24px;color:{COR_SUAVE};font-size:12px;line-height:1.5;">'
        "Precos-alvo em R$. Upside e margem de seguranca em percentual sobre o preco atual. "
        "O P25 e o cenario conservador da faixa: use-o como referencia antes do P50. "
        "Metodologia completa no METODOLOGIA.md do repositorio.</p>"
        "</div>"
    )


def montar_relatorio(
    df: pd.DataFrame | None,
    erros: pd.DataFrame | None = None,
    top: int = TOP_PADRAO,
    periodo: str | None = None,
) -> tuple[str, str]:
    """Monta assunto e HTML do email.

    ``df`` ausente ou vazio significa que a coleta nao chegou a gravar o CSV: o
    email vira um alerta de falha.
    """
    periodo = periodo or date.today().strftime("%Y-%m")

    if df is None or df.empty:
        motivo = "coleta nao gerou CSV"
        assunto = ASSUNTO_FALHA.format(periodo=periodo, motivo=motivo)
        partes = [
            "<p>A coleta mensal terminou sem gravar "
            "<code>dados/valores_valuations_acoes.csv</code>.</p>"
        ]
        if erros is not None and not erros.empty:
            registros = erros.head(30).to_dict(orient="records")
            colunas = tuple(
                (coluna, titulo)
                for coluna, titulo in (
                    ("acao", "Acao"),
                    ("etapa", "Etapa"),
                    ("excecao", "Excecao"),
                )
                if coluna in erros.columns
            )
            partes.append('<h3 style="font-size:15px;">Falhas registradas</h3>')
            partes.append(_tabela(registros, colunas))
        else:
            partes.append(
                "<p>Nenhum registro em <code>dados/erros.csv</code>: o erro "
                "provavelmente aconteceu antes da coleta, no carregamento das "
                "premisas. Veja o log da execucao no GitHub Actions.</p>"
            )
        return assunto, _envelope(f"Falha na coleta de {periodo}", "".join(partes))

    total = len(df)
    avaliados = int((df["status"] == Status.OK.value).sum())
    assunto = ASSUNTO_OK.format(periodo=periodo, ok=avaliados, total=total)

    partes = [
        f'<p style="font-size:14px;">{total} tickers no universo, '
        f"<b>{avaliados}</b> com <code>status=ok</code>.</p>"
    ]

    registros = _top_por_upside(df, top)
    partes.append(f'<h3 style="font-size:15px;">Top {top} por upside potencial</h3>')
    if registros:
        partes.append(_tabela(registros, COLUNAS_TOP))
    else:
        partes.append("<p>Nenhum ticker passou nos portoes de sanidade nesta execucao.</p>")

    partes.append('<h3 style="font-size:15px;">Cobertura por status</h3>')
    partes.append(_resumo_status(df))

    if erros is not None and not erros.empty:
        partes.append(
            f'<p style="font-size:13px;">{len(erros)} tickers falharam na coleta '
            "e estao listados no anexo <code>erros.csv</code>.</p>"
        )

    return assunto, _envelope(f"Valuation {periodo}", "".join(partes))


def enviar(
    credenciais: Credenciais,
    assunto: str,
    corpo_html: str,
    anexos: tuple[Path, ...] = (),
) -> bool:
    """Envia o email. Retorna ``False`` em qualquer falha, sem propagar."""
    mensagem = EmailMessage()
    mensagem["From"] = credenciais.usuario
    mensagem["To"] = credenciais.destinatario
    mensagem["Subject"] = assunto
    mensagem["Date"] = formatdate(localtime=True)
    mensagem.set_content("Ative a visualizacao HTML para ler este relatorio.")
    mensagem.add_alternative(corpo_html, subtype="html")

    for anexo in anexos:
        if not anexo.exists():
            continue
        mensagem.add_attachment(
            anexo.read_bytes(),
            maintype="text",
            subtype="csv",
            filename=anexo.name,
        )

    try:
        contexto = ssl.create_default_context()
        with smtplib.SMTP(credenciais.host, credenciais.porta, timeout=30) as smtp:
            smtp.starttls(context=contexto)
            smtp.login(credenciais.usuario, credenciais.senha)
            smtp.send_message(mensagem)
    except Exception as exc:
        log.error("falha ao enviar o email: %s", exc)
        return False

    log.info("relatorio enviado para %s", credenciais.destinatario)
    return True


def _ler_csv(caminho: Path | None) -> pd.DataFrame | None:
    if caminho is None or not caminho.exists():
        return None
    try:
        return pd.read_csv(caminho)
    except Exception as exc:
        log.warning("%s: nao foi possivel ler o CSV: %s", caminho, exc)
        return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Argumentos de linha de comando."""
    parser = argparse.ArgumentParser(description="Envia o relatorio de valuation por email")
    parser.add_argument(
        "--csv",
        type=Path,
        default=RAIZ / "dados" / "valores_valuations_acoes.csv",
        help="CSV com os resultados",
    )
    parser.add_argument(
        "--erros",
        type=Path,
        default=RAIZ / "dados" / "erros.csv",
        help="CSV de falhas de coleta (opcional)",
    )
    parser.add_argument("--para", help="destinatario (default: EMAIL_PARA)")
    parser.add_argument("--top", type=int, default=TOP_PADRAO)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="grava o HTML em --saida em vez de enviar",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=RAIZ / "dados" / "relatorio_email.html",
        help="arquivo do --dry-run",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Gera o relatorio e envia (ou grava, no ``--dry-run``)."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    df = _ler_csv(args.csv)
    erros = _ler_csv(args.erros)
    assunto, corpo = montar_relatorio(df, erros, top=args.top)

    if args.dry_run:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(corpo, encoding="utf-8")
        log.info("dry-run: %s gravado (assunto: %s)", args.saida, assunto)
        return 0

    credenciais = Credenciais.do_ambiente(destinatario=args.para)
    if credenciais is None:
        log.warning("email nao enviado: credenciais ausentes")
        return 0

    anexos = tuple(caminho for caminho in (args.csv, args.erros) if caminho.exists())
    return 0 if enviar(credenciais, assunto, corpo, anexos) else 1


__all__ = [
    "ASSUNTO_FALHA",
    "ASSUNTO_OK",
    "Credenciais",
    "enviar",
    "main",
    "montar_relatorio",
    "parse_args",
]

if __name__ == "__main__":
    raise SystemExit(main())
