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

## 5. Cenário de receita projetada (segundo valuation)

O valuation **oficial** continua sendo o da seção 4: crescimento histórico
médio com fade linear. Em paralelo, o pipeline publica um **segundo DCF** em que
apenas o vetor de crescimento muda — em vez do fade, cada ano usa a previsão do
modelo de receita. As colunas ficam no fim do CSV (`preco_receita_p25/p50/p75`,
`upside_receita_p50`, `status_receita`, ...) e **não** alteram preço-alvo,
recomendação, status ou ranking oficiais. `publicar_modelo_receita: false` em
`config.yaml` desliga o cenário; `--sem-previsao` o pula numa execução.

### 5.1 Painel histórico

A fonte é o conjunto de **dados abertos da CVM** (DFP — Demonstrações Financeiras
Padronizadas), de 2010 a 2025, que cobre os exercícios de 2009 a 2025. Cada
pacote anual traz o exercício corrente e o anterior; reafirmações são resolvidas
pelo arquivo mais recente, pelo consolidado e pela maior `VERSAO`. O mapeamento
CNPJ → ticker vem do formulário FCA. O painel resultante é versionado em
`dados/receitas_historicas.csv` (~150 tickers, 2009–2025):

```bash
python -m valuation.data.cvm --atualizar --anos 2010-2025
```

O download completo tem ~220 MB e roda **uma vez por ano**; o pipeline mensal
apenas lê o CSV. O exercício mais recente do yfinance é anexado ao painel antes
do cálculo das defasagens, para o run mensal não depender da atualização da CVM.

### 5.2 Modelos

Os dois modelos lineares usam variáveis independentes, estimados por mínimos
quadrados (`numpy.linalg.lstsq`), sem sklearn ou statsmodels:

**Modelo A — fundamentos** (variação *entre* empresas):

```
g_it = a + b1·log(receita)_{i,t−1} + b2·margem_EBIT_{i,t−1}
         + b3·ROA_{i,t−1} + b4·giro_{i,t−1}
         + efeito_fixo_ano + efeito_fixo_setor + erro
```

**Modelo B — macro** (variação *no tempo*, com efeito fixo de empresa):

```
g_it = α_i + b1·Δlog(IBC-Br)_t + b2·IPCA_t + b3·Δlog(câmbio)_t + erro
```

Baselines: **AR** (repete o último crescimento) e **mediana do setor**.

**Modelos de machine learning** (opcionais) disputam o mesmo backtest: XGBoost,
LightGBM, CatBoost, uma MLP e duas redes recorrentes (LSTM e GRU). A comparação
é de **solução completa** — o ML pode usar, além das variáveis dos modelos A/B,
features extras calculadas apenas com informação até `t−1`:

| Feature | Definição |
|---|---|
| `g_lag2` | crescimento de `t−2` |
| `margem_lag2` | margem EBIT de `t−2` |
| `log_ativo_lag` | log do ativo total deflacionado |
| `alavancagem_lag` | patrimônio líquido / ativo total |
| `idade_empresa` | número de exercícios já observados |
| `crescimento_medio_3` | média de `g` nos três anos anteriores |
| `vol_crescimento` | desvio-padrão de `g` nos quatro anos anteriores |
| `d_margem` | variação da margem entre `t−2` e `t−1` |

O setor entra como categórica nativa nas árvores e one-hot na MLP. As
bibliotecas são opcionais: `pip install -e ".[ml]"` (boosting e MLP) e
`".[deep]"` (torch, para LSTM/GRU). Modelo com biblioteca ausente é ignorado
com aviso, sem interromper o pipeline. Os hiperparâmetros são deliberadamente
conservadores (poucas árvores, profundidade 3), porque o painel tem ~2 mil
linhas e ~150 empresas.

### 5.3 Backtest e seleção

