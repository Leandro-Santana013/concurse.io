from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(ignore_https_errors=True)
        page.goto('https://www.pciconcursos.com.br/provas/download/escriturario-agente-comercial-banco-do-brasil-cesgranrio-2023', timeout=20000)
        loc = page.locator("a.prova-pdf-link[data-acao='baixar']")
        print(f"Encontrou {loc.count()} links")
        for i in range(loc.count()):
            arq = loc.nth(i).get_attribute("data-arquivo")
            tok = loc.nth(i).get_attribute("data-code")
            print(f"Link {i}: arq={arq}, tok={tok}")
        browser.close()

if __name__ == '__main__':
    test()
