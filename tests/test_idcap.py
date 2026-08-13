"""
Test specific IDCAP pages and Google search for PDFs
"""
import requests
from bs4 import BeautifulSoup
import urllib.parse

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': 'https://www.google.com/'
}

# Test DuckDuckGo HTML with IDCAP/IDECAN specific searches
test_queries = [
    'site:idcap.org.br prova pdf',
    'site:ibfc.org.br prova concurso pdf',
    'trabalhador portuario prova concurso pdf site:gov.br OR site:idcap.org.br',
    'prova concurso "trabalhador portuario" filetype:pdf',
]

for query in test_queries:
    print(f"\n=== Query: {query[:80]} ===")
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        r = requests.get(url, headers=headers, timeout=12)
        soup = BeautifulSoup(r.text, 'html.parser')
        results = soup.select('.result')
        print(f"  Resultados DDG: {len(results)}")
        for res in results[:5]:
            url_el = res.select_one('.result__url')
            title_el = res.select_one('.result__title')
            if url_el:
                raw_url = url_el.text.strip()
                title = title_el.text.strip() if title_el else 'sem titulo'
                print(f"  - {raw_url[:80]} | {title[:50]}")
    except Exception as e:
        print(f"  ERRO: {e}")

# Also test direct IDCAP URL variations
print("\n=== Testando URLs diretos IDCAP ===")
direct_urls = [
    "https://idcap.org.br/concursos-realizados",
    "https://idcap.org.br/provas",
    "https://www.idcap.org.br/provas",
]
for url in direct_urls:
    try:
        r = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        print(f"  {url} -> {r.status_code} ({r.url})")
    except Exception as e:
        print(f"  {url} -> ERRO: {e}")
