from playwright.sync_api import sync_playwright

def find_contest():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        url_base = "https://idcap.selecao.net.br"
        try:
            page.goto(f"{url_base}/index/3/", timeout=30000, wait_until='domcontentloaded')
        except Exception as e:
            print("Erro ao carregar /index/3/:", e)
            
        links = page.query_selector_all("a[href*='/informacoes/']")
        found_url = None
        for a in links:
            text = a.evaluate("el => el.innerText.toLowerCase()")
            if "portuário" in text or "portuario" in text or "ogmo" in text:
                found_url = a.get_attribute('href')
                print(f"CONCURSO ENCONTRADO: {text.strip()} -> {found_url}")
                break
                
        if found_url:
            full_url = f"{url_base}{found_url}" if found_url.startswith('/') else found_url
            print(f"Acessando {full_url}...")
            try:
                page.goto(full_url, timeout=30000, wait_until='domcontentloaded')
            except Exception as e:
                print("Erro ao carregar concurso:", e)
            
            all_links = page.query_selector_all("a")
            for a in all_links:
                href = a.get_attribute("href")
                if href and ('.pdf' in href.lower() or '/download/' in href.lower()):
                    text = a.evaluate("el => el.innerText.trim()")
                    print(f"  - {text} : {href}")
        else:
            print("Não achou em /index/3/.")
                        
        browser.close()

if __name__ == "__main__":
    find_contest()
