from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import os
import time

def test_stealth():
    url = "https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010"
    
    user_data_dir = os.path.join(os.getcwd(), 'pw_user_data')
    os.makedirs(user_data_dir, exist_ok=True)
    
    with sync_playwright() as p:
        print("Iniciando contexto persistente...")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False, # Precisa ser False pra ter mais chance com Turnstile
            args=[
                '--disable-blink-features=AutomationControlled',
            ]
        )
        
        page = context.new_page()
        
        print("Aplicando stealth...")
        Stealth().apply_stealth_sync(page)
        
        try:
            print("Navegando...")
            page.goto(url)
            
            print("Esperando o link aparecer (ou falhar)...")
            loc = page.locator("a.prova-pdf-link").first
            loc.wait_for(timeout=20000)
            
            print("Clicando no link!")
            with page.expect_download(timeout=20000) as download_info:
                loc.click()
            
            download = download_info.value
            filepath = os.path.join(os.getcwd(), download.suggested_filename)
            download.save_as(filepath)
            print(f"Sucesso! Salvo em: {filepath}")
            
        except Exception as e:
            print("Erro ou bloqueio:", e)
        finally:
            print("Fechando...")
            context.close()

if __name__ == '__main__':
    test_stealth()
