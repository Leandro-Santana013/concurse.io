import requests
from bs4 import BeautifulSoup
import time

headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
res = requests.get('https://www.pciconcursos.com.br/provas/download/escriturario-agente-comercial-banco-do-brasil-s-a-cesgranrio-2021', headers=headers)
soup = BeautifulSoup(res.text, 'html.parser')
links = soup.select('a')
for link in links:
    arquivo = link.get('data-arquivo')
    token = link.get('data-code')
    acao = link.get('data-acao')
    if arquivo and token and acao == 'baixar':
        url = f"https://www.pciconcursos.com.br/download/{arquivo}?token={token}"
        print(f"Tentando baixar {url} ...")
        headers['Referer'] = 'https://www.pciconcursos.com.br/provas/download/escriturario-agente-comercial-banco-do-brasil-s-a-cesgranrio-2021'
        r2 = requests.get(url, headers=headers)
        print("Status:", r2.status_code)
        print("Content-Type:", r2.headers.get('Content-Type'))
        break
