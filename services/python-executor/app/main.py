# main.py

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import uuid  # Para generar IDs únicos de sesión
import importlib.util
import os
from typing import List, Dict, Any
import shutil
import logging
from logging.handlers import RotatingFileHandler
import asyncio  # Importación añadida
from datetime import datetime  # Importación añadida

# Configuración de Logging
logger = logging.getLogger("fastapi_app")
logger.setLevel(logging.DEBUG)  # Establece el nivel mínimo de severidad

# Formato de los logs
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Manejador para el archivo de log con rotación
file_handler = RotatingFileHandler(
    "server.log", maxBytes=5*1024*1024, backupCount=5
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)

# Manejador para la consola
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

# Añadir manejadores al logger
logger.addHandler(file_handler)
logger.addHandler(console_handler)

app = FastAPI()

# Directorio base para almacenar los módulos de cada sesión
BASE_MODULES_DIR = "./modules"

# Crear el directorio base si no existe
if not os.path.exists(BASE_MODULES_DIR):
    os.makedirs(BASE_MODULES_DIR)
    logger.debug(f"Creado directorio base para módulos: {BASE_MODULES_DIR}")

# Modelos de datos

class StartSessionRequest(BaseModel):
    pass  # Ya no se requiere TTL

class StartSessionResponse(BaseModel):
    session_id: str

class ModuleUpload(BaseModel):
    name: str
    files: Dict[str, str]  # filename: content

class UploadModulesRequest(BaseModel):
    modules: List[ModuleUpload]

class ExecutionRequest(BaseModel):
    function: str
    params: Dict[str, Any]

class CloseSessionRequest(BaseModel):
    pass  # No es necesario incluir el session_id en el cuerpo, se obtiene de la ruta

# Manejador de sesiones en memoria
sessions = {}
session_lock = asyncio.Lock()

def get_module_files(session_id: str, module_name: str) -> List[str]:
    """
    Obtiene la lista de archivos para un módulo específico dentro de una sesión.
    Retorna una lista con las rutas relativas de los archivos.
    """
    module_path = os.path.join(BASE_MODULES_DIR, session_id, module_name)
    file_list = []
    if os.path.isdir(module_path):
        for root, dirs, files in os.walk(module_path):
            for file in files:
                # Obtener la ruta relativa del archivo respecto al módulo
                rel_dir = os.path.relpath(root, module_path)
                rel_file = os.path.join(rel_dir, file) if rel_dir != '.' else file
                file_list.append(rel_file)
    return file_list

@app.post("/start-session/", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest):
    """
    Inicia una nueva sesión y devuelve un session_id único.
    """
    session_id = str(uuid.uuid4())
    
    async with session_lock:
        sessions[session_id] = {
            "modules": {}
        }
    logger.info(f"Sesión iniciada: {session_id}")
    
    return StartSessionResponse(session_id=session_id)

@app.post("/upload-modules/{session_id}/", status_code=200)
async def upload_modules(
    session_id: str,
    request: UploadModulesRequest,
    req: Request  # Inyecta el objeto Request
):
    """
    Sube módulos al servidor asociados a una sesión existente.
    El session_id se proporciona como parte de la ruta.
    """
    # Log de los detalles de la petición
    logger.debug("----- Inicio de la petición -----")
    
    # Método y URL
    logger.info(f"Método: {req.method}")
    logger.info(f"URL: {req.url}")

    # Path Parameters
    logger.info(f"Path Parameter - session_id: {session_id}")

    # Query Parameters
    if req.query_params:
        logger.info(f"Query Parameters: {dict(req.query_params)}")
    else:
        logger.info("No hay Query Parameters.")

    # Headers (filtrando información sensible)
    sensitive_headers = ["authorization", "cookie"]
    filtered_headers = {
        k: ("***" if k.lower() in sensitive_headers else v)
        for k, v in req.headers.items()
    }
    logger.info(f"Headers: {filtered_headers}")

    # Cuerpo de la petición (Body)
    try:
        # Dado que ya tienes el objeto `request` como `UploadModulesRequest`,
        # puedes loggear sus contenidos directamente.
        logger.debug(f"Cuerpo de la petición: {request.json()}")  # Asegúrate de que `UploadModulesRequest` tenga método `json()`
    except Exception as e:
        logger.error(f"Error al loggear el cuerpo de la petición: {e}")

    logger.debug("----- Fin de los detalles de la petición -----")
    
    # Continuar con el procesamiento normal
    logger.debug(f"Inicio de la función upload_modules para sesión {session_id}.")
    
    async with session_lock:
        logger.debug(f"Verificando existencia de la sesión {session_id}.")
        if session_id not in sessions:
            logger.error(f"Sesión no encontrada: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found.")
        logger.debug(f"Sesión {session_id} encontrada.")
    
    session_path = os.path.join(BASE_MODULES_DIR, session_id)
    if not os.path.exists(session_path):
        os.makedirs(session_path)
        logger.debug(f"Creado directorio para sesión: {session_path}")
    else:
        logger.debug(f"Directorio para sesión ya existe: {session_path}")
    
    # Guardar los archivos de los módulos
    for module in request.modules:
        logger.debug(f"Procesando módulo: {module.name}")
        module_path = os.path.join(session_path, module.name)
        if not os.path.exists(module_path):
            os.makedirs(module_path)
            logger.debug(f"Creado directorio para módulo: {module_path}")
        else:
            logger.debug(f"Directorio para módulo ya existe: {module_path}")
        
        for filename, content in module.files.items():
            file_path = os.path.join(module_path, filename)
            try:
                with open(file_path, 'w') as f:
                    f.write(content)
                logger.debug(f"Archivo guardado: {file_path}")
            except Exception as e:
                logger.error(f"Error al guardar el archivo {file_path}: {e}")
                raise HTTPException(status_code=500, detail=f"Error saving file {filename}: {e}")
    
    # Cargar y ejecutar main() una sola vez por módulo
    async with session_lock:
        logger.debug(f"Cargando módulos para sesión {session_id}.")
        modules_loaded = sessions[session_id]["modules"]
        for module in request.modules:
            module_dir = os.path.join(session_path, module.name)
            main_py = os.path.join(module_dir, "main.py")
            if os.path.isfile(main_py):
                try:
                    spec = importlib.util.spec_from_file_location(module.name, main_py)
                    loaded_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(loaded_module)
                    logger.debug(f"Módulo cargado dinámicamente: {main_py}")
                    if hasattr(loaded_module, "main"):
                        logger.debug(f"Ejecutando función main para módulo: {module.name}")
                        module_instance = loaded_module.main(modules_loaded)
                        modules_loaded[module.name] = module_instance
                        logger.info(f"Función main ejecutada para módulo: {module.name}")
                except Exception as e:
                    logger.error(f"Error al cargar o ejecutar el módulo {module.name}: {e}")
                    raise HTTPException(status_code=500, detail=f"Error loading module {module.name}: {e}")
            else:
                logger.warning(f"Archivo main.py no encontrado para módulo: {module.name}")
        
        sessions[session_id]["modules"] = modules_loaded
        logger.info(f"Módulos cargados para sesión {session_id}: {[m.name for m in request.modules]}")
    
    logger.debug(f"Finalizando función upload_modules para sesión {session_id}.")
    return {"status": f"Módulos subidos correctamente a la sesión {session_id}"}

