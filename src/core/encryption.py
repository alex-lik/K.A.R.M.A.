"""Utilities for encrypting configuration secrets."""

import logging
import os
from typing import Optional, Union

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class EncryptionManager:
    """Encrypts and decrypts short strings and files using Fernet."""

    def __init__(self, key_path: Optional[str] = None) -> None:
        self.key_path = key_path or self._default_key_path()
        self._fernet = self._load_fernet()

    @staticmethod
    def _default_key_path() -> str:
        app_dir = os.path.join(os.path.expanduser("~"), ".filesync")
        os.makedirs(app_dir, exist_ok=True)
        return os.path.join(app_dir, "encryption.key")

    def _load_fernet(self) -> Fernet:
        key: Optional[bytes] = None

        if os.path.exists(self.key_path):
            try:
                with open(self.key_path, "rb") as key_file:
                    key = key_file.read().strip()
            except OSError as exc:
                logger.error("Failed to read encryption key: %s", exc)

        if not key:
            key = Fernet.generate_key()
            try:
                os.makedirs(os.path.dirname(self.key_path), exist_ok=True)
                with open(self.key_path, "wb") as key_file:
                    key_file.write(key)
            except OSError as exc:
                logger.error("Failed to persist encryption key: %s", exc)
                raise

        try:
            return Fernet(key)
        except (ValueError, TypeError) as exc:
            logger.error("Invalid encryption key data: %s", exc)
            raise

    @staticmethod
    def _to_bytes(data: Union[str, bytes]) -> bytes:
        if isinstance(data, bytes):
            return data
        return str(data).encode("utf-8")

    def encrypt(self, data: Union[str, bytes, None]) -> str:
        if data in (None, ""):
            return ""
        token = self._fernet.encrypt(self._to_bytes(data))
        return token.decode("utf-8")

    def decrypt(self, token: Union[str, bytes, None]) -> str:
        if token in (None, ""):
            return ""
        try:
            decrypted = self._fernet.decrypt(self._to_bytes(token))
        except InvalidToken:
            logger.warning("Attempted to decrypt with an invalid token.")
            return ""
        except (TypeError, ValueError) as exc:
            logger.error("Failed to decrypt token: %s", exc)
            return ""
        return decrypted.decode("utf-8")

    def encrypt_file(self, source_path: str, destination_path: str) -> None:
        with open(source_path, "rb") as source_file:
            payload = source_file.read()

        encrypted = self._fernet.encrypt(payload)

        dest_dir = os.path.dirname(destination_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        with open(destination_path, "wb") as dest_file:
            dest_file.write(encrypted)

    def decrypt_file(self, source_path: str, destination_path: str) -> None:
        with open(source_path, "rb") as source_file:
            payload = source_file.read()

        try:
            decrypted = self._fernet.decrypt(payload)
        except InvalidToken as exc:
            logger.error("Failed to decrypt file %s: invalid token", source_path)
            raise

        dest_dir = os.path.dirname(destination_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        with open(destination_path, "wb") as dest_file:
            dest_file.write(decrypted)
