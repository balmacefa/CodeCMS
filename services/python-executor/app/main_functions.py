# server.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import hashlib
import importlib.util
import tempfile
import os

# 1) Importamos la interfaz y la implementación
from storage_base import ScriptStorage
from storage_inmemory import InMemoryScriptStorage
# from storage_db import DatabaseScriptStorage  # <- Si quisieras usar la DB

app = FastAPI()

# Escogemos la implementación en memoria (o la de DB)
storage: ScriptStorage = InMemoryScriptStorage()
# storage: ScriptStorage = DatabaseScriptStorage(db_path="scripts.db")

class UploadScriptRequest(BaseModel):
    script: str

class UploadScriptResponse(BaseModel):
    id: str

class ExecuteScriptRequest(BaseModel):
    id: str
    function_name: str
    params: Dict[str, Any]

class ExecuteScriptResponse(BaseModel):
    result: Any

@app.post("/upload-script/", response_model=UploadScriptResponse)
def upload_script(request: UploadScriptRequest):
    script_content = request.script
    script_hash = hashlib.md5(script_content.encode("utf-8")).hexdigest()

    # Si no existe, lo guardamos
    if not storage.script_exists(script_hash):
        storage.store_script(script_hash, script_content)

    return UploadScriptResponse(id=script_hash)

@app.get("/scripts/", response_model=List[str])
def list_scripts():
    return storage.list_scripts()

@app.post("/call-script/", response_model=ExecuteScriptResponse)
def call_script(request: ExecuteScriptRequest):
    script_id = request.id
    fn_name = request.function_name
    params = request.params

    if not storage.script_exists(script_id):
        raise HTTPException(status_code=404, detail="Script no encontrado.")

    # Obtener el contenido y el módulo
    content = storage.get_script_content(script_id)
    if content is None:
        raise HTTPException(status_code=500, detail="No se encontró contenido del script.")

    module = storage.get_script_module(script_id)
    # Si el módulo es None, cargarlo
    if module is None:
        module = load_script_module(script_id, content)
        # Almacenar el módulo en la implementación
        storage.set_script_module(script_id, module)

    # Verificar la función
    if not hasattr(module, fn_name):
        raise HTTPException(
            status_code=400,
            detail=f"No existe la función '{fn_name}' en el script."
        )

    fn = getattr(module, fn_name)
    try:
        result = fn(**params)
    except TypeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error en parámetros: {e}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error en ejecución de la función: {e}"
        )

    return ExecuteScriptResponse(result=result)

def load_script_module(script_id: str, script_content: str):
    """
    Carga el script en un módulo Python de manera dinámica usando importlib.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        script_path = os.path.join(tmp_dir, f"{script_id}.py")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        spec = importlib.util.spec_from_file_location(script_id, script_path)
        if spec is None:
            raise RuntimeError("No se pudo crear spec de importación.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module