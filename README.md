[![Rodando Valuation Acoes](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/actions/workflows/rodando_coleta.yml/badge.svg)](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/actions/workflows/rodando_coleta.yml)
[![Atualizar Tabela README](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/actions/workflows/atualizar_tabela_readme.yml/badge.svg)](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/actions/workflows/atualizar_tabela_readme.yml)
[![CI](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/actions/workflows/ci.yml/badge.svg)](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/actions/workflows/ci.yml)

# Descrição do Repositório

Aplicação para estimar o valor intrínseco de empresas brasileiras listadas na B3
a partir de dados públicos do Yahoo Finance e do IBGE. Cada ação recebe uma
**faixa de preço** (P25/P50/P75), uma recomendação com margem de segurança e um
status de qualidade do resultado.

Dois modelos são usados, escolhidos pelo setor da empresa:

- **Fluxo de Caixa Descontado (DCF/FCFF):** projeta o fluxo de caixa livre para a
  firma, desconta pelo WACC e chega ao valor por ação pela ponte do enterprise
  value para o equity. Aplicado a empresas não financeiras.
- **Dividendos Descontados (DDM) em dois estágios:** desconta dividendos
  projetados ao custo de capital próprio. Aplicado a bancos, seguradoras e
  bolsas, e publicado como informação secundária para as demais empresas que
  pagam dividendos.

O antigo modelo de Gordon de um estágio foi substituído: ele gerava preços
negativos sempre que `ROE × (1 − payout) ≥ Ke`, sem nenhuma guarda.

A metodologia completa — fórmulas, premissas, portões de sanidade e limitações —
está em **[METODOLOGIA.md](METODOLOGIA.md)**.

## Objetivos

- Estimar valor intrínseco com premissas explícitas e auditáveis.
- Separar o que é resultado confiável do que é artefato de dados ruins.
- Publicar uma faixa de valor, não um número único.
- Manter o histórico de execuções em CSV, com hash das premissas em cada linha.

## Estrutura do Repositório

```
valuation/
├── domain/            # matemática pura: sem rede, sem I/O
│   ├── premissas.py   # entradas validadas com Pydantic
│   ├── wacc.py        # CAPM, Hamada, custo da dívida
│   ├── dcf.py         # FCFF + valor terminal + ponte para o equity
│   ├── ddm.py         # dividendos em dois estágios
│   ├── sensibilidade.py  # grade WACC × g e percentis
│   ├── series.py      # utilidades de séries temporais e IPCA
│   └── erros.py       # Status e exceções de negócio
├── data/              # coleta, cache e normalização
│   ├── provider.py    # yfinance, uma requisição por ticker, cache parquet
│   ├── universo.py    # leitura do universo de tickers
│   ├── moeda.py       # detecção de demonstrações em moeda estrangeira
│   ├── ibge.py        # IPCA via SIDRA
│   └── snapshot.py    # snapshot imutável de um ticker
└── pipeline/          # orquestração, validação e relatórios
    ├── config.py      # premissas versionadas em config.yaml
    ├── indicadores.py # demonstrações contábeis -> premissas
    ├── validacoes.py  # portões de sanidade e recomendação
    ├── relatorio.py   # CSV e bloco do README
    └── run.py         # CLI e execução completa

config.yaml            # premissas de mercado e betas setoriais
tests/                 # 56 testes, sem rede
dados/setor.csv        # universo de tickers (setor e segmento)
dados/valores_valuations_acoes.csv   # saída do pipeline
fundamentos/           # implementação antiga, obsoleta (não é usada)
codigos_rodando/       # wrappers chamados pelos workflows
```

## Como executar

Requer Python 3.11 ou superior.

```bash
pip install -e ".[dev]"

# universo completo
python -m valuation.pipeline.run

# alguns tickers, com log detalhado
python -m valuation.pipeline.run --tickers PETR4,VALE3,ITUB4 -v

# sem rede, usando apenas o cache local
python -m valuation.pipeline.run --offline

# não mexer no README
python -m valuation.pipeline.run --sem-readme
```

