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
│   ├── previsao.py    # modelos de receita, encolhimento e backtest
│   ├── features.py    # colunas dos modelos e features extras
│   ├── modelos_ml.py  # XGBoost, LightGBM, CatBoost, MLP e LSTM/GRU
│   ├── sensibilidade.py  # grade WACC × g e percentis
│   ├── series.py      # utilidades de séries temporais e IPCA
│   └── erros.py       # Status e exceções de negócio
├── data/              # coleta, cache e normalização
│   ├── provider.py    # yfinance, uma requisição por ticker, cache parquet
│   ├── universo.py    # leitura do universo de tickers
│   ├── moeda.py       # detecção de demonstrações em moeda estrangeira
│   ├── ibge.py        # IPCA via SIDRA
│   ├── cvm.py         # painel histórico de receitas da CVM (DFP)
│   ├── macro.py       # séries anuais do BCB (SGS)
│   └── snapshot.py    # snapshot imutável de um ticker
└── pipeline/          # orquestração, validação e relatórios
    ├── config.py      # premissas versionadas em config.yaml
    ├── indicadores.py # demonstrações contábeis -> premissas
    ├── receita.py     # painel analítico e projeção de receita
    ├── validacoes.py  # portões de sanidade e recomendação
    ├── relatorio.py   # CSV e bloco do README
    └── run.py         # CLI e execução completa

config.yaml            # premissas de mercado e betas setoriais
tests/                 # 148 testes, sem rede
dados/setor.csv        # universo de tickers (setor e segmento)
dados/receitas_historicas.csv        # painel CVM versionado (2009–2025)
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

# pular o cenário de receita projetada
python -m valuation.pipeline.run --sem-previsao

