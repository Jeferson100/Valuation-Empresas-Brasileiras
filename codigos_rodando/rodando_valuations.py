import pandas as pd
import yfinance as yf
from fundamentos import ValuationModoloGordon, ValuationFluxoCaixaDescontado, IndicadoresFinanceiros
import warnings

warnings.filterwarnings("ignore")


acoes= pd.read_csv("dados/setor.csv")['tic'].to_list()
data_valuation = {
    'acao': [],
    'valor_atual':[],
    'preco_gordon': [],
    'preco_fluxo': [],
    'diferenca_gordon': [],
    'diferenca_fluxo': [],
    'margem_ebit': [],
    'variacao_receita': [],
    'wacc': [],
    'quantidade_acoes': [],
    'divida_total': [],
    'caixa': [],
    'outros_ativos': [],
    'passivos_menos_divida': [],
    'percentual_imposto': [],
}
for acao in acoes:
    print('-'*10, acao, '-'*10)
    try:
        valu = ValuationModoloGordon(f'{acao}.SA')
        preco_gordon = valu.preco_acao()

        ind = IndicadoresFinanceiros(ticker=f'{acao}.SA')
        indicadores = ind.todos_indicadores()

        valuation_fluxo = ValuationFluxoCaixaDescontado(
                    receita_ano=indicadores['ultimareceita'],
                    porcenta_crescimento_receita=indicadores['variacaoreceita']['median_deflacionada'] if 'median_deflacionada' in indicadores['variacaoreceita'].keys() else indicadores['variacaoreceita']['median_normal'],
                    margem_ebit=indicadores['margemebit'],
                    imposto_porcentagem=indicadores['percentualimposto'],
                    depreciacao_capex=indicadores['depreciacaocapex'],
                    capex_da_receita=indicadores['capexreceita'],
                    wacc=indicadores['wacc'],
                    numero_de_acoes=indicadores['quantidadeacoes'],
                    divida=indicadores['dividatotal'],
                    disponivel=indicadores['caixa'],
                    ativos_nao_operacionais=indicadores['outrosativos'],
                    passivos_circulantes=indicadores['passivosmenosdivida'],
                    necessidade_capital_de_giro=indicadores['necessidadecapitalgiro'],
                    anos_projecao=5, 
                    taxa_crecimento_perpetuidade=0.014,
                    calculo_necessidade_capital_de_giro=False)

        _ , valor_fluxo = valuation_fluxo.calcular_valuation()

        yaho = yf.Ticker(f'{acao}.SA')
        valor_acao_atual = round(yaho.history(period="10Y", interval="1d")['Close'][-1],2)
        
        data_valuation['acao'].append(acao)
        data_valuation['valor_atual'].append(valor_acao_atual)
        data_valuation['preco_gordon'].append(preco_gordon['valuation_acao'])
        data_valuation['preco_fluxo'].append(valor_fluxo['valor_por_acao'])
        data_valuation['diferenca_gordon'].append(round((preco_gordon['valuation_acao'] - valor_acao_atual)/valor_acao_atual,2))
        data_valuation['diferenca_fluxo'].append(round((valor_fluxo['valor_por_acao'] - valor_acao_atual)/valor_acao_atual,2))
        data_valuation['margem_ebit'].append(indicadores['margemebit'])
        data_valuation['variacao_receita'].append(indicadores['variacaoreceita'])
        data_valuation['wacc'].append(indicadores['wacc'])
        data_valuation['quantidade_acoes'].append(indicadores['quantidadeacoes'])
        data_valuation['divida_total'].append(indicadores['dividatotal'])
        data_valuation['caixa'].append(indicadores['caixa'])
        data_valuation['outros_ativos'].append(indicadores['outrosativos'])
        data_valuation['passivos_menos_divida'].append(indicadores['passivosmenosdivida'])
        data_valuation['percentual_imposto'].append(indicadores['percentualimposto'])
    except:
        print(f'Erro ao obter dados da acao {acao}')
data_valores = pd.DataFrame(data_valuation)

data_valores.sort_values(by=['diferenca_gordon', 'diferenca_fluxo'], ascending=False).to_csv('dados/valores_valuations_acoes.csv', index=False)