import requests
from bs4 import BeautifulSoup
import urllib.parse

query = "trabalhador portuario"
url = f"https://www.pciconcursos.com.br/pesquisa/?q={urllib.parse.quote(query)}+prova"
headers = {'User-Agent': 'Mozilla/5.0'}

r = requests.get(url, headers=headers)
soup = BeautifulSoup(r.text, 'html.parser')
links = soup.select('.caixa a')
print("PCI Links:")
for link in links[:5]:
    print(link.text.strip(), link.get('href'))
