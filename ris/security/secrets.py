"""Secret storage in the operating system's credential store (AI-05, SYN-02).

Uses ``keyring`` (macOS Keychain, Windows Credential Manager, Secret Service on
Linux). When no secure backend is available, secrets are kept in memory for
the current session only — never written to the database, config or logs.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

SERVICE = "ResumeIntelligenceStudio"
KNOWN_SECRETS = ("ai_api_key", "gdrive_token", "cloud_passphrase")


class SecretStore:
    def __init__(self, use_keyring: bool = True) -> None:
        self._memory: dict[str, str] = {}
        self._keyring = None
        if use_keyring and not os.environ.get("RIS_DISABLE_KEYRING"):
            try:
                import keyring
                from keyring.backends import fail

                backend = keyring.get_keyring()
                priority = getattr(backend, "priority", 0)
                if not isinstance(backend, fail.Keyring) and (priority is None or priority > 0):
                    self._keyring = keyring
            except Exception:  # noqa: BLE001 - any keyring problem means "not available"
                self._keyring = None

    @property
    def persistent(self) -> bool:
        return self._keyring is not None

    def describe(self) -> str:
        if self._keyring is None:
            return "Session only (no secure credential store available; secrets are forgotten when you quit)."
        try:
            name = type(self._keyring.get_keyring()).__name__
        except Exception:  # noqa: BLE001
            name = "system keyring"
        return f"Operating-system credential store ({name})."

    def get(self, name: str) -> str | None:
        if self._keyring is not None:
            try:
                val = self._keyring.get_password(SERVICE, name)
                if val is not None:
                    return val
            except Exception:  # noqa: BLE001
                log.warning("Credential store read failed for a secret")
        return self._memory.get(name)

    def set(self, name: str, value: str) -> bool:
        """Store a secret. Returns True when stored persistently."""
        if not value:
            self.delete(name)
            return self.persistent
        if self._keyring is not None:
            try:
                self._keyring.set_password(SERVICE, name, value)
                self._memory.pop(name, None)
                return True
            except Exception:  # noqa: BLE001
                log.warning("Credential store write failed; keeping the secret for this session only")
        self._memory[name] = value
        return False

    def delete(self, name: str) -> None:
        self._memory.pop(name, None)
        if self._keyring is not None:
            try:
                self._keyring.delete_password(SERVICE, name)
            except Exception:  # noqa: BLE001 - missing entries are fine
                pass

    def has(self, name: str) -> bool:
        return bool(self.get(name))
