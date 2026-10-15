from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Abstract storage interface for persisting raw uploaded contract documents.

    Decouples document ingestion logic from local filesystem, allowing seamless
    future migration to AWS S3, Google Cloud Storage, or Azure Blob Storage.
    """

    @abstractmethod
    async def save_file(self, file_id: str, content: bytes, extension: str) -> str:
        """Persist raw file content and return storage locator/path."""
        pass

    @abstractmethod
    async def read_file(self, storage_path: str) -> bytes:
        """Retrieve raw file content by storage locator."""
        pass

    @abstractmethod
    async def delete_file(self, storage_path: str) -> None:
        """Remove file from storage."""
        pass

    @abstractmethod
    async def file_exists(self, storage_path: str) -> bool:
        """Check whether file exists in storage."""
        pass
