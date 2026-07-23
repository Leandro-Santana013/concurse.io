"""
Test Gemini PDF URL suggestion
"""
import os, json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)

query = "trabalhador portuario avulso"

model = genai.GenerativeModel('gemini-2.5-flash')
prompt = f"""
Você é um especialista em concursos públicos brasileiros. O usuário quer encontrar provas reais em PDF de:
"{query}"

Sua tarefa: fornecer URLs REAIS e ACESSÍVEIS de arquivos PDF de provas de concurso sobre esse tema.

Fontes preferidas (em ordem):
1. Sites gov.br
2. Sites de bancas: IDECAN, IDCAP, IBFC, CEBRASPE, FCC, VUNESP, CESGRANRIO

IMPORTANTE:
- Retorne APENAS um JSON válido
- Só coloque URLs que você tem ALTA confiança que existem
- Se não souber, retorne []

Formato:
[
  {{"title": "Título", "url": "https://url.pdf"}},
]
"""

response = model.generate_content(prompt)
print("Resposta Gemini:")
print(response.text)
