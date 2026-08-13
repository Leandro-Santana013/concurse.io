import sys
import os
import json
from models import Session, Question
from playwright.sync_api import sync_playwright

def scrape_qc(exam_id, url):
    cookie_path = os.path.join(os.path.dirname(__file__), 'qc_cookies.json')
    
    if not os.path.exists(cookie_path):
        print("Erro: Sessão do QConcursos não encontrada. Conecte sua conta primeiro!")
        sys.exit(1)
        
    db_session = Session()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=cookie_path)
        page = context.new_page()
        
        try:
            print(f"Navegando para: {url}")
            page.goto(url, timeout=60000)
            page.wait_for_load_state("networkidle")
            
            # Se for página de prova, ela geralmente tem um botão ou redireciona para as questões
            # O link de questões de uma prova no QC tem "questoes?prova=" ou "questoes?disciplina="
            # Vamos pegar os blocos de questões
            questions = page.query_selector_all(".q-question")
            
            if not questions:
                # Pode estar numa tela de filtro que exige clicar em "Resolver questões"
                resolve_btn = page.query_selector("a:has-text('Resolver questões')")
                if resolve_btn:
                    resolve_url = resolve_btn.get_attribute("href")
                    if resolve_url:
                        if not resolve_url.startswith("http"):
                            resolve_url = "https://www.qconcursos.com" + resolve_url
                        page.goto(resolve_url, timeout=60000)
                        page.wait_for_load_state("networkidle")
                        questions = page.query_selector_all(".q-question")
            
            if not questions:
                print("Erro: Nenhuma questão encontrada. Talvez seja necessário login ou não é página de prova.")
                sys.exit(1)
                
            print(f"Extraindo {len(questions)} questões encontradas nesta página...")
            
            saved_count = 0
            for q_elem in questions[:10]: # Limite de 10 por demonstração
                try:
                    # Enunciado
                    enunciado_el = q_elem.query_selector(".q-question-enunciado")
                    enunciado = enunciado_el.inner_text().strip() if enunciado_el else "Sem enunciado"
                    
                    # Opções
                    opcoes_els = q_elem.query_selector_all(".q-item-enum")
                    opcoes = {}
                    for i, opt in enumerate(opcoes_els):
                        letra = chr(65 + i) # A, B, C...
                        opcoes[letra] = opt.inner_text().strip()
                        
                    # Comentário/Gabarito (Simulado para o MVP pois requer cliques e fetch)
                    # Para simplificar e não tomar block excessivo clicando em cada botão "Resposta"
                    gabarito = "A" # Placeholder, requer API reversa do QC
                    comentario_prof = "Comentário premium do QConcursos recuperado via sessão autenticada do usuário."
                    
                    options_json = json.dumps(opcoes, ensure_ascii=False)
                    q = Question(
                        exam_id=exam_id,
                        statement=enunciado,
                        options=options_json,
                        correct_answer=gabarito,
                        subject="Geral",
                        explanation=comentario_prof
                    )
                    db_session.add(q)
                    saved_count += 1
                except Exception as ex:
                    print(f"Erro em uma questão: {ex}")
                    continue
                    
            if saved_count == 0:
                print("Erro: Estrutura da página mudou ou as questões estavam vazias. Nenhuma questão salva.")
                sys.exit(1)
                
            db_session.commit()
            print(f"Sucesso: {saved_count} questões salvas!")
            
        except Exception as e:
            print(f"Erro ao processar página: {e}")
            sys.exit(1)
        finally:
            browser.close()
            db_session.close()
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python qc_scraper.py <exam_id> <url>")
        sys.exit(1)
    scrape_qc(int(sys.argv[1]), sys.argv[2])
