from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True, accept_downloads=True)
        page = context.new_page()
        
        page.goto('https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010', timeout=20000)
        
        loc = page.locator('a.prova-pdf-link').nth(0)
        arq = loc.get_attribute("data-arquivo")
        tok = loc.get_attribute("data-code")
        u = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
        print("URL montada:", u)
        
        try:
            r = page.goto(u, timeout=20000)
            print("Status page.goto:", r.status if r else None)
            print("URL final da pagina:", page.url)
            print("Conteudo html:", page.content()[:200])
        except Exception as e:
            print("Erro no page.goto:", e)
        
        browser.close()

if __name__ == '__main__':
    test()
