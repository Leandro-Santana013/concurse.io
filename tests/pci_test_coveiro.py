from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        
        print("Indo para Araxa Coveiro...")
        page.goto('https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-coveiro-prefeitura-araxa-mg-gestao-concurso-2010', timeout=20000)
        
        page.wait_for_selector('a.prova-pdf-link')
        loc = page.locator('a.prova-pdf-link')
        print("Links:", loc.count())
        
        for i in range(loc.count()):
            arq = loc.nth(i).get_attribute("data-arquivo")
            tok = loc.nth(i).get_attribute("data-code")
            u = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
            print(f"Tentando URL {i}:", u)
            
            r = context.request.get(u, headers={'Referer': 'https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-coveiro-prefeitura-araxa-mg-gestao-concurso-2010'})
            print(f"Status {i}:", r.status)
            body = r.body()
            print(f"Len {i}:", len(body))
            if body[:4] == b'%PDF':
                print("PDF VALIDO!")
                break
        
        browser.close()

if __name__ == '__main__':
    test()
