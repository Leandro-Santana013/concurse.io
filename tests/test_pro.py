import os
from dotenv import load_dotenv
import google.generativeai as genai
from orchestrator import ApiKeyManager
load_dotenv()
api_keys = ApiKeyManager()
genai.configure(api_key=api_keys.keys[0])
model = genai.GenerativeModel('gemini-3.5-pro')
try:
    res = model.generate_content('TESTE')
    print('Sucesso 3.5-pro:', res.text.strip())
except Exception as e:
    print('Falha 3.5-pro:', e)

