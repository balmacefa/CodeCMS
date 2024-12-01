# Archivo: dev.dockerfile

FROM python:3.11-slim

# Configurar directorio de trabajo
WORKDIR /app

# Evitar la generación de archivos .pyc en el contenedor
ENV PYTHONDONTWRITEBYTECODE=1

# Desactivar el buffer de salida para facilitar el logging
ENV PYTHONUNBUFFERED=1

# Instalar dependencias del sistema necesarias para desarrollo
RUN apt-get update && apt-get install -y --no-install-recommends build-essential
RUN rm -rf /var/lib/apt/lists/*

# Copiar archivo de dependencias e instalarlas
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar herramientas adicionales para desarrollo
RUN pip install watchdog debugpy # Agregar debugpy para depuración

# Exponer los puertos necesarios
# Puerto de la aplicación
EXPOSE 8000
# Puerto de depuración remota
EXPOSE 5678

# Comando por defecto para modo desarrollo con depuración habilitada
CMD ["sh", "-c", "python -m debugpy --listen 0.0.0.0:5678 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
