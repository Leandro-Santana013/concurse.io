"""
Scrape PCI Concursos for PDFs
"""
import requests
from bs4 import BeautifulSoup
import urllib.parse
import re

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}



# Test PCI Concursos search  
print("\n=== PCI Concursos Busca ===")
try:
    r = requests.get("https://www.pciconcursos.com.br/provas/", headers=headers, timeout=10)
    soup = BeautifulSoup(r.text, 'html.parser')
    # Find prova links
    links = soup.find_all('a', href=True)
    prova_links = [(a.text.strip(), a['href']) for a in links 
                   if '/prova/' in a.get('href','') or 'prova' in a.get('href','')]
    print(f"Links de prova: {len(prova_links)}")
    for t, h in prova_links[:10]:
        print(f"  '{t[:50]}' -> {h[:100]}")
        
    # Try to get a prova page to see if it has PDF
    if prova_links:
        sample_link = prova_links[0][1]
        if not sample_link.startswith('http'):
            sample_link = 'https://www.pciconcursos.com.br' + sample_link
        r2 = requests.get(sample_link, headers=headers, timeout=8)
        soup2 = BeautifulSoup(r2.text, 'html.parser')
        pdfs = [a['href'] for a in soup2.find_all('a', href=True) if '.pdf' in a.get('href','').lower()]
        print(f"\nPDFs na prova: {pdfs[:3]}")
except Exception as e:
    print(f"ERRO: {e}")

# Test Bing HTML search
print("\n=== BING SEARCH ===")
try:
    q = "trabalhador portuario avulso prova pdf concurso"
    r = requests.get(f"https://www.bing.com/search?q={urllib.parse.quote(q)}", headers=headers, timeout=12)
    print(f"Bing status: {r.status_code}")
    soup = BeautifulSoup(r.text, 'html.parser')
    for li in soup.select('#b_results li.b_algo')[:8]:
        link = li.select_one('a')
        if link:
            href = link.get('href', '')
            text = link.text.strip()[:60]
            print(f"  '{text}' -> {href[:100]}")
            if '.pdf' in href.lower():
                print("    >>> PDF DIRETO!")
except Exception as e:
    print(f"ERRO: {e}")
