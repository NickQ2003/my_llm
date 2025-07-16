# backend/Dockerfile (ajusta el path si tu main_cloud.py está en /env o /backend)
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main_cloud:app", "--host", "0.0.0.0", "--port", "8000"]
# Ajusta el nombre del archivo main_cloud.py si es necesario