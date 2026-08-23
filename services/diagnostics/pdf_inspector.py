import fitz
import re
import os

# Palavras-chave e padrões característicos de documentos administrativos que NÃO são cadernos de questões
ADMINISTRATIVE_PATTERNS = [
    r'\bEDITAL\s+(?:DE\s+)?(?:ABERTURA|CONCURSO|PROCESSO|COMPLEMENTAR|RETIFICA[ÇC][ÃA]O|N[º°\.]?\s*\d+)',
    r'\bCRONOGRAMA\s+(?:PREVISTO|DE\s+EXECU[ÇC][ÃA]O|DO\s+CONCURSO)',
    r'\bRESULTADO\s+(?:FINAL|PRELIMINAR|DA\s+PROVA|DOS\s+RECURSOS|DE\s+HOMOLOGA[ÇC][ÃA]O)',
    r'\bHOMOLOGA[ÇC][ÃA]O\s+(?:DO\s+RESULTADO|FINAL|DAS\s+INSCRI[ÇC][ÕO]ES)',
    r'\bCONVOCA[ÇC][ÃA]O\s+(?:PARA|PARA\s+O\s+TAF|PARA\s+A\s+PROVA|PARA\s+POSSE)',
    r'\bRELA[ÇC][ÃA]O\s+(?:DE\s+INSCRITOS|DOS\s+CANDIDATOS|PRELIMINAR|FINAL)',
    r'\bPARECER\s+(?:DA\s+BANCA|DO\s+RECURSO|T[ÉE]CNICO)',
    r'\bANEXO\s+[I|V|X\d]+\s*[-–—:]\s*(?:CONTE[ÚU]DO\s+PROGRAM[ÁA]TICO|CRONOGRAMA|QUADRO\s+DE\s+VAGAS|FORMUL[ÁA]RIO)',
    r'\bFORMUL[ÁA]RIO\s+DE\s+RECURSO',
    r'\bCOMUNICADO\s+OFICIAL\b',
    r'\bRETIFICA[ÇC][ÃA]O\s+DE\s+EDITAL\b',
    r'\bTERMO\s+DE\s+REFER[ÊE]NCIA\b',
    r'\bRESPOSTA\s+AOS\s+RECURSOS\b'
]

ADMINISTRATIVE_REGEX = re.compile('|'.join(ADMINISTRATIVE_PATTERNS), re.IGNORECASE)

def is_administrative_document(text):
    """Verifica se um texto contém termos característicos de documento administrativo/edital."""
    if not text:
        return False
    return bool(ADMINISTRATIVE_REGEX.search(str(text)))

# Padrões que indicam folhas exclusivas de gabarito
ANSWER_KEY_PATTERNS = [
    r'\bGABARITO\s+OFICIAL\s+(?:DEFINITIVO|PRELIMINAR|DA\s+PROVA)?\b',
    r'\bFOLHA\s+DE\s+RESPOSTAS\b',
    r'\bQUADRO\s+DE\s+RESPOSTAS\b',
    r'\bTABELA\s+DE\s+GABARITO\b'
]
ANSWER_KEY_HEADER_REGEX = re.compile('|'.join(ANSWER_KEY_PATTERNS), re.IGNORECASE)

# Padrões que indicam questões reais com enunciados e alternativas
QUESTION_START_REGEX = re.compile(r'(?:^|\n)\s*(?:QUEST[ÃA]O\s+(\d{1,3})|(\d{1,3})\s*[\.\-\)]\s+(?!(?:DAS|DOS|DO|DA|DE|DISPOSI|CRONOGRAMA|CONTE[ÚU]DO|OBJETO|VAGAS|INSCRI|RECURSOS?)\b)[A-Z\u00C0-\u00DC])', re.IGNORECASE)
OPTION_PATTERN_REGEX = re.compile(r'(?:^|\n)\s*(?:\([A-E]\)|[A-E]\s*[\.\-\)])\s+', re.IGNORECASE)

