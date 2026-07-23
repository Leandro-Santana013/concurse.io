from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True, accept_downloads=True)
        page = context.new_page()
        
        try:
            page.goto('https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010', timeout=60000)
        except Exception as e:
            pass
            
        page.wait_for_selector('a.prova-pdf-link')
        loc = page.locator('a.prova-pdf-link').nth(0)
        
        print("Clicando no botão...")
        try:
            with page.expect_download(timeout=10000) as dl_info:
                loc.click()
            dl = dl_info.value
            print("Download recebido via click:", dl.url)
        except Exception as e:
            print("Erro no expect_download via click:", e)
            print("URL final da pagina:", page.url)
        
        browser.close()

if __name__ == '__main__':
    test()
