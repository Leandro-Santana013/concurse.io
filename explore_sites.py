"""
Deep dive into IDCAP concurso 178 to find actual prova/gabarito PDFs
"""
import requests
from bs4 import BeautifulSoup

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'pt-BR,pt;q=0.9',
}

# IDCAP SAAE 178 - look for caderno de prova / gabarito
print('=== IDCAP 178 ALL PDFs ===')
r = requests.get('https://idcap.org.br/informacoes/178/', headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')
all_links = [(a.text.strip(), a.get('href','')) for a in soup.find_all('a', href=True)]
pdf_links = [(t, h) for t, h in all_links if '.pdf' in h.lower()]

for t, h in pdf_links:
    lower_t = t.lower()
    markers = ['gabarito', 'caderno', 'prova objetiva', 'prova']
    is_prova = any(m in lower_t for m in markers)
    prefix = '**' if is_prova else '  '
    try:
        print(f'{prefix} [{t}] -> {h}')
    except:
        pass

# Check for gabarito links specifically
print()
print('=== Gabarito links ===')
gabarito_links = [(t, h) for t, h in pdf_links if 'gabarito' in t.lower()]
for t, h in gabarito_links:
    try:
        print(f'  [{t}] -> {h}')
    except:
        pass

# Also check IDCAP MMA 170 for gabarito/caderno
print()
print('=== IDCAP MMA 170 - Gabarito/Caderno ===')
r = requests.get('https://idcap.org.br/informacoes/170/', headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')
all_links = [(a.text.strip(), a.get('href','')) for a in soup.find_all('a', href=True)]
pdf_links = [(t, h) for t, h in all_links if '.pdf' in h.lower()]

for t, h in pdf_links:
    lower_t = t.lower()
    if any(kw in lower_t for kw in ['gabarito', 'caderno', 'prova']):
        try:
            print(f'  [{t}] -> {h}')
        except:
            pass

# Test if we can actually download one of these PDFs
print()
print('=== Testing PDF download ===')
test_url = 'https://anexos.cdn.selecao.net.br/uploads/227/concursos/178/anexos/438c99f6-4526-4405-a5b4-c2f8bb165ec6.pdf'
try:
    r = requests.get(test_url, headers=headers, timeout=15, stream=True)
    print(f'Status: {r.status_code}')
    print(f'Content-Type: {r.headers.get("Content-Type", "")}')
    print(f'Content-Length: {r.headers.get("Content-Length", "unknown")}')
except Exception as e:
    print(f'ERRO: {e}')

# Also test the new R2 CDN format
test_url2 = 'https://anexos-r2.selecao.net.br/uploads/227/concursos/239/anexos/4a6024d1-6049-40bc-87cb-17134f90a6fa.pdf'
try:
    r = requests.get(test_url2, headers=headers, timeout=15, stream=True)
    print(f'R2 Status: {r.status_code}')
    print(f'R2 Content-Type: {r.headers.get("Content-Type", "")}')
    print(f'R2 Content-Length: {r.headers.get("Content-Length", "unknown")}')
except Exception as e:
    print(f'ERRO: {e}')

# Check IDECAN portal edital 6 more deeply (has PROVA OBJETIVA section)
print()
print('=== IDECAN Portal Edital 6 - Deep check ===')
r = requests.get('https://portal.concursos.idecan.org.br/edital/ver/6', headers=headers, timeout=10)
soup = BeautifulSoup(r.text, 'html.parser')

# Look at the HTML structure around #collapse10
collapse = soup.find(id='collapse10')
if collapse:
    print('Found #collapse10:')
    links = collapse.find_all('a', href=True)
    for a in links:
        try:
            print(f'  [{a.text.strip()[:60]}] -> {a["href"][:150]}')
        except:
            pass
else:
    print('No #collapse10 found')

# Look for all accordion/collapse sections
accordions = soup.find_all(class_=['accordion', 'collapse', 'panel'])
print(f'Accordion/collapse elements: {len(accordions)}')
for acc in accordions:
    acc_id = acc.get('id', '')
    links = acc.find_all('a', href=True)
    pdf_in_acc = [a for a in links if '.pdf' in a.get('href','').lower()]
    if pdf_in_acc:
        try:
            print(f'  Section {acc_id}: {len(pdf_in_acc)} PDFs')
            for a in pdf_in_acc[:3]:
                print(f'    [{a.text.strip()[:60]}] -> {a["href"][:150]}')
        except:
            pass

# Check all links on edital 6
all_links6 = [(a.text.strip(), a.get('href','')) for a in soup.find_all('a', href=True)]
download_links = [(t, h) for t, h in all_links6 
                  if any(kw in h.lower() for kw in ['download', 'cdn', 'storage', 'blob', 'bucket'])]
print(f'Download/CDN links: {len(download_links)}')
for t, h in download_links[:10]:
    try:
        print(f'  [{t[:60]}] -> {h[:150]}')
    except:
        pass

# ==========================================
# TESTE PARA PCI CONCURSOS (Provas e Simulados)
# ==========================================
print("\n=== Testando PCI Concursos ===")

pci_urls = [
    "https://www.pciconcursos.com.br/provas/",
    "https://www.pciconcursos.com.br/simulados/"
]

for pci_url in pci_urls:
    print(f"\nBuscando categorias em: {pci_url}")
    try:
        r_pci = requests.get(pci_url, headers=headers, timeout=10)
        soup_pci = BeautifulSoup(r_pci.text, 'html.parser')
        
        # O PCI Concursos lista as provas/simulados em tags <a> soltas pelo corpo ou em listas
        pci_links = []
        for a in soup_pci.find_all('a', href=True):
            href = a.get('href', '')
            # Filtra links que são categorias de provas ou simulados
            if '/provas/' in href or '/simulados/' in href:
                # Evita links genéricos de paginação ou cabeçalho
                if len(href.split('/')) > 4 or 'testes-anteriores' in href:
                    pci_links.append((a.text.strip(), href))
                    
        print(f"Encontrados {len(pci_links)} links de categorias.")
        
        # Mostra os 5 primeiros
        for title, link in pci_links[:5]:
            full_link = link if link.startswith('http') else 'https://www.pciconcursos.com.br' + link
            print(f"  [{title[:60]}] -> {full_link}")
            
    except Exception as e:
        print(f"Erro ao acessar {pci_url}: {e}")
