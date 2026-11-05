"""Painel historico de demonstracoes financeiras da CVM (DFP).

Fonte oficial e gratuita:
    https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_YYYY.zip

Cada pacote anual traz o exercicio corrente e o anterior, entao 2010-2026 cobre
2009-2026: ~17 transicoes por empresa, contra as 4 do yfinance.

O download completo tem ~220 MB, entao ele nao roda no pipeline mensal. O painel
e gerado por ``python -m valuation.data.cvm --atualizar`` e versionado em
``dados/receitas_historicas.csv`` (~1 MB). O run mensal apenas le o CSV.
"""

from __future__ import annotations

import argparse
import io
import logging
import shutil
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

import pandas as pd

from ..domain.erros import ErroDados

log = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[2]

URL_DFP = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{ano}.zip"
URL_FCA = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip"

# Contas padronizadas da CVM. O codigo e estavel entre 2010 e 2026.
CONTAS_DRE = {
    "3.01": "receita",
    "3.05": "ebit",
    "3.07": "lucro_antes_imposto",
    "3.08": "imposto",
    "3.09": "lucro_liquido",
}
CONTAS_BPA = {"1": "ativo_total"}
CONTAS_BPP = {"2.03": "patrimonio_liquido"}

COLUNAS_CSV = [
    "CNPJ_CIA",
    "DT_FIM_EXERC",
    "ORDEM_EXERC",
    "CD_CONTA",
    "VL_CONTA",
    "ESCALA_MOEDA",
    "VERSAO",
]

ESCALA = {"MIL": 1_000.0, "UNIDADE": 1.0}

COLUNAS_PAINEL = [
    "receita",
    "ebit",
    "lucro_antes_imposto",
    "imposto",
    "lucro_liquido",
    "ativo_total",
    "patrimonio_liquido",
]


def baixar(url: str, destino: Path, forcar: bool = False) -> Path:
    """Baixa ``url`` para ``destino``, reaproveitando o arquivo existente."""
    if destino.exists() and destino.stat().st_size > 0 and not forcar:
        return destino

    destino.parent.mkdir(parents=True, exist_ok=True)
    log.info("baixando %s", url)
    temporario = destino.with_name(destino.name + ".part")
    try:
        requisicao = urllib.request.Request(url, headers={"User-Agent": "valuation-br/1.0"})
        with (
            urllib.request.urlopen(requisicao, timeout=300) as resposta,
            temporario.open("wb") as arquivo,
        ):
            shutil.copyfileobj(resposta, arquivo)
        temporario.replace(destino)
    except Exception as exc:
        temporario.unlink(missing_ok=True)
        raise ErroDados(f"falha ao baixar {url}: {exc}") from exc
    return destino


def _ler_csv(pacote: Path, nome: str, colunas: list[str] | None = None) -> pd.DataFrame:
    """Le um CSV de dentro do ZIP, sem extrair o pacote inteiro."""
    with zipfile.ZipFile(pacote) as pacote_zip:
        if nome not in pacote_zip.namelist():
            return pd.DataFrame()
        bruto = pacote_zip.read(nome)
    return pd.read_csv(
        io.BytesIO(bruto),
        sep=";",
        encoding="latin-1",
        dtype=str,
        usecols=colunas,
    )


def _bloco(
    pacote: Path,
    nome: str,
    mapa: dict[str, str],
    ano_arquivo: int,
    tipo: str,
) -> pd.DataFrame:
    """Extrai as contas de um arquivo no formato longo (cnpj, ano, campo, valor)."""
    dados = _ler_csv(pacote, nome, COLUNAS_CSV)
    if dados.empty or "CD_CONTA" not in dados.columns:
        return pd.DataFrame()

    dados = dados[dados["CD_CONTA"].isin(mapa)]
    if dados.empty:
        return pd.DataFrame()

    # Cada arquivo traz o exercicio corrente e o anterior. "ULTIMO" evita
    # duplicar a mesma conta com o comparativo do ano anterior.
    ordem = dados["ORDEM_EXERC"].astype(str).str.upper()
    dados = dados[ordem.str.endswith("LTIMO")]
    if dados.empty:
        return pd.DataFrame()

    ano = pd.to_datetime(dados["DT_FIM_EXERC"], errors="coerce").dt.year
    escala = dados["ESCALA_MOEDA"].map(ESCALA).fillna(1.0)
    valor = pd.to_numeric(dados["VL_CONTA"], errors="coerce") * escala

    bloco = pd.DataFrame(
        {
            "cnpj": dados["CNPJ_CIA"].to_numpy(),
            "ano": ano.to_numpy(),
            "campo": dados["CD_CONTA"].map(mapa).to_numpy(),
            "valor": valor.to_numpy(),
            "versao": pd.to_numeric(dados["VERSAO"], errors="coerce").fillna(0).to_numpy(),
            "arquivo": ano_arquivo,
            # 1 = consolidado, 0 = individual. O consolidado vence quando existe.
            "tipo": 1 if tipo == "con" else 0,
        }
    )
    bloco = bloco.dropna(subset=["ano", "valor"])
    bloco["ano"] = bloco["ano"].astype(int)
    return bloco


