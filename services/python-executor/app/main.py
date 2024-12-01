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
import json
import inspect

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
logger.debug("Aplicación FastAPI inicializada.")

# Directorio base para almacenar los módulos de cada sesión
BASE_MODULES_DIR = "./modules"

# Crear el directorio base si no existe
if not os.path.exists(BASE_MODULES_DIR):
    os.makedirs(BASE_MODULES_DIR)
    logger.debug(f"Creado directorio base para módulos: {BASE_MODULES_DIR}")
else:
    logger.debug(f"Directorio base para módulos ya existe: {BASE_MODULES_DIR}")

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


def generate_dts_string(module_name: str, cls: type) -> str:
    """
    Genera un string representando un archivo `.d.ts` basado en una clase y sus métodos.
    """
    def python_to_ts_type(py_type: Any) -> str:
        """Convierte un tipo de Python a TypeScript."""
        if py_type in [str, "str"]:
            return "string"
        elif py_type in [int, "int"]:
            return "number"
        elif py_type in [float, "float"]:
            return "number"
        elif py_type in [bool, "bool"]:
            return "boolean"
        elif py_type in [list, "list", List]:
            return "any[]"  # Mejorado si hay subtipos
        elif py_type in [dict, "dict", Dict]:
            return "{ [key: string]: any }"  # Mejorado si hay subtipos
        elif py_type in [Any, "Any", "unknown"]:
            return "unknown"
        else:
            return "any"  # Por defecto

    dts_lines = [f"declare module \"{module_name}\" {{"]

    class_name = cls.__name__
    class_doc = inspect.getdoc(cls) or ""
    dts_lines.append(f"  /**")
    dts_lines.append(f"   * {class_doc}")
    dts_lines.append(f"   */")
    dts_lines.append(f"  class {class_name} {{")
    
    # Obtener métodos de la clase
    for method_name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
        method_doc = inspect.getdoc(method) or ""
        signature = inspect.signature(method)

        # Crear un único parámetro llamado "args"
        args_structure = []
        for param_name, param in signature.parameters.items():
            if param_name == "self":  # Ignorar `self`
                continue
            ts_type = python_to_ts_type(param.annotation)
            args_structure.append(f"{param_name}: {ts_type}")

        # Convertir estructura de args en TypeScript
        args_str = f"args: {{ {', '.join(args_structure)} }}"
        return_type = python_to_ts_type(signature.return_annotation)

        dts_lines.append(f"    /**")
        dts_lines.append(f"     * {method_doc}")
        dts_lines.append(f"     */")
        dts_lines.append(f"    {method_name}({args_str}): {return_type};")
    
    # Cerrar definición de la clase
    dts_lines.append("  }")
    dts_lines.append("}")

    return "\n".join(dts_lines)



def get_module_files(session_id: str, module_name: str) -> List[str]:
    """
    Obtiene la lista de archivos para un módulo específico dentro de una sesión.
    Retorna una lista con las rutas relativas de los archivos.
    """
    module_path = os.path.join(BASE_MODULES_DIR, session_id, module_name)
    file_list = []
    logger.debug(f"Buscando archivos en: {module_path}")
    if os.path.isdir(module_path):
        for root, dirs, files in os.walk(module_path):
            for file in files:
                # Obtener la ruta relativa del archivo respecto al módulo
                rel_dir = os.path.relpath(root, module_path)
                rel_file = os.path.join(rel_dir, file) if rel_dir != '.' else file
                file_list.append(rel_file)
                logger.debug(f"Archivo encontrado: {rel_file}")
    else:
        logger.warning(f"El directorio del módulo no existe: {module_path}")
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

import inspect

@app.post("/upload-modules/{session_id}/", status_code=200)
async def upload_modules(
    session_id: str,
    request: UploadModulesRequest,
    req: Request
):
    """
    Sube módulos al servidor asociados a una sesión existente.
    Genera un archivo `.d.ts` basado en las clases y métodos encontrados.
    """
    logger.debug(f"Inicio de la función upload_modules para sesión {session_id}.")
    
    async with session_lock:
        if session_id not in sessions:
            logger.error(f"Sesión no encontrada: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found.")
        logger.debug(f"Sesión {session_id} encontrada.")
    
    session_path = os.path.join(BASE_MODULES_DIR, session_id)
    if not os.path.exists(session_path):
        os.makedirs(session_path)
        logger.debug(f"Creado directorio para sesión: {session_path}")
    
    dts_content = []

    for module in request.modules:
        module_path = os.path.join(session_path, module.name)
        if not os.path.exists(module_path):
            os.makedirs(module_path)
            logger.debug(f"Creado directorio para módulo: {module_path}")
        
        for filename, content in module.files.items():
            file_path = os.path.join(module_path, filename)
            try:
                with open(file_path, 'w') as f:
                    f.write(content)
                logger.debug(f"Archivo guardado: {file_path}")
            except Exception as e:
                logger.error(f"Error al guardar el archivo {file_path}: {e}")
                raise HTTPException(status_code=500, detail=f"Error saving file {filename}: {e}")
    
    async with session_lock:
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
                    
                    # Buscar clases en el módulo y generar `.d.ts`
                    for attr_name in dir(loaded_module):
                        attr = getattr(loaded_module, attr_name)
                        if isinstance(attr, type):  # Es una clase
                            dts_content.append(generate_dts_string(module.name, attr))

                except Exception as e:
                    logger.error(f"Error al cargar o ejecutar el módulo {module.name}: {e}")
                    raise HTTPException(status_code=500, detail=f"Error loading module {module.name}: {e}")
            else:
                logger.warning(f"Archivo main.py no encontrado para módulo: {module.name}")
        
    sessions[session_id]["modules"] = modules_loaded
    logger.info(f"Módulos cargados para sesión {session_id}: {[m.name for m in request.modules]}")

    # Unir el contenido del archivo `.d.ts`
    dts_final_content = "\n\n".join(dts_content)

    logger.debug(f"Finalizando función upload_modules para sesión {session_id}.")
    return {"status": f"Módulos subidos correctamente a la sesión {session_id}", "dts_content": dts_final_content}

