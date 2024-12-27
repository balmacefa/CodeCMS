# storage_inmemory.py
from typing import Optional, List, Any
from storage_base import ScriptStorage

class InMemoryScriptStorage(ScriptStorage):
    """
    Implementación en memoria.
    Almacena un diccionario con la forma:
      data[script_hash] = {
        "content": str,
        "module": Any
      }
    """

    def __init__(self):
        self.data = {}

    def store_script(self, script_hash: str, content: str) -> None:
        self.data[script_hash] = {
            "content": content,
            "module": None
        }

    def get_script_content(self, script_hash: str) -> Optional[str]:
        entry = self.data.get(script_hash)
        if entry is None:
            return None
        return entry["content"]

    def get_script_module(self, script_hash: str) -> Optional[Any]:
        entry = self.data.get(script_hash)
        if entry is None:
            return None
        return entry["module"]

    def set_script_module(self, script_hash: str, module: Any) -> None:
        if script_hash in self.data:
            self.data[script_hash]["module"] = module

    def list_scripts(self) -> List[str]:
        return list(self.data.keys())

    def script_exists(self, script_hash: str) -> bool:
        return script_hash in self.data

    def delete_script(self, script_hash: str) -> None:
        if script_hash in self.data:
            del self.data[script_hash]
