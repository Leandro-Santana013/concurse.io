import os
import sys
import glob
import json
import re

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from services.pdf_pipeline import parse_exam_document

def audit_pdfs():
    bancas_dir = r"c:\Users\nicky\Downloads\provas_bancas\provas_bancas"
    pdf_files = glob.glob(os.path.join(bancas_dir, "*", "*.pdf"))
    print(f"Total PDFs found in bancas: {len(pdf_files)}")
    
    # Select up to 15 diverse PDFs from different bancas
    selected_by_banca = {}
    for p in pdf_files:
        banca = os.path.basename(os.path.dirname(p))
        if banca not in selected_by_banca:
            selected_by_banca[banca] = p
            
    sample_pdfs = list(selected_by_banca.values())[:12]
    
    # Also add OGMO PDF
    ogmo_pdf = os.path.join("pdfs", "19_1787612141.pdf")
    if os.path.exists(ogmo_pdf):
        sample_pdfs.insert(0, ogmo_pdf)
        
    print(f"Auditing {len(sample_pdfs)} sample PDFs...")
    
    results = []
    for pdf_path in sample_pdfs:
        banca_name = os.path.basename(os.path.dirname(pdf_path)) or "LOCAL"
        file_name = os.path.basename(pdf_path)
        print(f"\n--- Testing: [{banca_name}] {file_name} ---")
        try:
            qs = parse_exam_document(pdf_path, exam_id=1, extract_images=False)
            q_count = len(qs)
            q_nums = [q.get('numero_questao') for q in qs]
            
            # Check sequential integrity
            int_nums = []
            for n in q_nums:
                try:
                    int_nums.append(int(n))
                except Exception:
                    pass
            
            is_seq = False
            gaps = []
            if int_nums:
                expected = list(range(int_nums[0], int_nums[-1] + 1))
                gaps = sorted(set(expected) - set(int_nums))
                is_seq = (len(gaps) == 0 and len(int_nums) == len(expected))
                
            # Check option counts
            opt_counts = [len(q.get('opcoes', {})) for q in qs]
            opt_distribution = {}
            for oc in opt_counts:
                opt_distribution[oc] = opt_distribution.get(oc, 0) + 1
                
            # Check for corrupted URLs or "-d" artifacts in statements
            corrupted_urls = 0
            for q in qs:
                stmt = q.get('enunciado', '')
                if 'D) e-' in stmt or 'D) ik-' in stmt or re.search(r'\bD\)\s+[a-z0-9\-]+(?:tumblr|\.com|\.org|\.br)', stmt):
                    corrupted_urls += 1
                    
            print(f"  Count: {q_count} questions | Min: {int_nums[0] if int_nums else '?'} | Max: {int_nums[-1] if int_nums else '?'}")
            print(f"  Option distributions: {opt_distribution}")
            if gaps:
                print(f"  Gaps: {gaps[:10]} (total missing: {len(gaps)})")
            if corrupted_urls > 0:
                print(f"  ⚠️ Corrupted URL/Bullet artifacts found in {corrupted_urls} questions!")
                
            results.append({
                'banca': banca_name,
                'file': file_name,
                'count': q_count,
                'gaps_count': len(gaps),
                'opt_dist': opt_distribution,
                'corrupted_urls': corrupted_urls
            })
        except Exception as e:
            print(f"  ❌ Error: {e}")
            results.append({
                'banca': banca_name,
                'file': file_name,
                'error': str(e)
            })

    print("\n" + "="*70)
    print("SUMMARY AUDIT REPORT:")
    print("="*70)
    for r in results:
        if 'error' in r:
            print(f"[{r['banca']}] {r['file']}: ERROR {r['error']}")
        else:
            print(f"[{r['banca']}] {r['file']}: {r['count']} qs (Gaps: {r['gaps_count']}, Corrupt URLs: {r['corrupted_urls']}, Opts: {r['opt_dist']})")

if __name__ == '__main__':
    audit_pdfs()