def extrair_ano(ano: int, cache: Path) -> pd.DataFrame:
    """Le DRE, BPA e BPP (consolidado e individual) de um pacote anual."""
    pacote = cache / f"dfp{ano}.zip"
    if not pacote.exists():
        log.warning("pacote de %d ausente: %s", ano, pacote)
        return pd.DataFrame()

    partes = []
    for tipo in ("con", "ind"):
        for nome, mapa in (
            (f"dfp_cia_aberta_DRE_{tipo}_{ano}.csv", CONTAS_DRE),
            (f"dfp_cia_aberta_BPA_{tipo}_{ano}.csv", CONTAS_BPA),
            (f"dfp_cia_aberta_BPP_{tipo}_{ano}.csv", CONTAS_BPP),
        ):
            partes.append(_bloco(pacote, nome, mapa, ano, tipo))
    return pd.concat([p for p in partes if not p.empty], ignore_index=True)


def mapa_tickers(ano: int, cache: Path) -> pd.DataFrame:
    """Mapa CNPJ -> codigo de negociacao, a partir do formulario FCA."""
    pacote = cache / f"fca{ano}.zip"
    ano_pacote = ano
    if not pacote.exists():
        # O FCA do ano corrente pode nao existir ainda; recua ate achar.
        for candidato in (ano, ano - 1, ano - 2):
            alternativo = cache / f"fca{candidato}.zip"
            if alternativo.exists():
                pacote = alternativo
                ano_pacote = candidato
                break
        else:
            pacote = baixar(URL_FCA.format(ano=ano), cache / f"fca{ano}.zip")

    bruto = _ler_csv(pacote, f"fca_cia_aberta_valor_mobiliario_{ano_pacote}.csv")
    if bruto.empty or "CNPJ_Companhia" not in bruto.columns:
        raise ErroDados(f"FCA sem mapa de tickers: {pacote}")

    mapa = (
        bruto[["CNPJ_Companhia", "Codigo_Negociacao"]]
        .dropna()
        .drop_duplicates()
        .rename(columns={"CNPJ_Companhia": "cnpj", "Codigo_Negociacao": "ticker"})
    )
    mapa["ticker"] = mapa["ticker"].astype(str).str.upper().str.strip()
    return mapa.reset_index(drop=True)


def expandir_units(mapa: pd.DataFrame, universo: set[str]) -> pd.DataFrame:
    """Mapeia KLBN3/KLBN4 -> KLBN11 e afins, quando so a unit esta listada."""
    conhecidos = set(mapa["ticker"])
    extras = []
    for ticker in universo:
        if ticker in conhecidos or not ticker or ticker[-1] not in "3456":
            continue
        unit = ticker[:-1] + "11"
        if unit not in conhecidos:
            continue
        linha = mapa[mapa["ticker"] == unit].iloc[0]
        extras.append({"cnpj": linha["cnpj"], "ticker": ticker})
    if not extras:
        return mapa
    return pd.concat([mapa, pd.DataFrame(extras)], ignore_index=True).drop_duplicates(
        ["cnpj", "ticker"]
    )