@app.post("/execute/{session_id}/", status_code=200)
async def execute(
    session_id: str,
    request: ExecutionRequest
):
    """
    Ejecuta una función específica dentro de la sesión.
    El session_id se proporciona como parte de la ruta.
    """
    logger.debug(f"Recibiendo solicitud para ejecutar función en la sesión {session_id}.")
    
    async with session_lock:
        if session_id not in sessions:
            logger.error(f"Sesión no encontrada: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found.")
        
        modules_loaded = sessions[session_id]["modules"]
        logger.debug(f"Módulos cargados para sesión {session_id}: {list(modules_loaded.keys())}")

    # Buscar la función en los módulos cargados
    target_module = None
    for module_name, module_instance in modules_loaded.items():
        if hasattr(module_instance, request.function):
            target_module = module_instance
            logger.debug(f"Función '{request.function}' encontrada en módulo '{module_name}'.")
            break

    if not target_module:
        logger.error(f"Función '{request.function}' no encontrada en ningún módulo de la sesión {session_id}.")
        raise HTTPException(
            status_code=400,
            detail=f"Function '{request.function}' not found in any module of session {session_id}"
        )
    
    try:
        func = getattr(target_module, request.function)
        logger.info(f"Ejecutando función '{request.function}' en sesión {session_id} con parámetros: {request.params}")
        result = func(**request.params)
        logger.info(f"Función '{request.function}' ejecutada exitosamente en sesión {session_id}. Resultado: {result}")
        return {"result": result}
    except Exception as e:
        logger.error(f"Error al ejecutar la función '{request.function}' en sesión {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/close-session/{session_id}/", status_code=200)
async def close_session(
    session_id: str,
    request: CloseSessionRequest
):
    """
    Cierra una sesión activa, liberando recursos en el servidor.
    El session_id se proporciona como parte de la ruta.
    """
    logger.debug(f"Recibiendo solicitud para cerrar la sesión {session_id}.")
    
    async with session_lock:
        if session_id not in sessions:
            logger.error(f"Sesión no encontrada: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found.")
        
        # Eliminar la sesión
        del sessions[session_id]
        logger.info(f"Sesión {session_id} eliminada del diccionario de sesiones.")
    
    # Eliminar los archivos de la sesión
    session_path = os.path.join(BASE_MODULES_DIR, session_id)
    if os.path.exists(session_path):
        shutil.rmtree(session_path)
        logger.info(f"Archivos de la sesión {session_id} eliminados.")
    else:
        logger.warning(f"Ruta de sesión {session_id} no encontrada para eliminar archivos.")
    
    return {"status": f"Session {session_id} closed successfully."}

@app.get("/", status_code=200)
async def root():
    """
    Ruta de verificación del estado del servidor.
    Devuelve información detallada sobre las sesiones activas, los módulos cargados y la estructura de archivos.
    """
    logger.debug("Recibiendo solicitud para verificar estado del servidor.")
    
    async with session_lock:
        active_sessions = len(sessions)
        sessions_info = []
        
        for session_id, session_data in sessions.items():
            modules_info = []
            for module_name in session_data["modules"]:
                files = get_module_files(session_id, module_name)
                modules_info.append({
                    "name": module_name,
                    "files": files
                })
            sessions_info.append({
                "session_id": session_id,
                "modules": modules_info
            })
    
    logger.info(f"Estado del servidor solicitado. Sesiones activas: {active_sessions}")
    return {
        "status": "Servidor en funcionamiento",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "active_sessions": active_sessions,
        "sessions": sessions_info  # Información detallada de las sesiones
    }