Opções disponíveis: `--tickers`, `--limite`, `--universo`, `--config`, `--saida`,
`--cache`, `--readme`, `--offline`, `--sem-readme` e `-v/--verbose`.

Saídas:

- `dados/valores_valuations_acoes.csv` — uma linha por ticker, com status,
  premissas, faixa de preço e recomendação.
- `dados/erros.csv` — apenas tickers que falharam na coleta, com a exceção.
- `README.md` — bloco de resultados entre os marcadores HTML
  `VALUATION:START` e `VALUATION:END` (cada um em sua própria linha).

## Qualidade

```bash
make format      # ruff format + ruff check --fix
make lint        # ruff check
make typecheck   # mypy
make test        # pytest com cobertura
make all         # tudo acima
```

O workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda formato,
lint, tipos e testes em Python 3.11 e 3.12 a cada push e pull request.

## Automação

- **`rodando_coleta.yml`** — todo dia 1º, às 07:00 UTC (ou manualmente), roda o
  pipeline completo, publica `dados/erros.csv` como artefato e faz commit do CSV
  e do README.
- **`atualizar_tabela_readme.yml`** — roda depois que a coleta termina com
  sucesso e atualiza apenas o bloco de resultados do README.

## Interpretando o CSV

| Coluna | Descrição |
|---|---|
| `modelo` | `dcf` ou `ddm` |
| `status` | `ok`, `wacc_invalido`, `g_maior_que_wacc`, `setor_incompativel`, `dados_insuficientes`, `nao_avaliavel`, `sem_dividendos`, `preco_desatualizado`, `resultado_absurdo` |
| `flags` | detalhe legível do motivo do status |
| `preco_alvo_p25/p50/p75` | faixa de valor por ação (R$) |
| `upside_p50` | `p50 / preço_atual − 1` |
| `margem_seguranca` | margem exigida para a recomendação (25%) |
| `recomendacao` | `compra`, `neutro`, `caro` ou `n/d` |
| `wacc`, `ke`, `kd`, `beta_l` | custo de capital e beta realavancado |
| `g_perpetuidade`, `g_receita` | crescimento na perpetuidade e crescimento real histórico de receita (a projeção faz fade de um para o outro) |
| `aliquota` | alíquota efetiva de imposto usada |
| `fator_cambio` | fator aplicado às demonstrações para levá-las à moeda do preço (1,0 = mesma moeda) |
| `premissas_hash` | hash do `config.yaml` usado na execução |

Somente linhas com `status=ok` entram no ranking do README.

## Contribuições

Se você encontrar algum problema ou tiver sugestões de melhoria, sinta-se à
vontade para abrir uma issue ou enviar um pull request. Para mudanças de
metodologia, descreva o impacto esperado e inclua um teste que reproduza o caso.

## Licença

Este projeto está licenciado sob a Licença Apache 2.0 — veja o arquivo
[LICENSE](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/blob/main/LICENSE)
para mais detalhes.

## Resultados das Estimativas

<!-- VALUATION:START -->
### Top 20 por upside potencial (status `ok`)

