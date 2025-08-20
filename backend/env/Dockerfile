FROM python:3.11-slim

WORKDIR /app

# Copia requirements primero para cacheo eficiente
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del backend
COPY . .

# Lanza Uvicorn en modo producción
CMD ["sh", "-c", "uvicorn main_cloud:app --host 0.0.0.0 --port 8000 & uvicorn main_cloud:app --host 0.0.0.0 --port 8001 && wait"]
