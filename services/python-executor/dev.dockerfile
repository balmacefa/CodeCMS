# Archivo: dev.dockerfile

FROM python:3.11-slim

# Configurar directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias para desarrollo
RUN apt-get update && apt-get install -y --no-install-recommends build-essential
RUN rm -rf /var/lib/apt/lists/*

# Copiar archivo de dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar herramientas adicionales para desarrollo
RUN pip install watchdog

# Exponer el puerto que usará la aplicación
EXPOSE 8000

# Comando por defecto para modo desarrollo con recarga automática
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
