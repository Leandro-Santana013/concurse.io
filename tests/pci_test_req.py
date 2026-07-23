import requests
from bs4 import BeautifulSoup
import time

def test():
    # 1. Fetch exam page
    url = "https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    
    s = requests.Session()
    r = s.get(url, headers=headers)
    print("Page status:", r.status_code)
    
    soup = BeautifulSoup(r.text, 'html.parser')
    loc = soup.find('a', class_='prova-pdf-link')
    arq = loc['data-arquivo']
    tok = loc['data-code']
    
    u = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
    print("Download URL:", u)
    
    headers['Referer'] = url
    
    # Let's do a request and see what it redirects to
    r2 = s.get(u, headers=headers, allow_redirects=False)
    print("Download status:", r2.status_code)
    if 'Location' in r2.headers:
        print("Redirect Location:", r2.headers['Location'])
    else:
        print("No redirect. Body snippet:", r2.text[:200])

if __name__ == '__main__':
    test()