def montar_painel(
    anos: list[int],
    cache: Path,
    universo: set[str] | None = None,
) -> pd.DataFrame:
    """Concatena os anos, resolve reafirmacoes e devolve o painel ticker-ano."""
    partes = [extrair_ano(ano, cache) for ano in anos]
    validas = [p for p in partes if not p.empty]
    if not validas:
        raise ErroDados("nenhum pacote da CVM pode ser lido")
    tudo = pd.concat(validas, ignore_index=True)
    if tudo.empty:
        raise ErroDados("nenhum pacote da CVM pode ser lido")

    # Ordem de precedencia:
    #   1. arquivo mais recente (reafirmacao de exercicio anterior vence);
    #   2. consolidado vence individual;
    #   3. maior VERSAO dentro do arquivo.
    tudo = tudo.sort_values(["arquivo", "tipo", "versao"])
    tudo = tudo.drop_duplicates(["cnpj", "ano", "campo"], keep="last")

    painel = tudo.pivot_table(
        index=["cnpj", "ano"],
        columns="campo",
        values="valor",
        aggfunc="first",
    ).reset_index()
    painel.columns.name = None

    for coluna in COLUNAS_PAINEL:
        if coluna not in painel.columns:
            painel[coluna] = float("nan")

    mapa = mapa_tickers(max(anos), cache)
    if universo:
        mapa = expandir_units(mapa, universo)

    painel = painel.merge(mapa, on="cnpj", how="inner")
    if universo:
        painel = painel[painel["ticker"].isin(universo)]

    painel["origem"] = "cvm"
    painel = painel.sort_values(["ticker", "ano"]).drop_duplicates(["ticker", "ano"], keep="last")
    return painel.reset_index(drop=True)


def carregar_painel(caminho: Path | str) -> pd.DataFrame:
    """Le o painel versionado; falha alto se ele nao existir."""
    caminho = Path(caminho)
    if not caminho.exists():
        raise ErroDados(f"painel historico ausente: {caminho}")
    return pd.read_csv(caminho)


def main(argv: list[str] | None = None) -> int:
    """Gera ``dados/receitas_historicas.csv`` a partir dos pacotes da CVM."""
    parser = argparse.ArgumentParser(description="Painel historico de receitas da CVM")
    parser.add_argument(
        "--atualizar",
        action="store_true",
        help="baixa os pacotes antes de montar (uma vez por ano)",
    )
    parser.add_argument("--cache", type=Path, default=RAIZ / "dados" / "cache" / "cvm")
    parser.add_argument("--saida", type=Path, default=RAIZ / "dados" / "receitas_historicas.csv")
    parser.add_argument("--universo", type=Path, default=RAIZ / "dados" / "setor.csv")
    parser.add_argument("--anos", default=f"2010-{date.today().year}")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    inicio, _, fim = args.anos.partition("-")
    anos = list(range(int(inicio), int(fim or inicio) + 1))

    if args.atualizar:
        for ano in anos:
            try:
                baixar(URL_DFP.format(ano=ano), args.cache / f"dfp{ano}.zip")
            except ErroDados as exc:
                # O pacote do ano corrente so existe no ano seguinte. Falhar
                # aqui nao deve impedir a atualizacao dos anos disponiveis.
                log.warning("pacote DFP de %d indisponivel: %s", ano, exc)
        try:
            baixar(URL_FCA.format(ano=anos[-1]), args.cache / f"fca{anos[-1]}.zip")
        except ErroDados as exc:
            # mapa_tickers recua para um FCA anterior ja baixado.
            log.warning("FCA de %d indisponivel: %s", anos[-1], exc)

    universo = pd.read_csv(args.universo).rename(columns={"tic": "acao", "Setor": "setor"})
    universo["acao"] = universo["acao"].astype(str).str.upper().str.strip()
    tickers = set(universo["acao"])

    painel = montar_painel(anos, args.cache, tickers)
    painel = painel.merge(
        universo[["acao", "setor"]], left_on="ticker", right_on="acao", how="left"
    ).drop(columns=["acao"])

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    painel.to_csv(args.saida, index=False, encoding="utf-8", lineterminator="\n")

    cobertura = painel.groupby("ano")["ticker"].nunique()
    log.info(
        "painel gravado: %d linhas, %d tickers, %s",
        len(painel),
        painel["ticker"].nunique(),
        args.saida,
    )
    for ano_cobertura, quantidade in cobertura.items():
        log.info("  %d: %d tickers", int(str(ano_cobertura)), quantidade)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "baixar",
    "carregar_painel",
    "expandir_units",
    "extrair_ano",
    "main",
    "mapa_tickers",
    "montar_painel",
]
