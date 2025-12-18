import uuid

def _u(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"

def _register(client, username: str, password: str):
    return client.post("/auth/register", json={"username": username, "password": password})

def _login(client, username: str, password: str):
    return client.post("/auth/login", json={"username": username, "password": password})

def test_register_returns_token(client):
    username = _u("alice")
    resp = _register(client, username, "secret123")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body.get("access_token"), str) and body["access_token"]
    if "token_type" in body:
        assert body["token_type"] == "bearer"

def test_register_duplicate_username_fails(client):
    username = _u("bob")
    password = "secret123"

    first = _register(client, username, password)
    assert first.status_code == 200, first.text

    dup = _register(client, username, password)
    assert dup.status_code == 400, dup.text

    detail = dup.json().get("detail")
    assert "Username already exists" in str(detail)

def test_login_success(client):
    username = _u("charlie")
    password = "secret123"

    resp_register = _register(client, username, password)
    assert resp_register.status_code == 200, resp_register.text

    resp_login = _login(client, username, password)
    assert resp_login.status_code == 200, resp_login.text

    data = resp_login.json()
    assert isinstance(data.get("access_token"), str) and data["access_token"]
    if "token_type" in data:
        assert data["token_type"] == "bearer"

def test_login_invalid_credentials(client):
    username = _u("ghost")
    resp = _login(client, username, "wrong")

    assert resp.status_code == 401, resp.text
    assert "Invalid username or password" in str(resp.json().get("detail"))