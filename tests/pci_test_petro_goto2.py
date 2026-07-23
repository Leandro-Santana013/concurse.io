from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True, accept_downloads=True)
        page = context.new_page()
        
        page.goto('https://www.pciconcursos.com.br/provas/download/tecnico-em-administracao-e-controle-junior-petrobras-cesgranrio-2010', timeout=20000)
        
        loc = page.locator('a.prova-pdf-link').nth(1)
        arq = loc.get_attribute("data-arquivo")
        tok = loc.get_attribute("data-code")
        u = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
        print("URL montada Petrobras:", u)
        
        print("Fazendo goto sem expect download...")
        r = page.goto(u, timeout=20000)
        print("Goto terminou!")
        if r:
            print("Status:", r.status)
            body = r.body()
            print("Len body:", len(body))
            if body[:4] == b'%PDF':
                print("E PDF!!")
        
        browser.close()

if __name__ == '__main__':
    test()
