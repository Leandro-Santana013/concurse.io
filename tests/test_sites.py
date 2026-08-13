"""
Test real scraping from IDCAP and other banca sites
"""
import requests
from bs4 import BeautifulSoup
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

tests = [
    ("IDCAP", "https://www.idcap.org.br/concursos-realizados"),
    ("IBFC", "https://www.ibfc.org.br/concurso"),
    ("VUNESP provas", "https://www.vunesp.com.br/VPUB0001/Paginas/ListaPorAssunto.aspx"),
    ("PCI Concursos", "https://www.pciconcursos.com.br/provas/?p=1&q=trabalhador+portuario"),
    ("QConcursos", "https://www.qconcursos.com/questoes-de-concursos/concursos"),
]

for name, url in tests:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        print(f"\n{name} -> Status: {r.status_code}, Bytes: {len(r.content)}")
        soup = BeautifulSoup(r.text, 'html.parser')
        # Find any PDF links
        pdf_links = [a['href'] for a in soup.find_all('a', href=True) if '.pdf' in a['href'].lower()]
        print(f"  PDFs encontrados: {len(pdf_links)}")
        for l in pdf_links[:3]:
            print(f"    -> {l}")
    except Exception as e:
        print(f"{name} -> ERRO: {e}")
