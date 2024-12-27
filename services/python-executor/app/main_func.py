import hashlib
import importlib.util
import tempfile
import os
import asyncio
import logging
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, List
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from typing import Dict, Any, Optional
# ==========================
# Configuración de Logging
# ==========================
logger = logging.getLogger("script_manager")
logger.setLevel(logging.INFO)  # Nivel de log que deseas (DEBUG, INFO, WARNING...)

# Handler para imprimir en consola; podrías usar FileHandler o RotatingFileHandler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
))
logger.addHandler(console_handler)


# logs= []

# Función auxiliar para logs asíncronos
async def log_message(message: str):
    """
    Envía un mensaje al logger en un hilo aparte para no bloquear el event loop.
    """
    # logs.append(message)
    await asyncio.to_thread(logger.info, message)

# ==========================
#   Inicialización FastAPI
# ==========================
app = FastAPI()

# Almacenamiento en memoria
scripts_map: Dict[str, Dict[str, Any]] = {}


# ========== Modelos Pydantic para Request/Response ==========

class UploadScriptRequest(BaseModel):
    """Modelo para subir un nuevo script."""
    script: str


class UploadScriptResponse(BaseModel):
    """Devuelve el hash MD5 (id) del script subido."""
    id: str

class ExecuteScriptRequest(BaseModel):
    """Modelo para llamar a una función de un script ya almacenado."""
    id: str
    function_name: str
    params: Optional[Dict[str, Any]] = None


class ExecuteScriptResponse(BaseModel):
    """Respuesta al ejecutar la función."""
    result: Any


class UpdateScriptRequest(BaseModel):
    """Modelo para actualizar (modificar) el contenido de un script."""
    new_script: str


# ========== Endpoints ==========
@app.get("/logs/",)
async def get_logs():
    return '[]'

@app.post("/upload-script/", response_model=UploadScriptResponse)
async def upload_script(request: UploadScriptRequest):
    """
    Sube un script (string Python). Calcula un hash MD5,
    lo almacena en memoria si no existe ya. Retorna el 'id' (hash).
    """
    script_content = request.script
    script_hash = hashlib.md5(script_content.encode("utf-8")).hexdigest()

    if script_hash not in scripts_map:
        scripts_map[script_hash] = {
            "content": script_content,
            "module": None
        }
        await log_message(f"[UPLOAD] Nuevo script con hash: {script_hash}")
    else:
        await log_message(f"[UPLOAD] Script repetido, hash: {script_hash} (ya existe)")

    return UploadScriptResponse(id=script_hash)


@app.get("/scripts/", response_model=List[str])
async def list_scripts():
    """
    Devuelve la lista de IDs (hashes) de los scripts almacenados.
    """
    await log_message("[LIST] Listado de scripts solicitado")
    return list(scripts_map.keys())


@app.post("/call-script/", response_model=ExecuteScriptResponse)
async def call_script(request: ExecuteScriptRequest):
    """
    Llama la función 'function_name' en el script con id='id', pasando 'params'.
    """
    script_id = request.id
    fn_name = request.function_name
    params = request.params

    # Verificamos que el script exista
    if script_id not in scripts_map:
        await log_message(f"[CALL] Script no encontrado: {script_id}")
        raise HTTPException(status_code=404, detail="Script no encontrado.")

    script_info = scripts_map[script_id]
    content = script_info["content"]
    module = script_info["module"]

    # Si el módulo no está cargado, lo cargamos
    if module is None:
        module = load_script_module(script_id, content)
        script_info["module"] = module
        await log_message(f"[CALL] Módulo cargado dinámicamente para script: {script_id}")

    # Verificamos que la función exista
    if not hasattr(module, fn_name):
        await log_message(f"[CALL] Función '{fn_name}' inexistente en script: {script_id}")
        raise HTTPException(
            status_code=400,
            detail=f"No existe la función '{fn_name}' en el script."
        )

    fn = getattr(module, fn_name)
    try:
        result = fn(**params)
        await log_message(f"[CALL] Ejecución OK en script: {script_id}, función: {fn_name}")
    except TypeError as e:
        await log_message(f"[CALL] TypeError en script: {script_id}, función: {fn_name}, error: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Error en los parámetros: {e}"
        )
    except Exception as e:
        await log_message(f"[CALL] Error en ejecución de script: {script_id}, función: {fn_name}, error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error en la ejecución de la función: {e}"
        )

    return ExecuteScriptResponse(result=result)


@app.post("/update-script/{script_id}")
async def update_script(script_id: str, request: UpdateScriptRequest):
    """
    Actualiza (modifica) el contenido de un script ya existente.
    Sobrescribe completamente el contenido con 'new_script'.
    Resetea 'module' a None para forzar recarga en la próxima ejecución.
    Retorna el nuevo contenido.
    """
    if script_id not in scripts_map:
        await log_message(f"[UPDATE] Script no encontrado: {script_id}")
        raise HTTPException(status_code=404, detail="Script no encontrado.")

    new_content = request.new_script
    scripts_map[script_id]["content"] = new_content
    scripts_map[script_id]["module"] = None
    await log_message(f"[UPDATE] Script actualizado: {script_id}")

    return {
        "id": script_id,
        "new_content": new_content
    }


@app.post("/delete-script/{script_id}")
async def delete_script(script_id: str):
    """
    Elimina completamente el script (y el módulo) del almacenamiento en memoria.
    """
    if script_id not in scripts_map:
        await log_message(f"[DELETE] Script no encontrado: {script_id}")
        raise HTTPException(status_code=404, detail="Script no encontrado.")

    del scripts_map[script_id]
    await log_message(f"[DELETE] Script eliminado: {script_id}")
    return {"status": f"Script {script_id} eliminado exitosamente."}


# ========== Función Auxiliar para cargar el módulo ==========
def load_script_module(script_id: str, script_content: str):
    """
    Carga dinámicamente 'script_content' en un módulo Python usando importlib.
    Retorna el módulo importado.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        script_path = os.path.join(tmp_dir, f"{script_id}.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        spec = importlib.util.spec_from_file_location(script_id, script_path)
        if spec is None:
            raise RuntimeError("No se pudo crear el spec de importación.")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

    return module


# ========== Template para dashboard (opcional) ==========
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    await log_message("[DASHBOARD] Renderizando página principal")
    return templates.TemplateResponse("dashboard.html", {"request": request})
