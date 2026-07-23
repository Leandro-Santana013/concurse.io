import requests
from bs4 import BeautifulSoup

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
url = "https://html.duckduckgo.com/html/?q=trabalhador+portuario+avulso+prova+ext:pdf"
r = requests.get(url, headers=headers)
print("Status:", r.status_code)
soup = BeautifulSoup(r.text, 'html.parser')
links = soup.select('.result__url')
print(f"Found {len(links)} links")
for a in links:
    print(a.text.strip())
