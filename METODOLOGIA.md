# Metodologia

Este documento descreve como o repositório transforma demonstrações contábeis em
um preço-alvo por ação, quais premissas usa e onde o resultado **não** deve ser
levado a sério. As premissas numéricas vivem em [`config.yaml`](config.yaml); o
hash desse arquivo vai para o CSV, de modo que cada linha é rastreável.

## 1. Universo e escolha do modelo

O universo é o arquivo [`dados/setor.csv`](dados/setor.csv) (tickers da B3 com
setor e segmento). O modelo é escolhido pelo setor:

| Setor | Modelo | Justificativa |
|---|---|---|
| `Financeiro` (bancos, seguradoras, bolsas) | **DDM** (dividendos descontados) | O conceito de FCFF não se aplica: dívida é insumo operacional e o capital de giro não é definível. |
| Demais setores | **DCF** (FCFF) | Fluxo de caixa livre para a firma, descontado pelo WACC. |

Empresas financeiras avaliadas por FCFF recebem `status=setor_incompativel` e
saem do ranking. Essa é uma regra dura, não um aviso.

## 2. Premissas de mercado

| Premissa | Valor padrão | Origem |
|---|---|---|
| Taxa livre de risco (`rf`) | 10,5% a.a. | Swap DI 360×12 (BM&F), média recente |
| Prêmio de risco (`erp`) | 7,5% a.a. | ERP maduro ≈ 4,5% + prêmio de risco país Brasil ≈ 3,0% |
| Crescimento na perpetuidade (`g`) | 3,0% a.a. | Meta de inflação de longo prazo (IPCA) |
| Horizonte explícito | 5 anos | `config.yaml` |
| Beta desalavancado | por setor | Referências de Damodaran ajustadas; fallback 0,85 |

O beta desalavancado (`beta_u`) é definido por setor em `config.yaml` e
realavancado com a estrutura de capital da própria empresa (equação de Hamada):

```
beta_l = beta_u × [1 + (1 − t) × D/E]
```

## 3. Custo médio ponderado de capital (WACC)

```
Ke   = Rf + beta_l × ERP
Kd   = |despesa de juros| / dívida bruta média      (limitado a [Rf, Rf + 10 p.p.])
E    = valor de mercado do equity (market cap)
D    = dívida bruta
V    = E + D
WACC = (E/V) × Ke + (D/V) × Kd × (1 − t)
```

Regras:

- **Nunca** há fallback silencioso para `V = 1`. Se `E ≤ 0` ou `E + D ≤ 0`, a
  linha recebe `status=wacc_invalido`.
- WACC fora do intervalo aberto `(0%; 50%)` também vira `wacc_invalido`. Isso
  captura dados corrompidos (por exemplo, market cap em outra moeda) sem
  contaminar o ranking.
- Em **bancos e seguradoras** o beta não é realavancado (`beta_l = beta_u`):
  depósitos e captações não são alavancagem financeira no sentido de Hamada, e
  tratá-los como tal elevaria o `Ke` de forma artificial.
- `beta_l > 5` ou `Ke ≥ 100%` indica estrutura de capital degenerada (market cap
  mínimo contra dívida enorme, típico de empresa em recuperação judicial) e vira
  `wacc_invalido` em vez de contaminar o ranking.
- A alíquota `t` é a alíquota efetiva histórica (seção 5).

## 4. Fluxo de caixa descontado (FCFF)

Para cada ano `t = 1..N` do horizonte explícito:

```
g_t         = g_receita + (g − g_receita) × (t − 1)/(N − 1)
Receita_t   = Receita_{t−1} × (1 + g_t)
EBIT_t      = Receita_t × margem_EBIT
NOPAT_t     = EBIT_t × (1 − t)
D&A_t       = Receita_t × (D&A/Receita)
CAPEX_t     = Receita_t × (CAPEX/Receita)
NWC_t       = Receita_t × (NWC/Receita)
ΔNWC_t      = NWC_t − NWC_{t−1}
FCFF_t      = NOPAT_t + D&A_t − CAPEX_t − ΔNWC_t
VP(FCFF_t)  = FCFF_t / (1 + WACC)^t
```