# atualizar o painel histórico da CVM (uma vez por ano, ~220 MB)
python -m valuation.data.cvm --atualizar --anos 2010-2025
```

Opções disponíveis: `--tickers`, `--limite`, `--universo`, `--config`, `--saida`,
`--cache`, `--receitas`, `--readme`, `--offline`, `--sem-readme`,
`--sem-previsao` e `-v/--verbose`.

Saídas:

- `dados/valores_valuations_acoes.csv` — uma linha por ticker, com status,
  premissas, faixa de preço, recomendação e o cenário de receita projetada.
- `dados/erros.csv` — apenas tickers que falharam na coleta, com a exceção.
- `dados/projecoes_receita.csv` — crescimento projetado por ticker.
- `dados/backtest_resumo.csv` — MAPE de cada modelo de receita.
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

## Relatório por email

A coleta mensal envia um relatório HTML com o resumo por status, o top 20 por
upside e o CSV completo em anexo. Se a execução falhar, o email sai como
`[FALHA]` com o resumo de `dados/erros.csv`.

Para ativar, crie três *secrets* em **Settings → Secrets and variables →
Actions**:

| Secret | Conteúdo |
|---|---|
| `SMTP_USUARIO` | conta que envia (Gmail) |
| `SMTP_SENHA` | senha de app de 16 caracteres |
| `EMAIL_PARA` | destinatário do relatório |

A senha de app exige verificação em duas etapas ativa e é gerada em
[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) —
a senha normal da conta não funciona por SMTP. Sem os três secrets o envio vira
um no-op com `warning`, então o pipeline continua funcionando.

Para ver o relatório sem enviar nada:

```bash
python -m valuation.pipeline.email --dry-run
# grava dados/relatorio_email.html
```

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
| `modelo_receita` | modelo do cenário de receita: `fundamentos`, `macro`, `AR`, `setor` ou `historico` |
| `crescimento_receita_ajustado` | crescimento real do primeiro ano usado no segundo DCF |
| `peso_empresa` | peso da tendência própria da empresa no encolhimento (0 a 1) |
| `preco_receita_p25/p50/p75` | faixa do **segundo DCF**, alimentado pela receita projetada (R$) |
| `upside_receita_p50`, `recomendacao_receita` | upside e recomendação do segundo DCF |
| `status_receita`, `flags_receita` | status do segundo DCF; uma falha aqui não altera o valuation oficial |
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

| acao   |   setor |   preco_atual |   preco_alvo_p25 |   preco_alvo_p50 |   preco_alvo_p75 |   upside_p50 |   margem_seguranca | recomendacao   |   wacc |   g_perpetuidade |
|:-------|--------:|--------------:|-----------------:|-----------------:|-----------------:|-------------:|-------------------:|:---------------|-------:|-----------------:|
| ESPA3  |     nan |          5.17 |             8.58 |             9.70 |            10.93 |        87.59 |              25.00 | compra         |   0.17 |             0.03 |
| ITUB3  |     nan |         44.89 |            82.83 |            83.74 |            84.80 |        86.54 |              25.00 | compra         |   0.20 |             0.03 |
| BPAC3  |     nan |         23.66 |            43.56 |            44.11 |            44.77 |        86.45 |              25.00 | compra         |   0.18 |             0.03 |
| MTRE3  |     nan |          3.13 |             5.47 |             5.83 |             6.29 |        86.16 |              25.00 | compra         |   0.14 |             0.03 |
| DEXP4  |     nan |          7.33 |            11.03 |            11.76 |            12.65 |        60.40 |              25.00 | compra         |   0.16 |             0.03 |
| DEXP3  |     nan |          7.39 |            11.03 |            11.75 |            12.64 |        59.03 |              25.00 | compra         |   0.16 |             0.03 |
| VLID3  |     nan |         14.58 |            21.64 |            23.07 |            24.83 |        58.23 |              25.00 | compra         |   0.16 |             0.03 |
| RNEW3  |     nan |          0.84 |             1.11 |             1.29 |             1.51 |        54.05 |              25.00 | neutro         |   0.19 |             0.03 |
| RNEW4  |     nan |          0.84 |             1.11 |             1.29 |             1.51 |        54.05 |              25.00 | neutro         |   0.19 |             0.03 |
| MTSA4  |     nan |         41.10 |            59.76 |            62.30 |            65.31 |        51.59 |              25.00 | compra         |   0.16 |             0.03 |
| SYNE3  |     nan |          2.90 |             3.90 |             4.20 |             4.56 |        44.93 |              25.00 | compra         |   0.18 |             0.03 |
| TELB3  |     nan |         11.85 |            16.66 |            17.15 |            17.70 |        44.75 |              25.00 | compra         |   0.17 |             0.03 |
| TRIS3  |     nan |          4.40 |             5.85 |             6.26 |             6.74 |        42.21 |              25.00 | neutro         |   0.15 |             0.03 |
| POMO3  |     nan |          3.41 |             4.31 |             4.73 |             5.25 |        38.68 |              25.00 | neutro         |   0.16 |             0.03 |
| CALI3  |     nan |         28.11 |            35.30 |            38.67 |            42.32 |        37.58 |              25.00 | neutro         |   0.15 |             0.03 |
| BOBR4  |     nan |          1.59 |             2.02 |             2.18 |             2.36 |        37.07 |              25.00 | neutro         |   0.20 |             0.03 |
| SOJA3  |     nan |          6.08 |             7.53 |             8.30 |             9.24 |        36.47 |              25.00 | neutro         |   0.16 |             0.03 |
| CYRE3  |     nan |         19.29 |            23.55 |            26.26 |            29.60 |        36.11 |              25.00 | neutro         |   0.16 |             0.03 |
| CGRA4  |     nan |         22.15 |            28.34 |            29.96 |            31.97 |        35.26 |              25.00 | neutro         |   0.16 |             0.03 |
| CGRA3  |     nan |         22.40 |            28.34 |            29.96 |            31.96 |        33.73 |              25.00 | neutro         |   0.16 |             0.03 |

**Cobertura:** 376 tickers no universo, 199 com `status=ok`.
Preços-alvo em R$; `upside` e `margem de segurança` em %.

| status | tickers |
|---|---:|
| `ok` | 199 |
| `nao_avaliavel` | 77 |
| `resultado_absurdo` | 61 |
| `wacc_invalido` | 33 |
| `dados_insuficientes` | 5 |
| `preco_desatualizado` | 1 |

Resultado completo: [dados/valores_valuations_acoes.csv](dados/valores_valuations_acoes.csv) · Metodologia: [METODOLOGIA.md](METODOLOGIA.md)
<!-- VALUATION:END -->
