from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
            ignore_https_errors=True,
            accept_downloads=True
        )
        page = context.new_page()
        
        # Bypass webdriver detection
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        url = 'https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010'
        page.goto(url, timeout=60000, wait_until="domcontentloaded")
        
        loc = page.locator('a.prova-pdf-link').nth(0)
        arq = loc.get_attribute("data-arquivo")
        tok = loc.get_attribute("data-code")
        u = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
        
        try:
            with page.expect_download(timeout=10000) as dl_info:
                r = page.goto(u, referer=url)
            print("Download recebido!", dl_info.value.url)
        except Exception as e:
            print("Erro no expect_download:", e)
            print("Status:", r.status if 'r' in locals() and r else None)
        
        browser.close()

if __name__ == '__main__':
    test()
