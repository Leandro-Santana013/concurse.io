from playwright.sync_api import sync_playwright
from playwright._impl._errors import TimeoutError

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
        
        pdf_bytes = None
        try:
            print("Esperando download...")
            with page.expect_download(timeout=10000) as dl_info:
                r = page.goto(u)
            dl = dl_info.value
            print("Foi download como anexo!", dl.url)
            import tempfile
            import os
            d = tempfile.mkdtemp()
            dp = os.path.join(d, "file.pdf")
            dl.save_as(dp)
            with open(dp, "rb") as f:
                pdf_bytes = f.read()
        except Exception as e:
            print("Nao foi download (timeout), vamos ver se foi inline:", type(e))
            # Se r estiver definido...
            # porem r so e definido se o goto terminar ANTES do timeout.
        
        if pdf_bytes:
            print("PDF OK, bytes:", len(pdf_bytes))
        browser.close()

if __name__ == '__main__':
    test()
