import pandas as pd

# Lê o arquivo CSV
df = pd.read_csv('dados/valores_valuations_acoes.csv')

# Converte o DataFrame para tabela em Markdown
markdown_table = df.to_markdown(index=False)

# Abre o arquivo README.md
with open('README.md', 'r') as file:
    readme_content = file.readlines()

# Verifica e localiza a seção "Resultados das Estimativas"
section_found = False
for i, line in enumerate(readme_content):
    if '## Estrutura do RepositÃ³rio' or '## Estrutura do Repositório' in line:
        index_fim = i
    if '## Resultados das Estimativas' in line:
        index_inicio = i

readme_content = readme_content[:index_inicio+1] + readme_content[index_fim-1:]
        
readme_content.insert(index_inicio + 1, f"### Tabela de Valuation\n{markdown_table}\n")

with open('README.md', 'w') as file:
    file.writelines(readme_content)  



