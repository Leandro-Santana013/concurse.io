from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        
        print("Indo para Petrobras...")
        page.goto('https://www.pciconcursos.com.br/provas/download/tecnico-em-administracao-e-controle-junior-petrobras-cesgranrio-2010', timeout=20000)
        
        page.wait_for_selector('a.prova-pdf-link')
        loc = page.locator('a.prova-pdf-link').nth(0)
        
        u = f"https://www.pciconcursos.com.br/download/{loc.get_attribute('data-arquivo')}?token={loc.get_attribute('data-code')}"
        print("URL download:", u)
        
        r = context.request.get(u, headers={'Referer': 'https://www.pciconcursos.com.br/provas/download/tecnico-em-administracao-e-controle-junior-petrobras-cesgranrio-2010'})
        print("Status code:", r.status)
        print("URL Final:", r.url)
        body = r.body()
        print('Len:', len(body), 'Type:', r.headers.get('content-type'))
        if body[:4] == b'%PDF':
            print("PDF VALIDO!")
        else:
            print("Conteudo invalido:", body[:100])
        
        browser.close()

if __name__ == '__main__':
    test()
