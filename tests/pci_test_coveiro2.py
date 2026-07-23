from playwright.sync_api import sync_playwright
import time

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(ignore_https_errors=True, accept_downloads=True)
        page = context.new_page()
        
        print("Indo para Araxa Coveiro...")
        page.goto('https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-coveiro-prefeitura-araxa-mg-gestao-concurso-2010', timeout=20000)
        
        page.wait_for_selector('a.prova-pdf-link')
        loc = page.locator('a.prova-pdf-link').nth(0)
        arq = loc.get_attribute("data-arquivo")
        tok = loc.get_attribute("data-code")
        u = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
        print("URL montada:", u)
        
        print("Tentando page.goto na url...")
        try:
            with page.expect_download(timeout=10000) as dl_info:
                r = page.goto(u)
            dl = dl_info.value
            print("Download recebido!", dl.url)
        except Exception as e:
            print("Erro no expect_download:", e)
            print("URL final da pagina:", page.url)
            print("Conteudo html:", page.content()[:200])
        
        browser.close()

if __name__ == '__main__':
    test()
