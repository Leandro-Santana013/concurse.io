import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import os

def test():
    options = uc.ChromeOptions()
    options.headless = False 
    
    # Enable automatic downloads without prompt
    prefs = {
        "download.default_directory": os.path.abspath(os.getcwd()),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    options.add_experimental_option("prefs", prefs)
    
    driver = uc.Chrome(options=options, version_main=150)
    
    try:
        url = 'https://www.pciconcursos.com.br/provas/download/auxiliar-de-servico-auxiliar-de-servicos-gerais-feminino-prefeitura-araxa-mg-gestao-concurso-2010'
        print("Acessando pagina do exame...")
        driver.get(url)
        
        # Wait for the link
        wait = WebDriverWait(driver, 30)
        loc = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a.prova-pdf-link")))
        
        print("Clicando no link de download...")
        # Scroll to view if needed
        driver.execute_script("arguments[0].scrollIntoView();", loc)
        time.sleep(1)
        loc.click()
        
        print("Esperando 15 segundos para o download terminar...")
        time.sleep(15)
        
        print("Arquivos no diretorio atual:")
        for f in os.listdir('.'):
            if f.endswith('.pdf') or 'codigo' in f:
                print("Encontrado:", f)
        
    except Exception as e:
        print("Erro:", e)
    finally:
        driver.quit()

if __name__ == '__main__':
    test()
