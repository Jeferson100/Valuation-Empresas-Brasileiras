import requests
from bs4 import BeautifulSoup
import pandas as pd

url = "https://www.dadosdemercado.com.br/acoes"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
resp.raise_for_status()

soup = BeautifulSoup(resp.text, "html.parser")
tabela = soup.find_all("table")[0]

linhas = tabela.find_all("tr")[1:]  # pular cabeçalho

dados = []
for linha in linhas:
    colunas = linha.find_all(["td", "th"])
    if len(colunas) >= 1:
        ticker = colunas[0].get_text(strip=True)
        if ticker:
            dados.append({"tic": ticker.upper(), "Setor": "", "Segmento": ""})

df = pd.DataFrame(dados)
df = df.drop_duplicates(subset=["tic"])
df = df.sort_values("tic").reset_index(drop=True)

print(f"Total de tickers extraídos: {len(df)}")
print(df.head(20).to_string(index=False))

# Salvar no formato esperado pelo pipeline
df.to_csv("dados/setor.csv", index=False, encoding="utf-8")
print("\nSalvo em dados/setor.csv")
