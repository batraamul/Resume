"""Structured error types. Every error carries a user-facing message."""

from __future__ import annotations


class RISError(Exception):
    """Base error. ``user_message`` is safe to show in the UI (no secrets, no record contents)."""

    def __init__(self, user_message: str, *, detail: str = "") -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.detail = detail


class ValidationFailed(RISError):
    def __init__(self, user_message: str, *, errors: list[str] | None = None, detail: str = "") -> None:
        super().__init__(user_message, detail=detail)
        self.errors = errors or []


class NotFound(RISError):
    pass


class ConcurrencyConflict(RISError):
    """The record changed since it was loaded (optimistic concurrency)."""


class StorageError(RISError):
    pass


class MigrationError(StorageError):
    pass


class IntegrityFailure(StorageError):
    pass


class BackupError(RISError):
    pass


class RestoreError(BackupError):
    pass


class DecryptionError(BackupError):
    pass


class ImportFailed(RISError):
    pass


class ExportError(RISError):
    pass


class ConversionError(ExportError):
    pass


class ReviewRequired(ExportError):
    """Export blocked until the pre-export review items are resolved."""

    def __init__(self, user_message: str, *, items: list | None = None) -> None:
        super().__init__(user_message)
        self.items = items or []


class TemplateError(RISError):
    pass


class SyncError(RISError):
    pass


class AuthExpired(SyncError):
    pass


class NetworkUnavailable(SyncError):
    pass


class RemoteChanged(SyncError):
    """The remote changed between read and write; retry the sync."""


class SecretStoreUnavailable(RISError):
    pass


class AIProviderError(RISError):
    pass