| acao   | setor               |   preco_atual |   preco_alvo_p25 |   preco_alvo_p50 |   preco_alvo_p75 |   upside_p50 |   margem_seguranca | recomendacao   |   wacc |   g_perpetuidade |
|:-------|:--------------------|--------------:|-----------------:|-----------------:|-----------------:|-------------:|-------------------:|:---------------|-------:|-----------------:|
| GOAU4  | Materiais Básicos   |         11.25 |            19.31 |            21.31 |            23.83 |        89.46 |              25.00 | compra         |   0.15 |             0.03 |
| CYRE3  | Consumo Cíclico     |         16.65 |            23.69 |            26.43 |            29.81 |        58.71 |              25.00 | compra         |   0.16 |             0.03 |
| TRIS3  | Consumo Cíclico     |          4.10 |             5.87 |             6.28 |             6.77 |        53.15 |              25.00 | compra         |   0.15 |             0.03 |
| CMIG4  | Utilidade Pública   |         10.00 |            13.36 |            14.94 |            17.03 |        49.45 |              25.00 | compra         |   0.13 |             0.03 |
| CAMB3  | Consumo Cíclico     |          6.95 |             8.77 |             9.39 |            10.09 |        35.05 |              25.00 | neutro         |   0.17 |             0.03 |
| BRAP3  | Materiais Básicos   |         17.39 |            22.58 |            22.93 |            23.36 |        31.85 |              25.00 | neutro         |   0.17 |             0.03 |
| BGIP4  | Financeiro          |         32.01 |            37.90 |            40.71 |            43.41 |        27.17 |              25.00 | neutro         |   0.15 |             0.03 |
| BMKS3  | Consumo Cíclico     |        353.46 |           436.70 |           442.15 |           448.42 |        25.09 |              25.00 | neutro         |   0.17 |             0.03 |
| BRAP4  | Materiais Básicos   |         18.50 |            22.58 |            22.93 |            23.36 |        23.94 |              25.00 | neutro         |   0.17 |             0.03 |
| BBAS3  | Financeiro          |         16.41 |            18.59 |            20.31 |            22.25 |        23.78 |              25.00 | neutro         |   0.17 |             0.03 |
| CEBR6  | Utilidade Pública   |         26.50 |            30.19 |            32.09 |            34.54 |        21.08 |              25.00 | neutro         |   0.14 |             0.03 |
| BBDC3  | Financeiro          |         12.75 |            14.02 |            15.30 |            16.92 |        20.01 |              25.00 | neutro         |   0.19 |             0.03 |
| MDIA3  | Consumo não Cíclico |         15.34 |            17.09 |            18.24 |            19.58 |        18.88 |              25.00 | neutro         |   0.16 |             0.03 |
| BBDC4  | Financeiro          |         13.83 |            15.03 |            16.39 |            18.11 |        18.54 |              25.00 | neutro         |   0.19 |             0.03 |
| FESA4  | Materiais Básicos   |          5.04 |             5.13 |             5.51 |             5.94 |         9.27 |              25.00 | neutro         |   0.17 |             0.03 |
| LOGG3  | Financeiro          |         20.29 |            20.32 |            22.15 |            24.44 |         9.14 |              25.00 | neutro         |   0.12 |             0.03 |
| AZZA3  | Consumo Cíclico     |         14.13 |            13.25 |            15.14 |            17.52 |         7.15 |              25.00 | caro           |   0.18 |             0.03 |
| LREN3  | Consumo Cíclico     |          8.87 |             8.26 |             8.89 |             9.71 |         0.20 |              25.00 | caro           |   0.17 |             0.03 |
| JHSF3  | Consumo Cíclico     |          9.00 |             7.58 |             8.62 |             9.92 |        -4.25 |              25.00 | caro           |   0.16 |             0.03 |
| CMIG3  | Utilidade Pública   |         16.04 |            13.09 |            14.62 |            16.61 |        -8.85 |              25.00 | caro           |   0.13 |             0.03 |

**Cobertura:** 144 tickers no universo, 103 com `status=ok`.
Preços-alvo em R$; `upside` e `margem de segurança` em %.

| status | tickers |
|---|---:|
| `ok` | 103 |
| `nao_avaliavel` | 17 |
| `resultado_absurdo` | 12 |
| `wacc_invalido` | 10 |
| `dados_insuficientes` | 2 |

Resultado completo: [dados/valores_valuations_acoes.csv](dados/valores_valuations_acoes.csv) · Metodologia: [METODOLOGIA.md](METODOLOGIA.md)
<!-- VALUATION:END -->
