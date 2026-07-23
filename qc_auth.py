import os
from playwright.sync_api import sync_playwright

def login_qc():
    cookie_path = os.path.join(os.path.dirname(__file__), 'qc_cookies.json')
    
    with sync_playwright() as p:
        # Abre navegador visível (headless=False)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        
        print("Abrindo página de login do QConcursos...")
        page.goto('https://www.qconcursos.com/login')
        
        try:
            # Espera até que o usuário faça o login e a página redirecione para o painel
            # Quando a URL parar de conter '/login', assumimos que o login foi feito.
            page.wait_for_url(lambda url: "login" not in url, timeout=120000) # espera até 2 minutos
            print("Login detectado com sucesso!")
            
            # Salva os cookies de sessão
            context.storage_state(path=cookie_path)
            print(f"Sessão salva em {cookie_path}")
            return True
        except Exception as e:
            print("Login cancelado ou tempo expirado:", e)
            return False
        finally:
            browser.close()

if __name__ == "__main__":
    login_qc()
