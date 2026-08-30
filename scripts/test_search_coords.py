import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

import fitz

doc = fitz.open('pdfs/56_1788095849.pdf')

def get_exact_question_coords(doc):
    q_map = {}
    for p_idx, page in enumerate(doc):
        for q_num in range(1, 201):
            if q_num in q_map:
                continue
            # Search for variants: "Questão 01", "Questão 1", "01.", "1."
            queries = [
                f"Questão {q_num:02d}",
                f"Questão {q_num}",
                f"QUESTÃO {q_num:02d}",
                f"QUESTÃO {q_num}",
                f"ITEM {q_num:02d}",
                f"ITEM {q_num}",
            ]
            for q_str in queries:
                rects = page.search_for(q_str)
                if rects:
                    # Pick the top-left-most match
                    r = rects[0]
                    q_map[q_num] = (p_idx, r.x0, r.y0)
                    break
    return q_map

coords = get_exact_question_coords(doc)
for q_n in [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]:
    print(f"Q#{q_n} exact coords: {coords.get(q_n)}")
