"""Boot the actual Android API before any cryptography module is imported."""

import os
from pathlib import Path
import subprocess
import sys


def test_android_boots_without_openssl_legacy_provider(tmp_path):
    root = Path(__file__).resolve().parents[1]
    script = r'''
import builtins
import importlib.util
import os
from pathlib import Path
import sys
import types

root, data_root = map(Path, sys.argv[1:])
os.environ.pop("CRYPTOGRAPHY_OPENSSL_NO_LEGACY", None)
real_import = builtins.__import__

def without_legacy_provider(name, *args, **kwargs):
    if name == "cryptography" or name.startswith("cryptography."):
        assert os.environ.get("CRYPTOGRAPHY_OPENSSL_NO_LEGACY") == "1", (
            "Android attempted to import cryptography before disabling the absent legacy provider"
        )
    return real_import(name, *args, **kwargs)

builtins.__import__ = without_legacy_provider

def verify_api(app, **settings):
    from fastapi.testclient import TestClient
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from services.auth import create_session_token, read_session_token

    assert settings["host"] == "127.0.0.1"
    assert settings["port"] == 45873
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/search", params={"q": "fiscal de postura IDCAP"}).status_code == 401
        preflight = client.options("/api/v1/search", headers={
            "Origin": "https://tauri.localhost",
            "Access-Control-Request-Method": "GET",
        })
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "https://tauri.localhost"

    # Disabling obsolete ciphers must preserve the authenticated encryption
    # used to protect the working database and local authentication session.
    aes = AESGCM(AESGCM.generate_key(bit_length=256))
    nonce, clear = os.urandom(12), b"protected Android processing data"
    encrypted = aes.encrypt(nonce, clear, b"android")
    assert aes.decrypt(nonce, encrypted, b"android") == clear
    try:
        aes.decrypt(nonce, encrypted[:-1] + bytes([encrypted[-1] ^ 1]), b"android")
    except InvalidTag:
        pass
    else:
        raise AssertionError("Tampered ciphertext was accepted")
    assert read_session_token(create_session_token(42)) == 42
    assert (data_root / "processing.db").is_file()
    assert len((data_root / ".engine-key").read_text()) >= 48
    print("ANDROID_BOOTSTRAP_OK: API, protected search, CORS, AES-GCM and session")

# Exercise the real bootstrap and real API in-process without opening a
# persistent HTTP server during the test. No API dependencies are replaced.
sys.modules["uvicorn"] = types.SimpleNamespace(run=verify_api)
spec = importlib.util.spec_from_file_location("mobile_engine", root / "desktop/engine/android/mobile_engine.py")
mobile_engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile_engine)
mobile_engine.run(str(data_root), "https://example.supabase.co", "sb_publishable_test")
'''
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(root)
    result = subprocess.run(
        [sys.executable, "-c", script, str(root), str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ANDROID_BOOTSTRAP_OK" in result.stdout
