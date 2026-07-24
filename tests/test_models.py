import os, time, sys
from dotenv import load_dotenv
from google import genai
from orchestrator import ModelManager, ApiKeyManager

load_dotenv()
api_keys = ApiKeyManager()
if not api_keys.keys:
    print('No API keys found')
    sys.exit(1)
genai.configure(api_key=api_keys.keys[0])

manager = ModelManager()
prompt = 'Responda apenas com a palavra TESTE e nada mais.'

print('--- Iniciando Teste de Modelos ---')
for name, model in manager.models.items():
    print(f'Testando modelo {name}...')
    start = time.time()
    try:
        res = model.generate_content(prompt)
        elapsed = time.time() - start
        print(f'  Sucesso! Tempo: {elapsed:.2f}s | Resposta: {res.text.strip()}')
    except Exception as e:
        print(f'  Falha! Erro: {e}')
print('--- Fim do Teste ---')

