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
    if '## Resultados das Estimativas' in line:
        section_found = True
        # Verifica se já existe uma tabela após essa seção
        if any('Tabela de Valuation' in content for content in readme_content[i:]):
            # Remove a tabela existente (caso já haja)
            start_index = next(j for j, content in enumerate(readme_content[i:]) if 'Tabela de Valuation' in content) + i
            # Remove a tabela existente (2 linhas: título + a própria tabela)
            readme_content[start_index:start_index + 2] = []
            print("Tabela existente removida.")
        # Adiciona a nova tabela
        readme_content.insert(i + 1, f"### Tabela de Valuation\n{markdown_table}\n")
        break

if not section_found:
    print("Seção 'Resultados das Estimativas' não encontrada.")

# Escreve a versão atualizada no README.md
with open('README.md', 'w') as file:
    file.writelines(readme_content)


