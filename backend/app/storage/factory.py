from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import StorageBackend
from app.storage.local import LocalStorageBackend


@lru_cache
def get_storage_backend() -> StorageBackend:
    """Factory creating configured storage backend."""
    settings = get_settings()
    if settings.storage_backend.lower() == "local":
        return LocalStorageBackend(base_dir=settings.upload_dir)
    elif settings.storage_backend.lower() == "s3":
        # S3 adapter placeholder for future cloud configuration
        raise NotImplementedError(
            "S3 storage backend will be enabled with AWS credentials configuration."
        )
    return LocalStorageBackend(base_dir=settings.upload_dir)
