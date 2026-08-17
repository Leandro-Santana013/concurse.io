FROM python:3.9-slim

WORKDIR /app

# Instalar dependências
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copiar o código
COPY . .

# Expor a porta exigida pelo Hugging Face
EXPOSE 7860

# Rodar a aplicação Flask
CMD ["gunicorn", "-b", "0.0.0.0:7860", "app:app"]
