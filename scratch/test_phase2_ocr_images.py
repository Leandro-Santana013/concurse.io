import sys
import os
import io
import fitz
import json

# Adicionar pasta raiz ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.pdf_parser import parse_exam_pdf_deterministic, _find_diagram_clusters

def test_diagram_crop_with_caption():
    print("=== Teste 1: Recorte Inteligente de Diagrama com Inclusao de Legenda ===")
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    
    # Enunciado da questão com menção a figura
    p.insert_text((50, 50), "QUESTAO 1\nConsidere o diagrama esquematico a seguir:", fontsize=10)
    
    # Desenho vetorial (um retângulo)
    shape = p.new_shape()
    shape.draw_rect(fitz.Rect(60, 90, 200, 180))
    shape.finish(color=(0, 0, 1), fill=(0.8, 0.8, 1))
    shape.commit()
    
    # Legenda textual imediatamente abaixo da figura
    p.insert_text((60, 195), "Figura 1 - Esquema do Circuito", fontsize=9)
    
    # Alternativas da questão
    p.insert_text((50, 230), "(A) Alternativa 1\n(B) Alternativa 2\n(C) Alternativa 3\n(D) Alternativa 4\n(E) Alternativa 5\n\nGABARITO: 1-C", fontsize=10)
    
    pdf_bytes = doc.write()
    doc.close()
    
    questions = parse_exam_pdf_deterministic(pdf_bytes, extract_images=True)
    print(f"Questoes extraidas: {len(questions)}")
    for q in questions:
        print(f"Q{q['numero_questao']} -> Imagens associadas: {q['images']}")
        
    assert len(questions) == 1
    assert questions[0]['images'] is not None
    assert len(questions[0]['images']) == 1
    assert questions[0]['resposta'] == 'C'
    
    # Verifica se o arquivo de imagem foi gerado no disco
    rel_path = questions[0]['images'][0].lstrip('/')
    full_img_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), rel_path)
    assert os.path.exists(full_img_path), f"Arquivo de imagem nao encontrado: {full_img_path}"
    print(f"[OK] Imagem salva em: {full_img_path}")
    print("[OK] Teste 1 passou com sucesso!\n")

def test_image_deduplication():
    print("=== Teste 2: Deduplicacao de Imagens e Logos Repetidos ===")
    doc = fitz.open()
    
    # Cria uma imagem simples em memória (100x100 vermelha)
    from PIL import Image
    im = Image.new('RGB', (100, 100), color=(255, 0, 0))
    im_bytes = io.BytesIO()
    im.save(im_bytes, format='PNG')
    im_data = im_bytes.getvalue()
    
    # Página 1 com questão 1 e figura
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50), "QUESTAO 1\nObserve a figura abaixo e responda:\n(A) Opcao A\n(B) Opcao B\n(C) Opcao C\n(D) Opcao D\n(E) Opcao E", fontsize=10)
    p1.insert_image(fitz.Rect(50, 100, 150, 200), stream=im_data)
    
    # Página 2 com questão 2 e a MESMA figura
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 50), "QUESTAO 2\nCom base na mesma figura anterior:\n(A) Opcao A\n(B) Opcao B\n(C) Opcao C\n(D) Opcao D\n(E) Opcao E\n\nGABARITO: 1-A, 2-B", fontsize=10)
    p2.insert_image(fitz.Rect(50, 100, 150, 200), stream=im_data)
    
    pdf_bytes = doc.write()
    doc.close()
    
    questions = parse_exam_pdf_deterministic(pdf_bytes, extract_images=True)
    print(f"Questoes extraidas com imagem: {len(questions)}")
    for q in questions:
        print(f"Q{q['numero_questao']} -> Imagens: {q['images']}")
        
    assert len(questions) == 2
    assert questions[0]['images'] is not None
    assert questions[1]['images'] is not None
    # Como as duas imagens são idênticas, a segunda deve reutilizar a URL da primeira
    assert questions[0]['images'][0] == questions[1]['images'][0]
    print("[OK] Deduplicacao comprovada: Ambas as questoes referenciam a mesma imagem unica!")
    print("[OK] Teste 2 passou com sucesso!\n")

def test_scanned_pdf_ocr_fallback():
    print("=== Teste 3: Fallback de OCR para PDFs Escaneados (RapidOCR) ===")
    
    # Cria uma imagem contendo texto simulando uma página escaneada
    from PIL import Image, ImageDraw
    img = Image.new('RGB', (800, 1000), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    draw.text((50, 50), "PORTUGUES", fill=(0, 0, 0))
    draw.text((50, 100), "QUESTAO 1", fill=(0, 0, 0))
    draw.text((50, 130), "Em relacao a concordancia verbal:", fill=(0, 0, 0))
    draw.text((50, 160), "(A) Houveram muitos problemas", fill=(0, 0, 0))
    draw.text((50, 190), "(B) Havia muitos problemas", fill=(0, 0, 0))
    draw.text((50, 220), "(C) Fazem dez anos", fill=(0, 0, 0))
    draw.text((50, 250), "(D) Vende-se casas", fill=(0, 0, 0))
    draw.text((50, 280), "(E) Chegou os alunos", fill=(0, 0, 0))
    draw.text((50, 330), "GABARITO: 1-B", fill=(0, 0, 0))
    
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    
    # Cria um PDF sem texto vetorial (apenas a imagem da página escaneada)
    doc = fitz.open()
    p = doc.new_page(width=595, height=842)
    p.insert_image(fitz.Rect(0, 0, 595, 842), stream=img_bytes.getvalue())
    pdf_bytes = doc.write()
    doc.close()
    
    # Verifica que o PDF não tem camada de texto nativa
    check_doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    native_text = check_doc[0].get_text('text').strip()
    check_doc.close()
    assert len(native_text) == 0, "O PDF de teste nao deveria conter texto vetorial"
    print("[OK] Confirmado que o PDF e 100% escaneado (0 caracteres nativos)")
    
    # Processa com o nosso parser (que aciona o RapidOCR automaticamente)
    questions = parse_exam_pdf_deterministic(pdf_bytes, extract_images=False)
    print(f"Questoes extraidas via RapidOCR: {len(questions)}")
    for q in questions:
        print(f"Q{q['numero_questao']}: {q['enunciado'][:40]}... | Opcoes: {len(q['opcoes']) if q['opcoes'] else 0} | Resposta: {q['resposta']}")
        
    assert len(questions) >= 1
    assert questions[0]['numero_questao'] == '1'
    assert 'B' in questions[0]['opcoes']
    assert questions[0]['resposta'] == 'B'
    print("[OK] Teste 3 passou com sucesso! RapidOCR extraiu com precisao a prova escaneada.\n")

if __name__ == '__main__':
    test_diagram_crop_with_caption()
    test_image_deduplication()
    test_scanned_pdf_ocr_fallback()
    print("[SUCESSO] TODOS OS TESTES DA FASE 2 PASSARAM COM 100% DE SUCESSO!")
