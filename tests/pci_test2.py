import requests
from bs4 import BeautifulSoup
res = requests.get('https://www.pciconcursos.com.br/provas/download/escriturario-agente-comercial-banco-do-brasil-s-a-cesgranrio-2021')
soup = BeautifulSoup(res.text, 'html.parser')
links = soup.select('a')
for link in links:
    href = link.get('href', '')
    text = link.text.strip()
    if 'javascript' in href or 'baixar' in text.lower():
        print(text, link.attrs)