Backtest *rolling-origin*: treina até `t−1`, prevê `t`, para cada origem a partir
de 2014. Nenhuma linha do ano-alvo entra no ajuste. Um modelo só substitui o AR
num setor se reduzir o MAPE em pelo menos 1 ponto percentual (`margem_minima`).

Resultado com o painel 2009–2025 (as expectativas do Focus estavam indisponíveis
na medição, então o Modelo B rodou com as três variáveis realizadas):

| Modelo | MAPE | MAPE mediano | Erro médio de `g` | Acerto de sinal |
|---|---:|---:|---:|---:|
| mediana do setor | 16,6% | **11,5%** | −1,1 p.p. | 61% |
| fundamentos (A) | 17,1% | 12,3% | −0,7 p.p. | 57% |
| CatBoost | 17,2% | 11,6% | −2,6 p.p. | 56% |
| XGBoost | 17,7% | 11,9% | −2,2 p.p. | 56% |
| LightGBM | 17,9% | 12,3% | −1,8 p.p. | 56% |
| macro (B) | 18,1% | 12,4% | −1,4 p.p. | 59% |
| AR | 19,3% | 12,9% | +0,3 p.p. | 58% |
| MLP | 19,6% | 14,6% | −3,3 p.p. | 52% |
| GRU | 22,3% | 17,2% | −3,2 p.p. | 52% |
| LSTM | 22,9% | 17,4% | −0,6 p.p. | 51% |

Os três modelos de *boosting* batem o AR no agregado (17,2%–17,9% contra
19,3%), mas **não** batem a mediana setorial. O MAPE mediano deles fica próximo
do da mediana setorial (11,6%–12,3% contra 11,5%), o que mostra que a média é
puxada por outliers; em compensação, subestimam o crescimento em 1,8–2,6 p.p. em
média — viés sistemático que importa no DCF, porque encolhe a receita projetada
em todos os anos. A MLP e, principalmente, as redes recorrentes perdem para o
AR: com 149 empresas e ~14 anos de série, não há sinal suficiente para
identificar dinâmica temporal.

A seleção por setor muda pouco: **CatBoost** entra em Petróleo, Gás e
Biocombustíveis (no lugar do Modelo B), e os demais setores mantêm a escolha
anterior — mediana setorial em Financeiro e Consumo não Cíclico; Modelo A em
Materiais Básicos e Utilidade Pública; Modelo B em Bens Industriais; AR em
Saúde, Tecnologia da Informação, Comunicações e Consumo Cíclico. Com dez candidatos por setor, a margem de 1 p.p. fica mais sujeita a
um vencedor espúrio: os nomes por setor devem ser lidos como descritivos, não
como evidência forte.

O **Modelo A bate o AR no agregado** e é adotado em Materiais Básicos (14,1%
contra 17,4%) e Utilidade Pública (15,9% contra 22,1%), mas perde para a mediana
setorial em vários setores e não é usado neles. O Modelo B vence o AR em Bens
Industriais (18,9% contra 22,6%). Esse resultado é modesto e fica registrado: na
maior parte do universo, a previsão publicada é um crescimento setorial, não uma
previsão específica da empresa.

### 5.4 Do modelo ao DCF

Depois da escolha por setor:

- **Encolhimento** empirical Bayes: `w = n/(n+k)`, com `k = 3`. A tendência da
  empresa é puxada para a mediana do setor quando a série é curta.
- **Amortecimento** exponencial até a perpetuidade:
  `g_t = g_perp + (g − g_perp)·φ^(t−1)`, com `φ = 0,85`.
- A tendência é estimada em termos **reais** (receita deflacionada pelo IPCA) e
  convertida para nominal:
  `g_nominal = (1 + g_real)·(1 + IPCA) − 1`. A perpetuidade real é derivada da
  nominal de 3%, para o último ano explícito encontrar o valor terminal sem
  salto.
- O crescimento anual é truncado em `[−20%; +35%]`.

