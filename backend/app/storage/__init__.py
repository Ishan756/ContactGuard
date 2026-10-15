"""Storage abstraction layer."""

from app.storage.base import StorageBackend
from app.storage.factory import get_storage_backend

__all__ = ["StorageBackend", "get_storage_backend"]
