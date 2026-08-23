import os, sys
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

import os
import sys
import requests
import fitz

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath('.'))
from services.pdf_pipeline import parse_exam_document

def download_and_extract(url: str, output_pdf: str, output_md: str):
    print("=" * 75)
    print(f"📥 Baixando PDF da Prova: {url}")
    print("=" * 75)
    
    os.makedirs(os.path.dirname(output_pdf) or '.', exist_ok=True)
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    
    with open(output_pdf, "wb") as f:
        f.write(resp.content)
    
    print(f"✅ PDF salvo com sucesso em: {output_pdf} ({len(resp.content) / 1024:.1f} KB)")
    
    doc = fitz.open(output_pdf)
    total_pages = len(doc)
    doc.close()
    
    print(f"⚙️ Executando pipeline de extração híbrido ({total_pages} páginas)...")
    questions = parse_exam_document(
        pdf_bytes_or_path=output_pdf,
        exam_id=101,
        extract_images=True
    )
    
    print(f"📊 Total de Questões Extraídas: {len(questions)}")
    
    md_lines = [
        f"# 📄 Caderno de Prova Extraído — concurse.io\n",
        f"- **Fonte/URL:** [{url}]({url})",
        f"- **Total de Páginas:** {total_pages}",
        f"- **Total de Questões Extraídas:** {len(questions)}\n",
        "---\n"
    ]
    
    for q in questions:
        q_num = q.get('numero_questao', '?')
        disciplina = q.get('disciplina', 'Geral')
        enunciado = q.get('enunciado', '').strip()
        opcoes = q.get('opcoes', {})
        resposta = q.get('resposta', '')
        imagens = q.get('images') or []
        
        md_lines.append(f"## Questão {q_num}")
        if disciplina and disciplina != 'Geral':
            md_lines.append(f"> **Disciplina:** {disciplina}\n")
        
        # Atrela as imagens / diagramas recortados da questão
        if imagens:
            for img_idx, img_path in enumerate(imagens, 1):
                # Normaliza caminho para relativo ao .md ou absoluto
                rel_img_path = img_path.lstrip('/')
                md_lines.append(f"![Diagrama/Figura da Questão {q_num} (Imagem {img_idx})](../{rel_img_path})\n")
        
        md_lines.append(f"{enunciado}\n")
        
        if opcoes:
            md_lines.append("### Alternativas:")
            if isinstance(opcoes, dict):
                for letra, texto in sorted(opcoes.items()):
                    md_lines.append(f"- **({letra})** {texto}")
            elif isinstance(opcoes, list):
                for opt in opcoes:
                    if isinstance(opt, dict):
                        md_lines.append(f"- **({opt.get('letra', '')})** {opt.get('texto', '')}")
                    else:
                        md_lines.append(f"- {opt}")
        
        if resposta:
            md_lines.append(f"\n*Gabarito identificado:* **{resposta}**\n")
            
        md_lines.append("\n---\n")
    
    with open(output_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
        
    print(f"🎉 Documento Markdown gerado com sucesso em: {output_md}")

if __name__ == "__main__":
    pdf_url = "https://anexos.cdn.selecao.net.br/uploads/227/concursos/210/anexos/88e63355-79f7-4c00-ae31-c9f73541120f.pdf"
    local_pdf = os.path.join("pdfs", "prova_teste_download.pdf")
    local_md = os.path.join("pdfs", "prova_extraida.md")
    download_and_extract(pdf_url, local_pdf, local_md)
