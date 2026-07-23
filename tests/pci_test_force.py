from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(ignore_https_errors=True, accept_downloads=True, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
        page = context.new_page()
        
        page.goto('https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010', timeout=60000, wait_until="domcontentloaded")
        
        page.wait_for_selector('a.prova-pdf-link')
        loc = page.locator('a.prova-pdf-link').nth(0)
        
        print("Clicando no botão...")
        try:
            with page.expect_download(timeout=10000) as dl_info:
                loc.click(force=True)
            dl = dl_info.value
            print("Download recebido via click:", dl.url)
        except Exception as e:
            print("Erro no expect_download via click:", e)
            print("URL final da pagina:", page.url)
        
        browser.close()

if __name__ == '__main__':
    test()
