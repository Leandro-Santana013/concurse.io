import requests
from bs4 import BeautifulSoup

def test():
    s = requests.Session()
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    s.headers.update(headers)
    page_url = 'https://www.pciconcursos.com.br/provas/download/escriturario-agente-comercial-banco-do-brasil-s-a-cesgranrio-2021'
    res = s.get(page_url)
    soup = BeautifulSoup(res.text, 'html.parser')
    links = soup.select('a')
    for link in links:
        arquivo = link.get('data-arquivo')
        token = link.get('data-code')
        acao = link.get('data-acao')
        if arquivo and token and acao == 'baixar':
            url = f"https://www.pciconcursos.com.br/download/{arquivo}?token={token}"
            print("Tentando", url)
            s.headers.update({'Referer': page_url})
            r2 = s.get(url)
            print("Status:", r2.status_code)
            print("Content-Type:", r2.headers.get('Content-Type'))
            print("Tamanho:", len(r2.content))
            break

if __name__ == '__main__':
    test()
