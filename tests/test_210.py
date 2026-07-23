from playwright.sync_api import sync_playwright

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print("Acessando informacoes/210...")
        page.goto("https://idcap.selecao.net.br/informacoes/210/", timeout=30000, wait_until='domcontentloaded')
        
        title = page.evaluate("() => { const h1 = document.querySelector('h1'); const h2 = document.querySelector('h2'); return (h1 ? h1.innerText : (h2 ? h2.innerText : '')); }")
        print("TITULO DO CONCURSO:", title)
        
        all_links = page.query_selector_all("a")
        for a in all_links:
            href = a.get_attribute("href")
            if href and ('.pdf' in href.lower() or '/download/' in href.lower()):
                text = a.evaluate("el => el.innerText.trim()")
                text_lower = text.lower()
                print(f"  - {text} : {href}")
                
        browser.close()

if __name__ == "__main__":
    test()
