"""
Test Bing search API for PDF concurso links (no key needed for HTML search)
Also test specific banca PDF repositories  
"""
import requests
from bs4 import BeautifulSoup
import urllib.parse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}

query = "trabalhador portuario avulso prova concurso filetype:pdf"

# Test Bing
print("=== BING ===")
try:
    bing_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&form=QBLH"
    r = requests.get(bing_url, headers=headers, timeout=12)
    print(f"Status: {r.status_code}")
    soup = BeautifulSoup(r.text, 'html.parser')
    # Bing search results
    for li in soup.select('#b_results .b_algo')[:5]:
        title = li.select_one('h2')
        cite = li.select_one('cite')
        if title and cite:
            print(f"  {title.text[:60]} | {cite.text[:80]}")
            if '.pdf' in cite.text.lower():
                print(f"    >>> PDF LINK!")
except Exception as e:
    print(f"ERRO: {e}")

# Also test known repositories of public exam PDFs
print("\n=== Repositorios gov.br ===")
gov_urls = [
    "https://www.gov.br/planejamento/pt-br/assuntos/concursos-e-selecoes",
    "https://www.portosgeral.com.br/documentos",
    "https://antaq.gov.br/portal/concursos",
]
for url in gov_urls:
    try:
        r = requests.get(url, headers=headers, timeout=8)
        print(f"\n{url} -> {r.status_code}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            pdfs = [a['href'] for a in soup.find_all('a', href=True) if '.pdf' in a.get('href','').lower()]
            for p in pdfs[:3]:
                print(f"  PDF: {p}")
    except Exception as e:
        print(f"  ERRO: {e}")
