import fitz
import sys
import re
import os

sys.path.insert(0, os.path.abspath('.'))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from services.pdf_pipeline.layout.layout_detector import detect_layout_and_ordered_blocks
from services.crawlers.html_exam_parser import clean_text_artifacts
from services.pdf_pipeline.fallbacks.typography_restorer import restore_exam_typography

doc = fitz.open('pdfs/70_1788234976.pdf')
raw_blocks = []
for p_idx, page in enumerate(doc):
    obs = detect_layout_and_ordered_blocks(page, set())
    for b in obs:
        raw_blocks.append(b['text'])

full_text = '\n\n'.join(raw_blocks)

# Regex robusto universal para opções
pattern_opt = re.compile(
    r'(?:^|\n|\s+)'
    r'(?:'
    r'([A-Ea-e])\s*\(\s*\)|'
    r'\(?\s*([A-Ea-e])\s*\)?\s*[\.\-\–\—\:\)]|'
    r'\(([A-Ea-e])\)|'
    r'\[([A-Ea-e])\]|'
    r'(?<=[\n\r])[ \t]*(?:\d+[\s\(\)\/]+)?\*?([A-Ea-e])\*?(?:\s*[\)\.\-\–\—\:]|[ \t]+)(?=[\w\u00C0-\u00FF\"\'\(\[\$\*\<])|'
    r'(?<=\s)\*?([A-Ea-e])\*?[ \t]+(?=[\w\u00C0-\u00FF\"\'\(\[\$\*\<])'
    r')'
)

def extract_options_and_enunciado(chunk: str):
    matches = []
    for m in pattern_opt.finditer(chunk):
        letter = None
        for g in m.groups():
            if g:
                letter = g.upper()
                break
        if letter:
            matches.append((letter, m.start(), m.end()))
    
    if not matches or len(matches) < 2:
        return chunk, {}

    start_indices = [idx for idx, (let, s, e) in enumerate(matches) if let == 'A']
    valid_sequences = []
    for s_idx in start_indices:
        seq = [matches[s_idx]]
        expected_ord = ord('B')
        for next_m in matches[s_idx + 1:]:
            let, s, e = next_m
            if ord(let) == expected_ord:
                seq.append(next_m)
                expected_ord += 1
                if expected_ord > ord('E'):
                    break
        if len(seq) >= 2:
            score = len(seq) * 1000 + (seq[0][1] / max(1, len(chunk))) * 100
            valid_sequences.append((score, seq))

    if not valid_sequences:
        return chunk, {}

    valid_sequences.sort(key=lambda x: x[0], reverse=True)
    best_seq = valid_sequences[0][1]

    enunciado = chunk[:best_seq[0][1]].strip()
    options = {}
    for o_idx, (let, s_val, e_val) in enumerate(best_seq):
        opt_s = e_val
        opt_e = best_seq[o_idx + 1][1] if o_idx + 1 < len(best_seq) else len(chunk)
        opt_content = chunk[opt_s:opt_e].strip()
        opt_content = re.sub(r'^[A-Ea-e]\s*[\(\[]\s*[\)\]]\s*', '', opt_content)
        opt_content = re.sub(r'^\(?[A-Ea-e]\s*[\)\.\-–—:]\s*', '', opt_content)
        opt_content = clean_text_artifacts(opt_content)
        options[let] = opt_content

    return enunciado, options

# Split by QUESTÃO headers
q_splits = list(re.finditer(r'(?:^|\n)\s*(?:QUEST[AÃ\u00C3\ufffd\?]?O\s+|ITEM\s+)0*(\d{1,3})\b', full_text, re.IGNORECASE))
print(f'Total question headers in full_text: {len(q_splits)}')

results = []
for idx, q_m in enumerate(q_splits):
    q_num = int(q_m.group(1))
    s_pos = q_m.end()
    e_pos = q_splits[idx+1].start() if idx+1 < len(q_splits) else len(full_text)
    chunk = full_text[s_pos:e_pos].strip()
    
    enunciado, opts = extract_options_and_enunciado(chunk)
    results.append((q_num, len(opts), enunciado, opts))

print(f'Processed {len(results)} questions.')
opt_dist = {}
for q_num, n_opts, _, _ in results:
    opt_dist[n_opts] = opt_dist.get(n_opts, 0) + 1
print('Option count distribution:', opt_dist)

# Check unique numbers
extracted_nums = set(r[0] for r in results)
missing = sorted(set(range(1, 181)) - extracted_nums)
print(f'Missing numbers 1..180 ({len(missing)}): {missing}')

imperfect = [r for r in results if r[1] < 5]
print(f'Imperfect questions count: {len(imperfect)}')
for q_num, n_opts, stmt, opts in imperfect:
    print(f'Q{q_num}: {n_opts} options -> keys={list(opts.keys())}')
    print(f'Stmt tail: ...{stmt[-120:]}')
    print('-'*40)
