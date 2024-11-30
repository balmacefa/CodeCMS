from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import uuid  # Importar el módulo uuid para generar IDs únicos
import importlib.util
import os
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime, timedelta
import shutil

app = FastAPI()

BASE_MODULES_DIR = "./modules"

if not os.path.exists(BASE_MODULES_DIR):
    os.makedirs(BASE_MODULES_DIR)

# Modelos de datos
class StartSessionRequest(BaseModel):
    ttl: int  # Time To Live en segundos

class StartSessionResponse(BaseModel):
    session_id: str
    expires_at: datetime

# ... (otros modelos existentes)

# Manejador de sesiones en memoria
sessions = {}
session_lock = asyncio.Lock()

async def session_timeout_handler(session_id: str, expiration_time: datetime):
    # Esperar hasta que expire el TTL
    await asyncio.sleep((expiration_time - datetime.utcnow()).total_seconds())
    async with session_lock:
        if session_id in sessions:
            # Eliminar la sesión
            del sessions[session_id]
            # Eliminar los archivos de la sesión
            session_path = os.path.join(BASE_MODULES_DIR, session_id)
            if os.path.exists(session_path):
                shutil.rmtree(session_path)
            print(f"Sesión {session_id} cerrada automáticamente por TTL.")

@app.post("/start-session/", response_model=StartSessionResponse)
async def start_session(request: StartSessionRequest):
    session_id = str(uuid.uuid4())
    expiration_time = datetime.utcnow() + timedelta(seconds=request.ttl)
    
    async with session_lock:
        sessions[session_id] = {
            "modules": {},
            "expires_at": expiration_time
        }
    
    # Iniciar el manejador de timeout para cerrar la sesión automáticamente
    asyncio.create_task(session_timeout_handler(session_id, expiration_time))
    
    return StartSessionResponse(session_id=session_id, expires_at=expiration_time)

# Modificar el endpoint /upload-modules/ para que ya no reciba session_id
class ModuleUpload(BaseModel):
    name: str
    files: Dict[str, str]  # filename: content

class UploadModulesRequest(BaseModel):
    modules: List[ModuleUpload]
    ttl: Optional[int] = None  # Time To Live en segundos (opcional)

@app.post("/upload-modules/")
async def upload_modules(request: UploadModulesRequest, authorization: Optional[str] = Header(None)):
    # Verificar si el cliente ya tiene una sesión iniciada
    # Esto puede variar dependiendo de cómo manejes la autenticación y las sesiones
    # Para este ejemplo, asumiremos que el cliente proporciona un token que identifica la sesión
    # Si no, podrías requerir que primero inicie una sesión usando /start-session/
    raise HTTPException(status_code=400, detail="Endpoint deprecated. Use /start-session/ followed by /upload-modules-with-session/.")

# Crear un nuevo endpoint que reciba el session_id generado por el servidor
class UploadModulesWithSessionRequest(BaseModel):
    modules: List[ModuleUpload]
    ttl: Optional[int] = None  # Time To Live en segundos

@app.post("/upload-modules-with-session/")
async def upload_modules_with_session(request: UploadModulesWithSessionRequest, authorization: Optional[str] = Header(None)):
    # Obtener el session_id de algún mecanismo de autenticación o pasar como parámetro
    # Por simplicidad, asumiremos que el session_id se pasa en los headers
    session_id = authorization  # Por ejemplo, usando el header Authorization: Bearer <session_id>
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id in Authorization header")
    
    async with session_lock:
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Actualizar el TTL si se proporciona
        if request.ttl:
            sessions[session_id]["expires_at"] = datetime.utcnow() + timedelta(seconds=request.ttl)
            asyncio.create_task(session_timeout_handler(session_id, sessions[session_id]["expires_at"]))
    
    session_path = os.path.join(BASE_MODULES_DIR, session_id)
    if not os.path.exists(session_path):
        os.makedirs(session_path)
    
    for module in request.modules:
        module_path = os.path.join(session_path, module.name)
        if not os.path.exists(module_path):
            os.makedirs(module_path)
        for filename, content in module.files.items():
            with open(os.path.join(module_path, filename), 'w') as f:
                f.write(content)
    
    # Cargar y ejecutar main() una sola vez por módulo
    async with session_lock:
        modules_loaded = sessions[session_id]["modules"]
        for module in request.modules:
            module_dir = os.path.join(session_path, module.name)
            main_py = os.path.join(module_dir, "main.py")
            if os.path.isfile(main_py):
                spec = importlib.util.spec_from_file_location(module.name, main_py)
                loaded_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(loaded_module)
                if hasattr(loaded_module, "main"):
                    module_instance = loaded_module.main(modules_loaded)
                    modules_loaded[module.name] = module_instance
        
        sessions[session_id]["modules"] = modules_loaded
    
    return {"status": f"Módulos subidos correctamente a la sesión {session_id}"}

# ... (resto de los endpoints existentes)
