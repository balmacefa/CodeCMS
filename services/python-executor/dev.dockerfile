FROM ubuntu:22.04

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Actualizar paquetes del sistema
RUN apt-get update

# Instalar dependencias necesarias
RUN apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    build-essential \
    wget \
    libgl1-mesa-glx \
    libxi6 \
    libxrender1 \
    libxrandr2 \
    libxcursor1 \
    libopenal1 \
    libsndfile1 \
    libfreetype6 \
    libpython3.11 \
    libpython3.11-dev

# Limpiar cachés de apt para reducir tamaño de la imagen
RUN rm -rf /var/lib/apt/lists/*

# Configurar Python 3.11 como predeterminado
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
RUN update-alternatives --config python3

# Crear un enlace simbólico de python3 a python
RUN ln -s /usr/bin/python3 /usr/bin/python

# Copiar archivo de dependencias e instalarlas
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Instalar herramientas adicionales para desarrollo
RUN python3 -m pip install watchdog debugpy

# Exponer puertos necesarios
EXPOSE 8000
EXPOSE 5678

# Comando por defecto
CMD ["sh", "-c", "python -m debugpy --listen 0.0.0.0:5678 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
