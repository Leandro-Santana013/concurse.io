from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            ignore_https_errors=True
        )
        page = context.new_page()
        print("Indo para a pagina...")
        page.goto('https://www.pciconcursos.com.br/provas/download/agente-municipal-de-transito-prefeitura-maracana-pa-fundacao-cetap-2024', timeout=20000)
        
        page.screenshot(path='pci_debug.png')
        
        loc = page.locator("a.prova-pdf-link[data-acao='baixar']")
        print(f"Encontrou {loc.count()} links.")
        for i in range(loc.count()):
            arq = loc.nth(i).get_attribute("data-arquivo")
            tok = loc.nth(i).get_attribute("data-code")
            print(f"Link {i}: arq={arq}, tok={tok}")
            
if __name__ == '__main__':
    test()
