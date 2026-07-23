"""
Test PCI Concursos specific cargo page for PDF links
"""
import requests
from bs4 import BeautifulSoup
import urllib.parse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}

# Test PCI Concursos search by query
query = "trabalhador portuario"
slug = query.lower().replace(' ', '-')
urls_to_test = [
    f"https://www.pciconcursos.com.br/pesquisa/?q={urllib.parse.quote(query)}",
    f"https://www.pciconcursos.com.br/provas/{slug}",
    "https://www.pciconcursos.com.br/provas/trabalhador-portuario",
    "https://www.pciconcursos.com.br/provas/operador-portuario",
]

for url in urls_to_test:
    print(f"\n=== {url[:80]} ===")
    try:
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        print(f"Status: {r.status_code}")
        
        # Find prova detail links
        links = soup.find_all('a', href=True)
        prova_links = [(a.text.strip(), a['href']) for a in links if '/prova/' in a.get('href','')]
        print(f"Provas encontradas: {len(prova_links)}")
        for t, h in prova_links[:5]:
            print(f"  '{t[:50]}' -> {h[:100]}")
            
        # If we find a prova link, try to get its PDF
        if prova_links:
            prova_url = prova_links[0][1]
            if not prova_url.startswith('http'):
                prova_url = 'https://www.pciconcursos.com.br' + prova_url
            r2 = requests.get(prova_url, headers=headers, timeout=8)
            soup2 = BeautifulSoup(r2.text, 'html.parser')
            # Look for PDF download link
            pdf_links = [a['href'] for a in soup2.find_all('a', href=True) if '.pdf' in a.get('href','').lower()]
            all_hrefs = [(a.text.strip(), a.get('href','')) for a in soup2.find_all('a', href=True)]
            print(f"\n  Dentro da prova {prova_url}:")
            print(f"  PDFs diretos: {pdf_links[:3]}")
            for t, h in all_hrefs[:10]:
                if h: print(f"    '{t[:40]}' -> {h[:80]}")
    except Exception as e:
        print(f"ERRO: {e}")
