# Descrição do Repositório

Este repositório contém uma aplicação para realizar o valuation de empresas brasileiras utilizando duas metodologias consagradas:

- **Fluxo de Caixa Descontado (DCF):** Avalia o valor da empresa com base na projeção e desconto dos fluxos de caixa futuros.
- **Método de Gordon:** Calcula o valor da empresa considerando dividendos e crescimento perpétuo.

A aplicação integra cálculos financeiros e indicadores por meio de módulos específicos, permitindo a comparação dos resultados obtidos por ambos os métodos.

## Objetivos

- O repositório tem como objetivo realizar o valuation de empresas brasileiras.
- Utiliza metodologias conhecidas, como o Fluxo de Caixa Descontado e o Método de Gordon.
- Integra dados financeiros históricos e indicadores obtidos de fontes como o Yahoo Finance.
- Permite comparar os resultados dos diferentes métodos de valuation.
- Auxilia investidores e analistas na tomada de decisões através de uma análise prática e educativa.


## Resultados dos Estimativas

![tabela](dados/tabela.md)

## Estrutura do Repositório

- **[dados](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/tree/main/dados)**  
  Pasta que armazena os arquivos CSV:
  - [setor.csv](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/blob/main/dados/setor.csv): Contém os códigos das ações (na coluna `tic`).
  - [valores_valuations_acoes.csv](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/blob/main/dados/valores_valuations_acoes.csv): Gera o relatório final com os resultados dos valuations.

- **[fundamentos](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/tree/main/fundamentos)**  
  Contém os módulos responsáveis pelos cálculos e coleta dos indicadores financeiros:
  - `__init__.py` : Inicializa o pacote `fundamentos`, permitindo a importação centralizada dos módulos de cálculos e indicadores financeiros.
  - **`calculo_wacc.py`**  
    Realiza o cálculo do WACC (Custo Médio Ponderado de Capital) através de diversos métodos:  
    - Importa dados financeiros via **yfinance** e **ipeadatapy** para acessar informações de mercado e taxas livres.  
    - Define a classe `CalculoWACC` que encapsula métodos para obter juros livres, beta, valor de mercado e dívida.  
    - Calcula o custo do patrimônio combinando juros livres, beta e retorno do mercado.  
    - Determina o custo da dívida e ajusta o valor pelo benefício fiscal dos impostos.  
    - Combina todos esses elementos para retornar o WACC final, arredondado conforme necessário.

  - `indicadores_financeiros.py`: Coleta e processa os indicadores financeiros para o calculo do Valuation.

    - Coleta dados financeiros do Yahoo Finance, incluindo balanço, fluxo de caixa e informações de mercado.
    - Calcula métricas essenciais como receita, EBIT, margem EBIT e taxa efetiva de imposto.
    - Determina rátios de CAPEX, depreciação e a relação entre depreciação e CAPEX.
    - Utiliza módulos auxiliares para obter WACC, ativos não operacionais, passivos líquidos e capital de giro.
    - Agrega todos os indicadores em um dicionário para suporte a análises de valuation.

  - `necessidade_capital_giro.py`: Calcula a necessidade de capital de giro.
    - Coleta dados do balanço anual da empresa via yfinance para extrair informações financeiras.
    - Extrai ativos operacionais, como contas a receber, estoque e outros ativos circulantes.
    - Obtém passivos operacionais, incluindo contas a pagar e outros passivos circulantes.
    - Calcula os totais de ativos e passivos circulantes operacionais.
    - Determina a necessidade de capital de giro como a diferença entre ativos e passivos circulantes.

  - `outros_ativos_nao_operecionais.py`: Avalia outros ativos não operacionais.
    - Coleta dados do balanço anual via yfinance para acessar informações de ativos não operacionais.
    - Extrai valores de investimentos e adiantamentos, outros ativos não circulantes e goodwill.
    - Obtém também valores para terrenos, melhorias e outros imóveis.
    - Cada método verifica se o índice existe no DataFrame, retornando o valor ou zero.
    - A função final agrega esses valores para fornecer o total dos ativos não operacionais.

  - `passivos_menos_divida.py`: Calcula os passivos descontando a dívida.

    - A classe utiliza yfinance para extrair dados do balanço anual de uma empresa com base em seu ticker.
    - Ela recupera os passivos não circulantes através do índice "TotalNonCurrentLiabilitiesNetMinorityInterest".
    - Extrai os passivos circulantes utilizando o índice "CurrentLiabilities".
    - Obtém a dívida total a partir do índice "TotalDebt".
    - Calcula o passivo líquido subtraindo a dívida total da soma dos passivos circulantes e não circulantes.

  - `valuation_fluxo_caixa_descontado.py`: 

    - Projeta as métricas financeiras anuais (receita, EBIT, impostos, CAPEX e depreciação) considerando o crescimento da receita.
    - Calcula o EBIT ajustado e o fluxo de caixa livre para cada ano, incluindo ajustes como a necessidade de capital de giro.
    - Desconta os fluxos de caixa futuros pela taxa WACC para obter seus valores presentes.
    - Estima o valor terminal (perpetuidade) com base em um crescimento constante e o desconta para o período atual.
    - Retorna um DataFrame com as projeções anuais e um dicionário com as métricas-chave, incluindo o valor por ação.

  - `valuation_metodo_gordon.py`: Implementa o valuation pelo método de Gordon.
    - Implementa o modelo de valuation de Gordon, focado na análise de dividendos e crescimento sustentável.
    - Obtém dados financeiros e históricos do Yahoo Finance para calcular métricas essenciais, como dividendos, beta e retorno.
    - Calcula a taxa de crescimento sustentável (g) e o custo de capital (WACC) a partir de indicadores como juros livres.
    - Estima o valor presente da ação dividindo o dividendo mediano pela diferença entre WACC e g sustentável.
    - Armazena os resultados em um dicionário, permitindo comparar o valuation calculado com a cotação atual da ação.

  - `variacao_receita.py`: Calcula a variação de receita.
    - Coleta os dados financeiros históricos de receita (TotalRevenue) da empresa usando yfinance.
    - Obtém e ajusta os dados de inflação (IPCA) via sidrapy, focando nas datas de dezembro.
    - Alinha os dados de inflação com as datas da receita para possibilitar ajustes precisos.
    - Calcula a inflação acumulada e utiliza-a para deflacionar os valores da receita.
    - Retorna métricas de crescimento da receita (média e mediana), tanto nominais quanto deflacionadas.


- **[rodando_valuations.py](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/blob/main/rodando_valuations.py)**  
  Script principal que integra os módulos, lê os dados de entrada, executa os cálculos de valuation para cada ação e gera um relatório com os resultados.

## Objetivos

- **Análise de Investimentos:** Auxiliar investidores e analistas financeiros a comparar diferentes metodologias de valuation.

- **Flexibilidade e Extensibilidade:** Permitir a inclusão de novos indicadores e métodos de avaliação, adaptando-se às necessidades dos usuários.


## Contribuições

Se você encontrar algum problema ou tiver sugestões de melhorias, sinta-se à vontade para abrir uma issue ou enviar um pull request.

## Licensa

Este projeto está licenciado sob a Licença Apache License 2.0 - veja o arquivo [LICENSE](https://github.com/Jeferson100/Valuation-Empresas-Brasileiras/blob/main/LICENSE) para mais detalhes.


