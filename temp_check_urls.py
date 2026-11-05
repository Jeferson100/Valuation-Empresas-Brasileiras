import requests

urls = [
    'https://www.dadosdemercado.com.br/acoes/download',
    'https://www.dadosdemercado.com.br/acoes/csv',
    'https://api.dadosdemercado.com.br/v1/tickers?ticker_type=acao',
    'https://api.dadosdemercado.com.br/v1/tickers',
]

for url in urls:
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        print(f'{url}: status={r.status_code}, tamanho={len(r.content)}, tipo={r.headers.get("content-type", "?")}')
        if r.status_code == 200 and len(r.content) > 100:
            print('  Primeiros 200 bytes:', r.content[:200])
    except Exception as e:
        print(f'{url}: ERRO {e}')
