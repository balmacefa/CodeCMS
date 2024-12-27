# storage_base.py
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any

class ScriptStorage(ABC):
    """
    Define la interfaz para almacenar y gestionar scripts.
    """

    @abstractmethod
    def store_script(self, script_hash: str, content: str) -> None:
        """
        Crea o actualiza el contenido de un script en almacenamiento.
        """
        pass

    @abstractmethod
    def get_script_content(self, script_hash: str) -> Optional[str]:
        """
        Retorna el contenido del script si existe, o None si no existe.
        """
        pass

    @abstractmethod
    def get_script_module(self, script_hash: str) -> Optional[Any]:
        """
        Retorna el módulo Python asociado al script (si está cacheado).
        """
        pass

    @abstractmethod
    def set_script_module(self, script_hash: str, module: Any) -> None:
        """
        Asigna o actualiza el módulo Python del script, en caso de que se use cache.
        """
        pass

    @abstractmethod
    def list_scripts(self) -> List[str]:
        """
        Devuelve la lista de IDs (hashes) de los scripts almacenados.
        """
        pass

    @abstractmethod
    def script_exists(self, script_hash: str) -> bool:
        """
        Retorna True si el script existe, False en caso contrario.
        """
        pass

    @abstractmethod
    def delete_script(self, script_hash: str) -> None:
        """
        Elimina el script del almacenamiento si existe.
        """
        pass
