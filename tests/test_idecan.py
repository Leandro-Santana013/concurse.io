"""
Scrape IDECAN directly and find PDF links
"""
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}

# Scrape IDECAN home
print("=== IDECAN ===")
r = requests.get("https://idecan.org.br/", headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

# Find all links
all_links = [(a.text.strip(), a.get('href', '')) for a in soup.find_all('a', href=True)]
print(f"Total links: {len(all_links)}")
for text, href in all_links[:30]:
    if href and href != '#':
        print(f"  '{text[:50]}' -> {href[:100]}")

# Look for PDF links specifically
pdfs = [(t, h) for t, h in all_links if '.pdf' in h.lower()]
print(f"\nPDFs diretos: {len(pdfs)}")
for t, h in pdfs:
    print(f"  {t} -> {h}")

# Try to find concurso/prova section links
concurso_links = [(t, h) for t, h in all_links if any(k in h.lower() or k in t.lower() 
                  for k in ['concurs', 'prova', 'gabarito', 'edital', 'processo'])]
print(f"\nLinks de concurso: {len(concurso_links)}")
for t, h in concurso_links[:10]:
    print(f"  '{t[:50]}' -> {h[:100]}")

# Try IDECAN concurso page
print("\n=== IDECAN /processos-seletivos ===")
for path in ['/processos-seletivos', '/concursos', '/gabaritos', '/provas', '/inscricoes']:
    try:
        r2 = requests.get(f"https://idecan.org.br{path}", headers=headers, timeout=8)
        print(f"  {path} -> {r2.status_code}")
        if r2.status_code == 200:
            soup2 = BeautifulSoup(r2.text, 'html.parser')
            pdfs2 = [a['href'] for a in soup2.find_all('a', href=True) if '.pdf' in a['href'].lower()]
            print(f"    PDFs: {pdfs2[:3]}")
    except Exception as e:
        print(f"  {path} -> ERRO: {e}")

# Test PCI Concursos with provas search
print("\n=== PCI Concursos provas ===")
r3 = requests.get("https://www.pciconcursos.com.br/provas/", headers=headers, timeout=10)
soup3 = BeautifulSoup(r3.text, 'html.parser')
print(f"Status: {r3.status_code}")
links3 = [(a.text.strip(), a.get('href','')) for a in soup3.find_all('a', href=True)]
for t, h in links3[:20]:
    if h and 'prova' in h.lower():
        print(f"  '{t[:50]}' -> {h[:100]}")
