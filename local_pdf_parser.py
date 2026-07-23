import re

def parse_exam_text_local(text):
    """
    Tenta extrair questões e alternativas de um texto de PDF de concurso
    usando heurísticas de Expressões Regulares (Regex).
    """
    questions = []
    
    # Normaliza múltiplas quebras de linha para evitar problemas no parser
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Pattern para o início de uma questão:
    # Ex: "1.", "01 -", "QUESTÃO 1", "Questão 01"
    # Grupo 1: Número da questão
    # Grupo 2: Conteúdo da questão (até a próxima questão ou fim do texto)
    question_pattern = re.compile(
        r'\n\s*(?:QUEST[AÃ]O\s*)?(\d{1,3})[\.\-\)]\s*(.*?)(?=\n\s*(?:QUEST[AÃ]O\s*)?\d{1,3}[\.\-\)]\s*|\Z)', 
        re.DOTALL | re.IGNORECASE
    )
    
    # Pattern para opções de múltipla escolha:
    # Ex: "A)", "(A)", "a.", "A - " no início de uma linha
    options_pattern = re.compile(
        r'\n\s*[\(]?([A-Ea-e])[\)\.\-]\s*(.*?)(?=\n\s*[\(]?[A-Ea-e][\)\.\-]\s*|\Z)', 
        re.DOTALL
    )
    
    # Adicionamos um \n artificial no início para o regex capturar a primeira questão se estiver na primeira linha
    matches = list(question_pattern.finditer('\n' + text))
    
    for match in matches:
        q_num = match.group(1)
        q_content = match.group(2).strip()
        
        # Se a questão for muito curta, pode ser falso positivo
        if len(q_content) < 15:
            continue
            
        opt_matches = list(options_pattern.finditer('\n' + q_content))
        
        options = {}
        statement = q_content
        
        if opt_matches:
            # O enunciado é tudo o que vem antes da primeira alternativa
            statement = q_content[:opt_matches[0].start()].strip()
            
            for opt_match in opt_matches:
                letter = opt_match.group(1).upper()
                opt_text = opt_match.group(2).strip()
                options[letter] = opt_text
                
            # Validação básica de opções: se achou apenas "A" e não achou "B",
            # é provável que seja um falso positivo (ex: "a. m. (antes do meio dia)").
            if 'A' in options and 'B' not in options and len(options) == 1:
                options = None
        else:
            options = None

        questions.append({
            "enunciado": statement,
            "opcoes": options,
            "resposta": "A" if options else "Certo"
        })
            
    return questions