O crescimento faz **fade linear**: vale o histórico no ano 1 e converge para `g`
no último ano. Sem isso, uma empresa que veio de um pico cíclico (−10% a.a.)
seria projetada em queda por todo o horizonte e, de repente, cresceria 3% para
sempre.

Valor terminal — cresce **sempre** a `g_perpetuidade`, nunca ao crescimento
histórico de receita. Em estado estacionário o CAPEX de manutenção se iguala à
D&A e o capital de giro cresce apenas com `g`:

```
FCFF_terminal = NOPAT_N × (1 + g) − g × NWC_N
VT            = FCFF_terminal / (WACC − g)
VP(VT)        = VT / (1 + WACC)^N
```

Sem essa normalização, uma empresa que investe acima da depreciação (Vale,
Petrobras) seria penalizada para sempre no valor terminal, porque o
`CAPEX/Receita` histórico continuaria valendo na perpetuidade.

Ponte para o equity:

```
EV     = Σ VP(FCFF_t) + VP(VT)
Equity = EV − dívida líquida + ativos não operacionais
Preço  = Equity / número de ações
```

Detalhes que evitam erros comuns:

- **Capital de giro entra como variação** (`ΔNWC`), não como nível. O nível já
  está embutido na receita-base.
- A **dívida líquida** subtraída é `dívida bruta − caixa`. Passivos não
  financeiros não entram na ponte.
- A convenção de meio de ano (`meio_ano: true`) usa expoente `t − 0,5`. Fica
  desligada por padrão para manter comparabilidade com o histórico.
- `g ≥ WACC − 1 p.p.` gera `status=g_maior_que_wacc` em vez de valor terminal
  negativo ou infinito.

## 5. Alíquota efetiva de imposto

```
t = mediana( Imposto de Renda / Lucro antes do imposto ), apenas anos com lucro > 0
```

O resultado é truncado em `[0; 34%]` (empresas não financeiras) ou `[0; 45%]`
(financeiras). Sem anos lucrativos, usa-se o teto da faixa.

Isso substitui o cálculo antigo (`Imposto / EBIT`, sem corte), que produzia
alíquotas de 3.796% e 593%.

## 6. Dividendos descontados em dois estágios (DDM)

Usado para o setor financeiro e como modelo secundário informativo para quem
distribui dividendos.

```
DPS_0    = mediana dos dividendos anuais dos últimos 3 anos completos
g1       = min( g_sustentável, Ke − g − 2 p.p. ),  g_sustentável = ROE × (1 − payout)
DPS_t    = DPS_0 × (1 + g1)^t                      para t = 1..N
VP expl. = Σ DPS_t / (1 + Ke)^t
VP(VT)   = [DPS_N × (1 + g) / (Ke − g)] / (1 + Ke)^N
Preço    = VP expl. + VP(VT)
```

Três anos (em vez de cinco) reduzem o atraso em empresas com dividendo
crescente, sem herdar um ano atípico isolado.

- `g1` é limitado para nunca se aproximar de `Ke`. O valor efetivamente usado
  fica registrado em `ResultadoDDM.g1_efetivo`.
- `Ke ≤ g + 1 p.p.` gera `status=g_maior_que_wacc`.
- Empresa sem dividendo identificado gera `status=sem_dividendos`.

## 7. Faixa de preço e sensibilidade

Um DCF é uma faixa, não um número. Para cada empresa é montada uma grade
`WACC × g` (ou `Ke × g` no DDM):

- WACC/Ke: valor central ± 2 p.p., passo de 0,5 p.p.
- `g`: de 0% a 4%, passo de 0,5 p.p.

De todos os cenários válidos (positivos e finitos) saem os percentis publicados:

| Coluna | Significado |
|---|---|
| `preco_alvo_p25` | cenário pessimista |
| `preco_alvo_p50` | cenário central |
| `preco_alvo_p75` | cenário otimista |

`upside_p50 = preco_alvo_p50 / preco_atual − 1`.

## 8. Portões de sanidade (status)

Nenhum número entra no ranking sem passar por estes filtros, aplicados nesta
ordem:

