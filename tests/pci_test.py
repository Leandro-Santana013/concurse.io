import requests
from bs4 import BeautifulSoup
res = requests.get('https://www.pciconcursos.com.br/provas/banco-do-brasil/')
soup = BeautifulSoup(res.text, 'html.parser')
links = soup.select('a')
for link in links:
    href = link.get('href')
    if href and '/download/' in href:
        print(href)
