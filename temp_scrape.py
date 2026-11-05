import requests
from bs4 import BeautifulSoup
import pandas as pd

url = "https://www.dadosdemercado.com.br/acoes"
resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
resp.raise_for_status()

print("Tamanho da página:", len(resp.text))

soup = BeautifulSoup(resp.text, "html.parser")

# Procurar tabelas na página
tabelas = soup.find_all("table")
print(f"Tabelas encontradas: {len(tabelas)}")

for i, tabela in enumerate(tabelas):
    linhas = tabela.find_all("tr")
    print(f"\nTabela {i}: {len(linhas)} linhas")
    if linhas:
        # Primeira linha (cabeçalho)
        cabecalho = [th.get_text(strip=True) for th in linhas[0].find_all(["th", "td"])]
        print(f"  Cabeçalho: {cabecalho}")
        # Primeira linha de dados
        if len(linhas) > 1:
            dados = [td.get_text(strip=True) for td in linhas[1].find_all(["td", "th"])]
            print(f"  Primeira linha: {dados}")