| Status | Condição |
|---|---|
| `setor_incompativel` | empresa financeira avaliada por FCFF |
| `preco_desatualizado` | último pregão há mais de 5 dias úteis, ou preço ≤ 0 |
| `nao_avaliavel` | preço-alvo não finito ou ≤ 0 |
| `resultado_absurdo` | `abs(upside) > 90%` |
| `wacc_invalido` | WACC fora de `(0%; 50%)` ou `E ≤ 0` |
| `g_maior_que_wacc` | `g ≥ WACC − 1 p.p.` (ou `Ke` no DDM) |
| `dados_insuficientes` | receita, número de ações ou preço ausentes |
| `sem_dividendos` | DDM sem DPS identificado |
| `ok` | passou por todos |

Tickers que falham na **coleta** (rede, ticker inexistente) vão para
`dados/erros.csv` com a exceção. Um ticker nunca desaparece em silêncio.

## 9. Recomendação e margem de segurança

A recomendação usa o piso da faixa (P25), não o valor central:

```
se P25 × (1 − 25%) > preço_atual  → "compra"
senão se P25 > preço_atual        → "neutro"
senão                             → "caro"
```

A margem de 25% (`margem_seguranca`) é a distância exigida entre o preço de
mercado e o cenário pessimista. Ela é publicada junto com o resultado, para que
o leitor possa recalcular com outra premissa.

## 10. Dados e reprodutibilidade

- **Uma requisição por ticker**, com cache em `dados/cache/` (parquet, TTL de 1
  dia) e retry com backoff exponencial. Respostas vazias (throttling do Yahoo)
  são retentadas como falha de rede; se persistirem, o ticker vai para
  `dados/erros.csv` com o motivo.
- O crescimento de receita é **real**: a série é deflacionada pelo IPCA
  acumulado (SIDRA/IBGE, tabela 1737, variável 69), depois se calcula a taxa
  geométrica média, truncada em `[−10%; +20%]`.
- Se o IPCA não estiver disponível, o crescimento é nominal e um aviso é
  registrado no log.
- **Moeda.** O Yahoo devolve as demonstrações na moeda de reporte da companhia
  (USD no caso de Petrobras e Vale) e o preço em BRL. O pipeline detecta a
  diferença pela escala entre `info.totalDebt` e o `Total Debt` do balanço e
  converte receita, dívida, caixa, capital de giro, ativos não operacionais e
  despesa de juros. Razões e percentuais não são afetados. O fator aplicado vai
  para a coluna `fator_cambio`.
- `premissas_hash` identifica a combinação exata de premissas usada na linha.

## 11. Limitações conhecidas

Leia antes de usar qualquer número como tese de investimento.

1. **Empresas em dificuldade financeira.** FCFF negativo no horizonte explícito
   produz valor terminal negativo. O portão `resultado_absurdo` corta o caso,
   mas não o corrige: o modelo não foi feito para distress.
2. **Empresas cíclicas no pico.** Margem EBIT mediana de um ciclo de alta
   superestima a perpetuidade. O truncamento em 60% reduz, mas não elimina, o
   problema. Prefira a faixa P25 para setores cíclicos.
3. **Financeiras.** O DDM depende de dividendos históricos estáveis. Bancos que
   retêm lucro ou pagam dividendos extraordinários ficam mal representados.
4. **Dados do Yahoo Finance.** Itens como `Other Current Assets` agregam contas
   heterogêneas; o capital de giro é uma aproximação. Mudanças de plano de contas
   entre anos afetam a mediana.
5. **Beta setorial fixo.** O beta não é estimado por regressão dos retornos da
   própria ação. Empresas com perfil muito diferente do setor ficam mal
   representadas.
6. **Sem ajuste por controle, liquidez ou governança.** O preço-alvo é o valor
   intrínseco proporcional; não há desconto de minoritário nem prêmio de controle.
7. **Projeções nominais em R$.** Inflação, câmbio e juros de longo prazo são
   tratados como constantes dentro do horizonte.

## 12. Referências

- Damodaran, A. *Investment Valuation* — betas setoriais, prêmio de risco país.
- Koller, T.; Goedhart, M.; Wessels, D. *Valuation* (McKinsey) — ponte de valor
  enterprise/equity e valor terminal.
- Assaf Neto, A. *Finanças Corporativas e Valor* — WACC e CAPM no contexto
  brasileiro.
- Banco Central do Brasil — Swap DI 360×12; IBGE/SIDRA — IPCA.
