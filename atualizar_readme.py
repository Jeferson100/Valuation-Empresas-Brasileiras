import pandas as pd

# Lê o arquivo CSV
df = pd.read_csv('dados/valores_valuations_acoes.csv')

# Converte o DataFrame para tabela em Markdown
markdown_table = df.to_markdown(index=False)

# Abre o arquivo README.md
with open('README.md', 'r') as file:
    readme_content = file.readlines()

# Verifica e localiza a seção "Resultados das Estimativas"
for i, line in enumerate(readme_content):
    if '## Resultados das Estimativas' in line:
        print(line)
        # Adiciona a tabela logo abaixo da seção
        readme_content.insert(i + 1, f"### Tabela de Valuation\n{markdown_table}\n")

# Escreve a versão atualizada no README.md
with open('README.md', 'w') as file:
    file.writelines(readme_content)