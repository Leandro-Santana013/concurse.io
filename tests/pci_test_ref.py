from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        # Use a custom user agent to avoid HeadlessChrome detection
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            ignore_https_errors=True, 
            accept_downloads=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        exam_url = 'https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010'
        
        # We can use wait_until="domcontentloaded" to avoid hanging on ads
        page.goto(exam_url, timeout=20000, wait_until="domcontentloaded")
        
        loc = page.locator('a.prova-pdf-link').nth(0)
        arq = loc.get_attribute("data-arquivo")
        tok = loc.get_attribute("data-code")
        u = f"https://www.pciconcursos.com.br/download/{arq}?token={tok}"
        print("URL montada:", u)
        
        try:
            r = page.goto(u, referer=exam_url, timeout=20000)
            print("Status page.goto:", r.status if r else None)
            print("URL final da pagina:", page.url)
            print("Tamanho do body:", len(r.body()) if r else 0)
        except Exception as e:
            print("Erro no page.goto:", e)
        
        browser.close()

if __name__ == '__main__':
    test()
