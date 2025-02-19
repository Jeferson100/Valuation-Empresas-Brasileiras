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
    if '## Estrutura do RepositÃ³rio' in line:
        index_fim = i
    if '## Resultados das Estimativas' in line:
        index_inicio = i
        
if len(readme_content[index_inicio:index_fim-1]) <= 10:
    print("Tabela não existe ou foi removida.")
    readme_content.insert(index_inicio + 1, f"### Tabela de Valuation\n{markdown_table}\n")
else:
    print("Tabela já existe, substituindo...")
    readme_content[index_inicio+2:index_fim-1] = markdown_table.splitlines()
    
# Escreve a versão atualizada no README.md
with open('README.md', 'w') as file:
    file.writelines(readme_content)  



