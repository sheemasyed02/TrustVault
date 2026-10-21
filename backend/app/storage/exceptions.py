"""Safe storage exceptions that avoid leaking credentials or SDK internals."""


class StorageError(Exception):
    """Base storage error with a user-safe message."""

    def __init__(self, message: str = "Storage operation failed") -> None:
        super().__init__(message)
        self.message = message


class StorageConfigurationError(StorageError):
    """Raised when required R2 configuration is missing or invalid."""


class StorageNotFoundError(StorageError):
    """Raised when an object key does not exist in the private bucket."""

    def __init__(self, message: str = "Object not found") -> None:
        super().__init__(message)


class StorageIntegrityError(StorageError):
    """Raised when an expected SHA-256 does not match uploaded bytes."""

    def __init__(self, message: str = "Object checksum mismatch") -> None:
        super().__init__(message)


class StorageOperationError(StorageError):
    """Raised for R2/network failures that are not missing objects."""
