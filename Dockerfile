FROM python:3.11-slim

WORKDIR /app

# Instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o código
COPY . .

# Expor a porta da aplicação FastAPI
EXPOSE 8000

# Rodar a aplicação FastAPI ASGI com Uvicorn
CMD ["uvicorn", "fastapi_app:app", "--host", "0.0.0.0", "--port", "8000"]
