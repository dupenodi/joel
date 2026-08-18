"""Encrypted credential storage.

Tokens and Composio account ids are encrypted before they enter SQLite. A
stable Fernet key is derived from ``JOEL_SECRET``; local installs without one
get a generated secret in the data volume so credentials still survive restarts.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken


class OAuthError(RuntimeError):
    pass


def _secret(data_dir: Path) -> bytes:
    configured = os.getenv("JOEL_SECRET", "").strip()
    if configured:
        return configured.encode()

    path = data_dir / ".joel-secret"
    if path.exists():
        return path.read_bytes().strip()
    data_dir.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(48).encode()
    path.write_bytes(generated)
    path.chmod(0o600)
    return generated


def _fernet(data_dir: Path) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(_secret(data_dir)).digest())
    return Fernet(key)


def encrypt_credentials(credentials: dict[str, Any], data_dir: Path) -> str:
    payload = json.dumps(credentials, separators=(",", ":")).encode()
    return _fernet(data_dir).encrypt(payload).decode()


def decrypt_credentials(ciphertext: str, data_dir: Path) -> dict[str, Any]:
    try:
        payload = _fernet(data_dir).decrypt(ciphertext.encode())
    except InvalidToken as exc:
        raise OAuthError(
            "Stored credentials cannot be decrypted; JOEL_SECRET may have changed"
        ) from exc
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise OAuthError("Stored credential payload is invalid")
    return value


def validate_return_to(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise OAuthError("return_to must be an absolute http(s) URL")
    return value
