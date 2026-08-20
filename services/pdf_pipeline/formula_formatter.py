from typing import Tuple
import re

def format_latex_formulas(text: str) -> Tuple[str, bool]:
    """
    Identifica expressões matemáticas e químicas comuns em provas (frações, raízes, expoentes,
    símbolos de conjuntos, equações) e formata para renderização KaTeX inline ($...$).
    
    Retorna:
      - formatted_text: texto com fórmulas formatadas
      - has_latex: booleano indicando se o texto contém notação LaTeX
    """
    if not text:
        return text, False

    original = text
    has_latex = False

    # 1. Substituição de potências simples (ex: x^2, m^3, 10^-5, cm²) usando inline $
    text = re.sub(r'([a-zA-Z0-9\)])\s*[\^]\s*([0-9\+\-]+)', r'$\1^{\2}$', text)
    text = re.sub(r'\b(\d+)\s*²\b', r'$\1^2$', text)
    text = re.sub(r'\b(\d+)\s*³\b', r'$\1^3$', text)
    text = re.sub(r'([m|c|k]m)²', r'$\\text{\1}^2$', text)
    text = re.sub(r'([m|c|k]m)³', r'$\\text{\1}^3$', text)

    # 2. Substituição de Raízes quadradas (ex: √2, √(x+1), \sqrt{...})
    if '√' in text:
        text = re.sub(r'√\s*\(?([a-zA-Z0-9\+\-\*/\s]+)\)?', r'$\\sqrt{\1}$', text)
        has_latex = True

    # 3. Substituição de símbolos matemáticos especiais
    replacements = [
        (r'(\b\d+)\s*([×·])\s*(\d+\b)', r'$\1 \\times \3$'),
        (r'\b(\d+)\s*([÷])\s*(\d+\b)', r'$\1 \\div \3$'),
        (r'\b([a-zA-Z0-9])\s*([≤])\s*([a-zA-Z0-9])', r'$\1 \\leq \3$'),
        (r'\b([a-zA-Z0-9])\s*([≥])\s*([a-zA-Z0-9])', r'$\1 \\geq \3$'),
        (r'\b([a-zA-Z0-9])\s*([≠])\s*([a-zA-Z0-9])', r'$\1 \\neq \3$'),
        (r'\b([a-zA-Z0-9])\s*([∈])\s*([a-zA-Z0-9])', r'$\1 \\in \3$'),
        (r'\b([a-zA-Z0-9])\s*([∉])\s*([a-zA-Z0-9])', r'$\1 \\notin \3$'),
        (r'\b([a-zA-Z0-9])\s*([⊂])\s*([a-zA-Z0-9])', r'$\1 \\subset \3$'),
        (r'\b([a-zA-Z0-9])\s*([∩])\s*([a-zA-Z0-9])', r'$\1 \\cap \3$'),
        (r'\b([a-zA-Z0-9])\s*([∪])\s*([a-zA-Z0-9])', r'$\1 \\cup \3$'),
    ]

    for pat, rep in replacements:
        if re.search(pat, text):
            text = re.sub(pat, rep, text)
            has_latex = True

    # 4. Detecção de frações explícitas (ex: 1/2, 3/4 quando isoladas em contexto numérico)
    if re.search(r'(?<=\s)(\d+)/(\d+)(?=\s|\.|\,)', text):
        text = re.sub(r'(?<=\s)(\d+)/(\d+)(?=\s|\.|\,)', r'$\\frac{\1}{\2}$', text)
        has_latex = True

    # 5. Detecção de blocos já em notação LaTeX ($...$ ou $$...$$ ou \frac)
    if '$' in text or '\\frac' in text or '\\sqrt' in text or '\\sum' in text:
        has_latex = True

    return text, has_latex
