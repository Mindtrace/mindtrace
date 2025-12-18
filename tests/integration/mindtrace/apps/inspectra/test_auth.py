import uuid

import requests


def _u(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _register(cm, username: str, password: str):
    payload = {"username": username, "password": password}
    return requests.post(f"{cm.url}/auth/register", json=payload)

def _login(cm, username: str, password: str):
    payload = {"username": username, "password": password}
    return requests.post(f"{cm.url}/auth/login", json=payload)

def test_register_returns_token(inspectra_cm):
    username = _u("alice")
    resp = _register(inspectra_cm, username, "secret123")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"

def test_register_duplicate_username_fails(inspectra_cm):
    username = _u("bob")
    password = "secret123"

    first = _register(inspectra_cm, username, password)
    assert first.status_code == 200, first.text

    dup = _register(inspectra_cm, username, password)
    assert dup.status_code == 400, dup.text
    assert "Username already exists" in dup.text

def test_login_success(inspectra_cm):
    username = _u("charlie")
    password = "secret123"

    resp_register = _register(inspectra_cm, username, password)
    assert resp_register.status_code == 200, resp_register.text

    resp_login = _login(inspectra_cm, username, password)
    assert resp_login.status_code == 200, resp_login.text

    data = resp_login.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_invalid_credentials(inspectra_cm):
    username = _u("ghost")
    resp = _login(inspectra_cm, username, "wrong")
    assert resp.status_code == 401, resp.text