import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)

for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
import os
from dotenv import load_dotenv
import google.generativeai as genai
from orchestrator import ApiKeyManager
load_dotenv()
api_keys = ApiKeyManager()
genai.configure(api_key=api_keys.keys[0])
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)

