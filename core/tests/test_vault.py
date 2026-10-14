import json
import sys

import pytest

from huntly.security.vault import InvalidPassword, Vault, VaultError, VaultLocked, decrypt_value, encrypt_value
from huntly.services import store

from .conftest import FAST_KDF, PASSWORD


def test_create_unlock_lock_cycle(tmp_path):
    v = Vault(tmp_path / "vault.json", FAST_KDF)
    assert not v.initialized
    v.create(PASSWORD)
    assert v.unlocked
    v.lock()
    with pytest.raises(VaultLocked):
        v.dek()
    with pytest.raises(InvalidPassword):
        v.unlock("wrong password!!")
    v.unlock(PASSWORD)
    assert v.unlocked


def test_short_password_rejected(tmp_path):
    with pytest.raises(VaultError):
        Vault(tmp_path / "v.json", FAST_KDF).create("short")


def test_vault_file_has_no_key_material_in_clear(tmp_path):
    v = Vault(tmp_path / "vault.json", FAST_KDF)
    v.create(PASSWORD)
    raw = (tmp_path / "vault.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["cipher"] == "AES-256-GCM"
    assert data["kdf"]["name"] == "argon2id"
    assert PASSWORD not in raw
    import base64

    assert base64.b64encode(v.dek()).decode() not in raw
    if sys.platform != "win32":  # POSIX permissions; Windows relies on the per-user profile ACL
        assert oct((tmp_path / "vault.json").stat().st_mode)[-3:] == "600"


def test_secret_roundtrip_and_aad_binding(tmp_path):
    v = Vault(tmp_path / "vault.json", FAST_KDF)
    v.create(PASSWORD)
    nonce, ct = encrypt_value(v.dek(), "groq_api_key", "gsk_supersecretvalue123")
    assert b"gsk_supersecret" not in ct
    assert decrypt_value(v.dek(), "groq_api_key", nonce, ct) == "gsk_supersecretvalue123"
    with pytest.raises(VaultError):
        decrypt_value(v.dek(), "x_bearer_token", nonce, ct)  # swapped name must fail


def test_change_password(tmp_path):
    v = Vault(tmp_path / "vault.json", FAST_KDF)
    v.create(PASSWORD)
    dek = v.dek()
    v.change_password(PASSWORD, "another long password")
    v.lock()
    with pytest.raises(InvalidPassword):
        v.unlock(PASSWORD)
    v.unlock("another long password")
    assert v.dek() == dek  # existing secrets stay readable


def test_secrets_stored_encrypted_in_database(unlocked):
    secret = "gsk_" + "ThisMustNeverAppearInPlaintext42"
    with unlocked.db.session() as s:
        store.put_secret(s, unlocked.vault, "groq_api_key", secret)
    unlocked.db.engine.dispose()
    for f in unlocked.paths.root.rglob("*"):
        if f.is_file():
            assert secret.encode() not in f.read_bytes(), f"plaintext secret found in {f}"
    assert unlocked.secret("groq_api_key") == secret
    unlocked.vault.lock()
    with pytest.raises(VaultLocked):
        unlocked.secret("groq_api_key")


def test_keyring_unlock(tmp_path, monkeypatch):
    stored = {}

    class FakeKeyring:
        @staticmethod
        def set_password(service, user, value):
            stored[(service, user)] = value

        @staticmethod
        def get_password(service, user):
            return stored.get((service, user))

        @staticmethod
        def delete_password(service, user):
            stored.pop((service, user), None)

    import sys

    monkeypatch.setitem(sys.modules, "keyring", FakeKeyring)
    v = Vault(tmp_path / "vault.json", FAST_KDF)
    v.create(PASSWORD, use_keyring=True)
    dek = v.dek()
    v2 = Vault(tmp_path / "vault.json", FAST_KDF)
    assert v2.try_keyring_unlock()
    assert v2.dek() == dek
    v2.disable_keyring()
    v3 = Vault(tmp_path / "vault.json", FAST_KDF)
    assert not v3.try_keyring_unlock()
