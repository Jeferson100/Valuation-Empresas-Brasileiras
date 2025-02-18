import yfinance as yf
import pandas as pd


class OutrosAtivosNaoOperacionais:
    def __init__(self, ticker: str):
        self.ticker = ticker
        self.stock = yf.Ticker(ticker=self.ticker)

    def investimentos_e_adiantamentos(self) -> float:
        investimentos_adiantamentos = self.stock.get_balancesheet(freq="yearly")
        if isinstance(investimentos_adiantamentos, pd.DataFrame):
            if "InvestmentsAndAdvances" in investimentos_adiantamentos.index:
                investimentos_adiantamentos = investimentos_adiantamentos.loc[
                    "InvestmentsAndAdvances"
                ][0]
            else:
                investimentos_adiantamentos = 0.0
            if isinstance(investimentos_adiantamentos, pd.Series):
                return float(investimentos_adiantamentos.iloc[0])
            return float(investimentos_adiantamentos)
        return 0.0

    def outros_ativos_nao_circulantes(self) -> float:
        outros_ativos_nao_circulantes = self.stock.get_balancesheet(freq="yearly")
        if isinstance(outros_ativos_nao_circulantes, pd.DataFrame):
            if "OtherNonCurrentAssets" in outros_ativos_nao_circulantes.index:
                outros_ativos_nao_circulantes = outros_ativos_nao_circulantes.loc[
                    "OtherNonCurrentAssets"
                ][0]
            else:
                outros_ativos_nao_circulantes = 0
            if isinstance(outros_ativos_nao_circulantes, pd.Series):
                return float(outros_ativos_nao_circulantes.iloc[0])
            return float(outros_ativos_nao_circulantes)
        return 0.0

    def goodwill_outros_ativos_intangiveis(self) -> float:
        goodwil = self.stock.get_balancesheet(freq="yearly")
        if isinstance(goodwil, pd.DataFrame):
            if "GoodwillAndOtherIntangibleAssets" in goodwil.index:
                goodwil = goodwil.loc["GoodwillAndOtherIntangibleAssets"][0]
            else:
                goodwil = 0
            if isinstance(goodwil, pd.Series):
                return float(goodwil.iloc[0])
            return float(goodwil)
        return 0.0

    def terrenos_melhorias(self) -> float:
        terrenos_melhorias = self.stock.get_balancesheet(freq="yearly")
        if isinstance(terrenos_melhorias, pd.DataFrame):
            if "LandAndImprovements" in terrenos_melhorias.index:
                terrenos_melhorias = terrenos_melhorias.loc["LandAndImprovements"][0]
            else:
                terrenos_melhorias = 0
            if isinstance(terrenos_melhorias, pd.Series):
                return float(terrenos_melhorias.iloc[0])
            return float(terrenos_melhorias)
        return 0.0

    def outros_imoveis(self) -> float:
        out_terrenos = self.stock.get_balancesheet(freq="yearly")
        if isinstance(out_terrenos, pd.DataFrame):
            if "OtherProperties" in out_terrenos.index:
                out_terrenos = out_terrenos.loc["OtherProperties"][0]
            else:
                out_terrenos = 0
            if isinstance(out_terrenos, pd.Series):
                return float(out_terrenos.iloc[0])
            return float(out_terrenos)
        return 0.0

    def valor_outros_ativos_nao_operacionais(self) -> float:
        inves_adiamtamento = self.investimentos_e_adiantamentos()
        outros_ativos_nao = self.outros_ativos_nao_circulantes()
        godwill = self.goodwill_outros_ativos_intangiveis()
        terrenos = self.terrenos_melhorias()
        outros_imove = self.outros_imoveis()
        valor_tota = float(
            pd.Series(
                [inves_adiamtamento, outros_ativos_nao, godwill, terrenos, outros_imove]
            )
            .fillna(0)
            .sum()
        )
        return valor_tota
