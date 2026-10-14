"""Local credential vault.

Design
------
* A random 256-bit data-encryption key (DEK) encrypts every secret with AES-256-GCM.
  The secret's name is bound as associated data, so ciphertexts cannot be swapped.
* The DEK is itself wrapped with AES-256-GCM under a key-encryption key (KEK)
  derived from the user's master password with Argon2id (RFC 9106 parameters).
* Only the salt, KDF parameters and wrapped DEK are written to ``vault.json``.
  The master password and the DEK never touch disk in plaintext.
* Optionally the user may let the OS keychain (libsecret / Keychain / Credential
  Manager) hold the DEK so the vault unlocks automatically on this device.

There is no recovery mechanism and no escrow: nobody but the user, including
the project maintainers, can decrypt the vault.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import threading
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

from huntly.security.redact import forget_all_secrets, register_secret

log = logging.getLogger(__name__)

VAULT_VERSION = 1
KEYRING_SERVICE = "huntly"
KEYRING_USER = "vault-dek"
MIN_PASSWORD_LENGTH = 10

# Argon2id parameters (RFC 9106 "second recommended option": 64 MiB, t=3, p=4).
DEFAULT_KDF = {"name": "argon2id", "memory_cost": 65536, "iterations": 3, "lanes": 4, "length": 32}


class VaultError(Exception):
    pass


class VaultLocked(VaultError):
    pass


class VaultNotInitialized(VaultError):
    pass


class InvalidPassword(VaultError):
    pass


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def derive_kek(password: str, salt: bytes, params: dict) -> bytes:
    if params.get("name") != "argon2id":
        raise VaultError(f"Unsupported KDF {params.get('name')!r}")
    kdf = Argon2id(
        salt=salt,
        length=params["length"],
        iterations=params["iterations"],
        lanes=params["lanes"],
        memory_cost=params["memory_cost"],
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_value(dek: bytes, name: str, plaintext: str) -> tuple[bytes, bytes]:
    nonce = os.urandom(12)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), f"huntly-secret:{name}".encode())
    return nonce, ct


def decrypt_value(dek: bytes, name: str, nonce: bytes, ciphertext: bytes) -> str:
    try:
        pt = AESGCM(dek).decrypt(nonce, ciphertext, f"huntly-secret:{name}".encode())
    except InvalidTag as exc:
        raise VaultError(f"Secret {name!r} failed integrity check") from exc
    return pt.decode("utf-8")


@dataclass
class VaultStatus:
    initialized: bool
    unlocked: bool
    keyring_enabled: bool
    keyring_available: bool


class Vault:
    """Holds the unwrapped DEK in memory while unlocked."""

    def __init__(self, path: Path, kdf_params: dict | None = None):
        self.path = path
        self._kdf_params = kdf_params or DEFAULT_KDF
        self._dek: bytes | None = None
        self._lock = threading.RLock()

    # -- state -------------------------------------------------------------
    def _read(self) -> dict:
        if not self.path.exists():
            raise VaultNotInitialized("Vault has not been created yet")
        return json.loads(self.path.read_text("utf-8"))

    def _write(self, data: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), "utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(self.path)

    @property
    def initialized(self) -> bool:
        return self.path.exists()

    @property
    def unlocked(self) -> bool:
        return self._dek is not None

    def status(self) -> VaultStatus:
        enabled = False
        if self.initialized:
            try:
                enabled = bool(self._read().get("keyring_enabled"))
            except (OSError, ValueError):
                enabled = False
        return VaultStatus(self.initialized, self.unlocked, enabled, keyring_available())

    def dek(self) -> bytes:
        with self._lock:
            if self._dek is None:
                raise VaultLocked("Vault is locked")
            return self._dek

    # -- lifecycle ---------------------------------------------------------
    def create(self, password: str, use_keyring: bool = False) -> None:
        with self._lock:
            if self.initialized:
                raise VaultError("Vault already exists")
            validate_password(password)
            dek = AESGCM.generate_key(bit_length=256)
            self._write(self._wrap(dek, password, keyring_enabled=False))
            self._dek = dek
            if use_keyring:
                self.enable_keyring()
            log.info("vault created")

    def _wrap(self, dek: bytes, password: str, keyring_enabled: bool) -> dict:
        salt = os.urandom(16)
        kek = derive_kek(password, salt, self._kdf_params)
        nonce = os.urandom(12)
        wrapped = AESGCM(kek).encrypt(nonce, dek, b"huntly-vault-dek-v1")
        return {
            "version": VAULT_VERSION,
            "cipher": "AES-256-GCM",
            "kdf": {**self._kdf_params, "salt": _b64e(salt)},
            "wrapped_dek": {"nonce": _b64e(nonce), "ciphertext": _b64e(wrapped)},
            "keyring_enabled": keyring_enabled,
        }

    def unlock(self, password: str) -> None:
        with self._lock:
            data = self._read()
            kdf = dict(data["kdf"])
            salt = _b64d(kdf.pop("salt"))
            kek = derive_kek(password, salt, kdf)
            try:
                dek = AESGCM(kek).decrypt(
                    _b64d(data["wrapped_dek"]["nonce"]),
                    _b64d(data["wrapped_dek"]["ciphertext"]),
                    b"huntly-vault-dek-v1",
                )
            except InvalidTag as exc:
                raise InvalidPassword("Incorrect master password") from exc
            self._dek = dek
            log.info("vault unlocked")

    def try_keyring_unlock(self) -> bool:
        if not self.initialized or self.unlocked:
            return self.unlocked
        try:
            if not self._read().get("keyring_enabled"):
                return False
            import keyring

            stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        except Exception as exc:  # keyring backends raise many types
            log.warning("keyring unlock unavailable: %s", type(exc).__name__)
            return False
        if not stored:
            return False
        dek = _b64d(stored)
        if len(dek) != 32:
            return False
        with self._lock:
            self._dek = dek
        log.info("vault unlocked via OS keychain")
        return True

    def lock(self) -> None:
        with self._lock:
            self._dek = None
        forget_all_secrets()
        log.info("vault locked")

    def change_password(self, old: str, new: str) -> None:
        with self._lock:
            validate_password(new)
            self.unlock(old)
            data = self._read()
            self._write(self._wrap(self.dek(), new, keyring_enabled=bool(data.get("keyring_enabled"))))
            log.info("vault password changed")

    def enable_keyring(self) -> None:
        import keyring

        with self._lock:
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, _b64e(self.dek()))
            data = self._read()
            data["keyring_enabled"] = True
            self._write(data)

    def disable_keyring(self) -> None:
        with self._lock:
            try:
                import keyring

                keyring.delete_password(KEYRING_SERVICE, KEYRING_USER)
            except Exception:
                pass
            if self.initialized:
                data = self._read()
                data["keyring_enabled"] = False
                self._write(data)

    # -- secrets -----------------------------------------------------------
    def seal(self, name: str, value: str) -> tuple[bytes, bytes]:
        register_secret(value)
        return encrypt_value(self.dek(), name, value)

    def open(self, name: str, nonce: bytes, ciphertext: bytes) -> str:
        value = decrypt_value(self.dek(), name, nonce, ciphertext)
        register_secret(value)
        return value


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise VaultError(f"Master password must be at least {MIN_PASSWORD_LENGTH} characters")


def keyring_available() -> bool:
    try:
        import keyring
        from keyring.backends import fail

        return not isinstance(keyring.get_keyring(), fail.Keyring)
    except Exception:
        return False


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)