@app.post("/execute/{session_id}/", status_code=200)
async def execute(
    session_id: str,
    request: ExecutionRequest
):
    """
    Ejecuta una función específica dentro de la sesión.
    El session_id se proporciona como parte de la ruta.
    """
    try:
        logger.debug(f"Recibiendo solicitud para ejecutar función en la sesión {session_id}.")
        
        async with session_lock:
            if session_id not in sessions:
                logger.error(f"Sesión no encontrada: {session_id}")
                return {"error": "Session not found."}
            
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
            return {
                "error": f"Function '{request.function}' not found in any module of session {session_id}"
            }
        
        try:
            func = getattr(target_module, request.function)
            logger.info(f"Ejecutando función '{request.function}' en sesión {session_id} con parámetros: {request.params}")
            
            # Determinar si la función es asíncrona
            if inspect.iscoroutinefunction(func):
                logger.debug(f"La función '{request.function}' es asíncrona. Ejecutando con 'await'.")
                result = await func(**request.params)
            else:
                logger.debug(f"La función '{request.function}' es síncrona. Ejecutando directamente.")
                result = func(**request.params)
            
            logger.info(f"Función '{request.function}' ejecutada exitosamente en sesión {session_id}. Resultado: {result}")
            return {"result": result}
        except Exception as func_exception:
            logger.error(f"Error al ejecutar la función '{request.function}' en sesión {session_id}: {func_exception}")
            return {"error": f"Error executing function '{request.function}': {str(func_exception)}"}
    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        return {"error": f"Unexpected error occurred: {str(e)}"}




@app.post("/close-session/{session_id}/", status_code=200)
async def close_session(
    session_id: str,
    request: CloseSessionRequest,
    req: Request  # Objeto Request para obtener información adicional
):
    """
    Cierra una sesión activa, ejecutando `onDestroy` en módulos si existe, y liberando recursos en el servidor.
    """
    logger.info(f"Solicitud recibida para cerrar la sesión {session_id}.")
    
    # Log de encabezados
    headers = dict(req.headers)
    logger.debug(f"Encabezados de la solicitud: {json.dumps(headers, indent=2)}")
    
    # Log de parámetros
    logger.debug(f"Parámetros de la solicitud: {request.dict()}")
    
    async with session_lock:
        if session_id not in sessions:
            logger.error(f"Sesión no encontrada: {session_id}")
            raise HTTPException(status_code=404, detail="Session not found.")
        
        logger.info(f"Sesión encontrada: {session_id}. Preparándose para ejecutar 'onDestroy' en los módulos.")

        # Ejecutar `onDestroy` en cada módulo de la sesión si existe
        modules_loaded = sessions[session_id]["modules"]
        for module_name, module_instance in modules_loaded.items():
            logger.debug(f"Procesando módulo: {module_name}")
            
            if hasattr(module_instance, "onDestroy"):
                on_destroy = getattr(module_instance, "onDestroy")
                try:
                    if inspect.iscoroutinefunction(on_destroy):
                        logger.info(f"Ejecutando evento asíncrono 'onDestroy' para módulo: {module_name}")
                        await on_destroy()
                    else:
                        logger.info(f"Ejecutando evento síncrono 'onDestroy' para módulo: {module_name}")
                        on_destroy()
                    logger.info(f"Evento 'onDestroy' ejecutado correctamente para módulo: {module_name}")
                except Exception as e:
                    logger.error(f"Error al ejecutar 'onDestroy' en módulo {module_name}: {e}")
            else:
                logger.debug(f"Módulo {module_name} no tiene un método 'onDestroy'.")
        
        logger.info(f"Todos los módulos procesados para sesión {session_id}. Procediendo a limpiar recursos.")

        # Eliminar la sesión del diccionario
        del sessions[session_id]
        logger.info(f"Sesión {session_id} eliminada del diccionario de sesiones.")
    
    # Eliminar los archivos de la sesión
    session_path = os.path.join(BASE_MODULES_DIR, session_id)
    if os.path.exists(session_path):
        try:
            shutil.rmtree(session_path)
            logger.info(f"Archivos de la sesión {session_id} eliminados del sistema de archivos.")
        except Exception as e:
            logger.error(f"Error al eliminar archivos de la sesión {session_id}: {e}")
    else:
        logger.warning(f"Ruta de sesión {session_id} no encontrada para eliminar archivos.")
    
    logger.info(f"Sesión {session_id} cerrada exitosamente.")
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
    logger.debug(f"Información de sesiones: {sessions_info}")
    return {
        "status": "Servidor en funcionamiento",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "active_sessions": active_sessions,
        "sessions": sessions_info  # Información detallada de las sesiones
    }

@app.get("/debug-sessions/", status_code=200)
async def debug_sessions():
    """
    Endpoint temporal para inspeccionar la estructura de 'sessions'.
    """
    logger.debug("Recibiendo solicitud para debug de sesiones.")
    async with session_lock:
        return sessions