def inspect_pdf_document(pdf_input):
    """
    Inspeciona rapidamente (< 30ms) o conteúdo e a estrutura do PDF.
    
    Aceita:
      - bytes do PDF
      - caminho para o arquivo PDF (str / os.PathLike)
      - objeto fitz.Document
      
    Retorna um dicionário estruturado:
      {
        "doc_type": "EXAM_QUESTIONS" | "ANSWER_KEY_ONLY" | "ADMINISTRATIVE_DOC" | "UNKNOWN",
        "confidence": float (0.0 a 1.0),
        "reason": str,
        "page_count": int,
        "is_valid_exam": bool,
        "detected_questions_count": int,
        "has_embedded_gabarito": bool
      }
    """
    doc = None
    should_close = False
    
    if isinstance(pdf_input, fitz.Document):
        doc = pdf_input
    elif isinstance(pdf_input, (bytes, bytearray)):
        doc = fitz.open(stream=pdf_input, filetype="pdf")
        should_close = True
    elif isinstance(pdf_input, str) and os.path.exists(pdf_input):
        doc = fitz.open(pdf_input)
        should_close = True
    else:
        return {
            "doc_type": "UNKNOWN",
            "confidence": 0.0,
            "reason": "Entrada de PDF inválida ou arquivo não encontrado.",
            "page_count": 0,
            "is_valid_exam": False,
            "detected_questions_count": 0,
            "has_embedded_gabarito": False
        }

    try:
        page_count = len(doc)
        if page_count == 0:
            return {
                "doc_type": "UNKNOWN",
                "confidence": 1.0,
                "reason": "O documento PDF está vazio (0 páginas).",
                "page_count": 0,
                "is_valid_exam": False,
                "detected_questions_count": 0,
                "has_embedded_gabarito": False
            }

        # Extrai texto das primeiras 2 a 3 páginas para análise rápida
        sample_text = ""
        max_sample_pages = min(3, page_count)
        for i in range(max_sample_pages):
            sample_text += "\n" + doc[i].get_text()

        sample_upper = sample_text.upper()

        # 1. Checagem de Folha de Gabarito Isolada
        option_matches = OPTION_PATTERN_REGEX.findall(sample_text)
        has_gabarito_header = bool(ANSWER_KEY_HEADER_REGEX.search(sample_text))
        gabarito_items = re.findall(r'\b\d{1,3}\s*[-–—:\.\)]\s*[A-Ea-e]\b', sample_text)
        tabular_items = re.findall(r'(?:QUEST[ÃA]O|ITEM|\b)\s*(\d{1,3})\s+([A-Ea-e]|CERTO|ERRADO|C|E)\b', sample_text, re.IGNORECASE)
        
        total_gab_signals = len(gabarito_items) + len(tabular_items)
        if page_count <= 4 and (has_gabarito_header or total_gab_signals >= 12):
            if len(option_matches) < 5 and not re.search(r'\bQUEST[ÃA]O\s+\d+\b', sample_text, re.IGNORECASE):
                return {
                    "doc_type": "ANSWER_KEY_ONLY",
                    "confidence": 0.94,
                    "reason": f"Folha de gabarito isolada detectada ({total_gab_signals} respostas mapeadas).",
                    "page_count": page_count,
                    "is_valid_exam": False,
                    "detected_questions_count": 0,
                    "has_embedded_gabarito": True
                }

        # 2. Coleta de amostra mais ampla para documentos com capa/instruções
        full_sample = sample_text
        if page_count > 3:
            # Pega também páginas 3, meio e penúltima/última para não ser enganado por capas
            extra_pages = [min(3, page_count - 1), page_count // 2, page_count - 1]
            for ep in set(extra_pages):
                if ep >= max_sample_pages:
                    full_sample += "\n" + doc[ep].get_text()

        all_q_starts = QUESTION_START_REGEX.findall(full_sample)
        all_options = OPTION_PATTERN_REGEX.findall(full_sample)
        has_cebraspe = bool(re.search(r'\b(CERTO|ERRADO)\b', full_sample, re.IGNORECASE))
        has_embedded_gabarito = bool(ANSWER_KEY_HEADER_REGEX.search(doc[-1].get_text() if page_count > 0 else ""))
        admin_matches = ADMINISTRATIVE_REGEX.findall(sample_text)

        # 3. Se for Documento Administrativo Puro (sem questões e sem alternativas)
        if admin_matches and len(all_options) < 4 and not re.search(r'\bQUEST[ÃA]O\s+\d+\b', full_sample, re.IGNORECASE):
            first_term = admin_matches[0]
            return {
                "doc_type": "ADMINISTRATIVE_DOC",
                "confidence": 0.96,
                "reason": f"Documento administrativo detectado ({first_term.strip()}). Não é um caderno de questões.",
                "page_count": page_count,
                "is_valid_exam": False,
                "detected_questions_count": 0,
                "has_embedded_gabarito": False
            }

        # 4. Se encontrou padrões consistentes de questões em qualquer parte do caderno
        if len(all_q_starts) >= 2 or (len(all_options) >= 5) or (has_cebraspe and len(all_q_starts) >= 1):
            return {
                "doc_type": "EXAM_QUESTIONS",
                "confidence": 0.95,
                "reason": "Caderno de questões com enunciados e alternativas estruturadas.",
                "page_count": page_count,
                "is_valid_exam": True,
                "detected_questions_count": len(all_q_starts),
                "has_embedded_gabarito": has_embedded_gabarito
            }

        # 5. Caso indeterminado / PDF escaneado sem camada de texto nativa
        if page_count >= 2:
            return {
                "doc_type": "EXAM_QUESTIONS",
                "confidence": 0.65,
                "reason": "Documento multipágina (possível PDF escaneado que requer OCR).",
                "page_count": page_count,
                "is_valid_exam": True,
                "detected_questions_count": 0,
                "has_embedded_gabarito": False
            }

        return {
            "doc_type": "UNKNOWN",
            "confidence": 0.40,
            "reason": "Estrutura do documento não reconhecida como prova de concurso.",
            "page_count": page_count,
            "is_valid_exam": False,
            "detected_questions_count": 0,
            "has_embedded_gabarito": False
        }

    finally:
        if should_close and doc:
            doc.close()