Limitações do cenário: o backtest do Modelo B usa a macro **realizada** do
ano-alvo (é otimista por construção); o painel depende do mapa CNPJ → ticker do
FCA e cobre 151 dos 159 tickers; holdings sem receita na DRE (Bradespar, por
exemplo) caem na mediana do setor.

Três limitações valem especificamente para os modelos de ML:

1. **A macro é nacional.** As variáveis do BCB têm 16 valores anuais, então o
   efeito macro é identificado no nível do ano, não da empresa. As árvores
   ganham pouco com isso e podem aprender a média de anos específicos.
2. **O tamanho efetivo da amostra é pequeno.** São 149 empresas e ~14
   observações por empresa; os modelos de boosting são regularizados para não
   decorar os anos de treino, e as redes recorrentes não têm série suficiente
   para identificar dinâmica temporal.
3. **A comparação é de solução completa.** O ML usa features que o OLS não usa;
   o ganho medido não é apenas "modelo melhor", é "modelo + engenharia de
   features".

## 6. Alíquota efetiva de imposto

```
t = mediana( Imposto de Renda / Lucro antes do imposto ), apenas anos com lucro > 0
```

O resultado é truncado em `[0; 34%]` (empresas não financeiras) ou `[0; 45%]`
(financeiras). Sem anos lucrativos, usa-se o teto da faixa.

Isso substitui o cálculo antigo (`Imposto / EBIT`, sem corte), que produzia
alíquotas de 3.796% e 593%.

## 7. Dividendos descontados em dois estágios (DDM)

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

## 8. Faixa de preço e sensibilidade

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

## 9. Portões de sanidade (status)

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

## 10. Recomendação e margem de segurança

A recomendação usa o piso da faixa (P25), não o valor central:

```
se P25 × (1 − 25%) > preço_atual  → "compra"
senão se P25 > preço_atual        → "neutro"
senão                             → "caro"
```

A margem de 25% (`margem_seguranca`) é a distância exigida entre o preço de
mercado e o cenário pessimista. Ela é publicada junto com o resultado, para que
o leitor possa recalcular com outra premissa.

## 11. Dados e reprodutibilidade

- **Uma requisição por ticker**, com cache em `dados/cache/` (parquet, TTL de 1
  dia) e retry com backoff exponencial. Respostas vazias (throttling do Yahoo)
  são retentadas como falha de rede; se persistirem, o ticker vai para
  `dados/erros.csv` com o motivo.
- O crescimento de receita é **real**: a série é deflacionada pelo IPCA
  acumulado (SIDRA/IBGE, tabela 1737, variável 69), depois se calcula a taxa
  geométrica média, truncada em `[−10%; +20%]`.
- Se o IPCA não estiver disponível, o crescimento é nominal e um aviso é
  registrado no log.
- O valuation oficial usa as demonstrações do Yahoo (até 4 anos). O cenário de
  receita usa o painel da CVM (seção 5), com ~17 exercícios por empresa.
- **Moeda.** O Yahoo devolve as demonstrações na moeda de reporte da companhia
  (USD no caso de Petrobras e Vale) e o preço em BRL. O pipeline detecta a
  diferença pela escala entre `info.totalDebt` e o `Total Debt` do balanço e
  converte receita, dívida, caixa, capital de giro, ativos não operacionais e
  despesa de juros. Razões e percentuais não são afetados. O fator aplicado vai
  para a coluna `fator_cambio`.
- `premissas_hash` identifica a combinação exata de premissas usada na linha.

## 12. Limitações conhecidas

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

## 13. Referências

- Damodaran, A. *Investment Valuation* — betas setoriais, prêmio de risco país.
- Koller, T.; Goedhart, M.; Wessels, D. *Valuation* (McKinsey) — ponte de valor
  enterprise/equity e valor terminal.
- Assaf Neto, A. *Finanças Corporativas e Valor* — WACC e CAPM no contexto
  brasileiro.
- Banco Central do Brasil — Swap DI 360×12; IBGE/SIDRA — IPCA.
