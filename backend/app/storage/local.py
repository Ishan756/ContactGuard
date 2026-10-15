import asyncio
import re
from pathlib import Path

from app.core.errors import AppException
from app.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    """Secure local disk storage backend.

    Stores files in a private directory outside any public or web-accessible root.
    Strictly prevents path traversal attacks.
    """

    def __init__(self, base_dir: str | Path = "data/uploads") -> None:
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_extension(self, extension: str) -> str:
        clean_ext = extension.lstrip(".").lower()
        if not re.match(r"^[a-zA-Z0-9]+$", clean_ext):
            raise AppException(
                "Invalid file extension format", code="INVALID_EXTENSION", status_code=400
            )
        return clean_ext

    def _resolve_safe_path(self, file_id: str, extension: str) -> Path:
        clean_ext = self._sanitize_extension(extension)
        filename = f"{file_id}.{clean_ext}"
        candidate_path = (self.base_dir / filename).resolve()

        # Path traversal guard: candidate must be strictly within base_dir
        if not candidate_path.is_relative_to(self.base_dir):
            raise AppException(
                "Path traversal attempt detected", code="SECURITY_ERROR", status_code=400
            )

        return candidate_path

    async def save_file(self, file_id: str, content: bytes, extension: str) -> str:
        target_path = self._resolve_safe_path(file_id, extension)

        def _write():
            target_path.write_bytes(content)

        await asyncio.to_thread(_write)
        return str(target_path)

    async def read_file(self, storage_path: str) -> bytes:
        resolved = Path(storage_path).resolve()
        if not resolved.is_relative_to(self.base_dir) or not resolved.is_file():
            raise AppException("File not found in storage", code="NOT_FOUND", status_code=404)

        return await asyncio.to_thread(resolved.read_bytes)

    async def delete_file(self, storage_path: str) -> None:
        resolved = Path(storage_path).resolve()
        if resolved.is_relative_to(self.base_dir) and resolved.is_file():
            await asyncio.to_thread(resolved.unlink, missing_ok=True)

    async def file_exists(self, storage_path: str) -> bool:
        resolved = Path(storage_path).resolve()
        if not resolved.is_relative_to(self.base_dir):
            return False
        return await asyncio.to_thread(resolved.is_file)
