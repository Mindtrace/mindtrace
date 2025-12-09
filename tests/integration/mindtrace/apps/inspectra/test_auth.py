import requests


def _register(cm, username: str, password: str):
    """Helper to register a user via the running Inspectra service."""
    payload = {"username": username, "password": password}
    resp = requests.post(f"{cm.url}/auth/register", json=payload)
    return resp


def _login(cm, username: str, password: str):
    """Helper to login via the running Inspectra service."""
    payload = {"username": username, "password": password}
    resp = requests.post(f"{cm.url}/auth/login", json=payload)
    return resp


def test_register_returns_token(inspectra_cm):
    resp = _register(inspectra_cm, "alice", "secret123")

    assert resp.status_code == 200

    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_register_duplicate_username_fails(inspectra_cm):
    username = "bob"
    password = "secret123"

    first = _register(inspectra_cm, username, password)
    assert first.status_code == 200

    dup = _register(inspectra_cm, username, password)
    assert dup.status_code == 400
    assert "Username already exists" in dup.text


def test_login_success(inspectra_cm):
    username = "charlie"
    password = "secret123"

    # ensure user exists
    resp_register = _register(inspectra_cm, username, password)
    assert resp_register.status_code == 200

    resp_login = _login(inspectra_cm, username, password)
    assert resp_login.status_code == 200

    data = resp_login.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(inspectra_cm):
    resp = _login(inspectra_cm, "ghost", "wrong")
    assert resp.status_code == 401
