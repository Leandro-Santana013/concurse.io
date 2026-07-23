import browser_cookie3
import requests
import json
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test():
    print("Extraindo cookies do Chrome...")
    try:
        cj = browser_cookie3.chrome(domain_name='pciconcursos.com.br')
        print(f"Encontrados {len(cj)} cookies.")
    except Exception as e:
        print("Erro ao extrair cookies:", e)
        return
        
    url = 'https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010'
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'Referer': 'https://www.pciconcursos.com.br/provas/araxa/'
    }
    
    print("Acessando pagina com os cookies do usuario...")
    session = requests.Session()
    session.cookies.update(cj)
    session.headers.update(headers)
    
    response = session.get(url, verify=False)
    print("Status:", response.status_code)
    
    if response.status_code != 200:
        print("Ainda bloqueado pelo Turnstile mesmo com cookies.")
        return
        
    soup = BeautifulSoup(response.text, 'html.parser')
    link = soup.select_one("a.prova-pdf-link")
    
    if not link:
        print("Link nao encontrado no HTML retornado.")
        return
        
    arq = link.get("data-arquivo")
    tok = link.get("data-code")
    u = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
    
    print("URL de download:", u)
    
    print("Tentando baixar o arquivo com a sessao...")
    dl = session.get(u, verify=False, allow_redirects=True)
    print("Status Download:", dl.status_code)
    print("URL Final:", dl.url)
    
    if dl.status_code == 200 and 'pdf' in dl.headers.get('Content-Type', '').lower():
        with open('codigo_cookie_test.pdf', 'wb') as f:
            f.write(dl.content)
        print("Sucesso! PDF salvo como codigo_cookie_test.pdf")
    else:
        print("Falha no download.")

if __name__ == '__main__':
    test()
