from curl_cffi import requests
from bs4 import BeautifulSoup

def test():
    url = "https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010"
    
    s = requests.Session(impersonate="chrome110")
    r = s.get(url)
    print("Page status:", r.status_code)
    
    soup = BeautifulSoup(r.text, 'html.parser')
    loc = soup.find('a', class_='prova-pdf-link')
    arq = loc['data-arquivo']
    tok = loc['data-code']
    
    u = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
    print("Download URL:", u)
    
    headers = {'Referer': url}
    r2 = s.get(u, headers=headers, allow_redirects=False)
    print("Download status:", r2.status_code)
    if 'Location' in r2.headers:
        print("Redirect Location:", r2.headers['Location'])
    else:
        print("No redirect.")

if __name__ == '__main__':
    test()
