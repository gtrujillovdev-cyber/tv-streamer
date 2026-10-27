FROM python:3.11-slim

# Instalar dependencias del sistema (adb, ffmpeg, procps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    adb \
    ffmpeg \
    iputils-ping \
    procps \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código del proyecto
COPY . .

# Exponer puerto de Streamlit (8501) y puertos de streaming (8080-8085)
EXPOSE 8501
EXPOSE 8080-8085

# Volumen para videos
VOLUME ["/videos"]

# Variables de entorno
ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
