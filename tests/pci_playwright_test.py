from playwright.sync_api import sync_playwright
import time

def test_pci():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        def handle_request(req):
            if req.resource_type in ['document', 'fetch', 'xhr'] or '.pdf' in req.url:
                print(f"[{req.method}] {req.url}")
        
        page.on("request", handle_request)
        print("Indo para a pagina...")
        page.goto('https://www.pciconcursos.com.br/provas/download/escriturario-agente-comercial-banco-do-brasil-s-a-cesgranrio-2021', timeout=20000)
        
        links = page.query_selector_all('a.prova-pdf-link')
        for a in links:
            arquivo = a.get_attribute('data-arquivo')
            acao = a.get_attribute('data-acao')
            if arquivo and 'gabarito' not in arquivo.lower() and acao == 'baixar':
                print(f"Clicando em: {arquivo}")
                a.click()
                time.sleep(5)
                break
        browser.close()

if __name__ == '__main__':
    test_pci()
