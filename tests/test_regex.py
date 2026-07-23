import re
import json

def parse_exam_text(text):
    questions = []
    
    # Heurística para separar questões. Ex: "1.", "01.", "Questão 1", "QUESTÃO 01"
    # Procuramos o padrão no início de uma linha
    question_pattern = re.compile(r'\n(?:QUESTÃO\s*)?(\d{1,3})[\.\-\)]\s*(.*?)(?=\n(?:QUESTÃO\s*)?\d{1,3}[\.\-\)]\s*|\Z)', re.DOTALL | re.IGNORECASE)
    
    # Heurística para separar opções. Ex: "A)", "(a)", "a."
    options_pattern = re.compile(r'\n\s*[\(]?([A-Ea-e])[\)\.]\s*(.*?)(?=\n\s*[\(]?[A-Ea-e][\)\.]\s*|\Z)', re.DOTALL)
    
    matches = question_pattern.finditer('\n' + text)
    
    for match in matches:
        q_num = match.group(1)
        q_content = match.group(2).strip()
        
        # Encontrar opções dentro do conteúdo da questão
        opt_matches = list(options_pattern.finditer('\n' + q_content))
        
        options = {}
        statement = q_content
        
        if opt_matches:
            # O enunciado é tudo antes da primeira opção
            statement = q_content[:opt_matches[0].start()].strip()
            for opt_match in opt_matches:
                letter = opt_match.group(1).upper()
                opt_text = opt_match.group(2).strip()
                options[letter] = opt_text
        
        questions.append({
            "enunciado": statement,
            "opcoes": options if options else None,
            "resposta": "A" if options else "Certo"
        })
        
    return questions

# Texto de teste simples
sample = """
1. Qual a capital do Brasil?
A) São Paulo
B) Rio de Janeiro
C) Brasília
D) Salvador
E) Curitiba

2. Sobre a expansão marítima, julgue os itens.
O descobrimento do Brasil ocorreu em 1500.

QUESTÃO 3 - O que é água?
a. Líquido
b. Sólido
c. Gás
"""

print(json.dumps(parse_exam_text(sample), indent=2, ensure_ascii=False))
