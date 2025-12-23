import uuid


def _u(prefix: str = "user") -> str:
    """
    Generate a unique username for tests.

    Uses a short UUID suffix to avoid collisions between tests,
    even when the database is reused or tests run in parallel.

    Args:
        prefix: Optional prefix to make usernames easier to read in logs.

    Returns:
        A unique username string.
    """
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _register(client, username: str, password: str):
    """
    Helper to register a user via the Inspectra auth endpoint.

    Args:
        client: FastAPI TestClient instance.
        username: Username to register.
        password: Plain-text password.

    Returns:
        FastAPI TestClient response.
    """
    return client.post(
        "/auth/register",
        json={"username": username, "password": password},
    )


def _login(client, username: str, password: str):
    """
    Helper to log a user in via the Inspectra auth endpoint.

    Args:
        client: FastAPI TestClient instance.
        username: Username to authenticate.
        password: Plain-text password.

    Returns:
        FastAPI TestClient response.
    """
    return client.post(
        "/auth/login",
        json={"username": username, "password": password},
    )


def test_register_returns_token(client):
    """
    Registering a new user should succeed and return an access token.

    The response must include:
    - a non-empty access_token
    - token_type == "bearer" (if present)
    """
    username = _u("alice")
    resp = _register(client, username, "secret123")

    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert isinstance(body.get("access_token"), str)
    assert body["access_token"]

    if "token_type" in body:
        assert body["token_type"] == "bearer"


def test_register_duplicate_username_fails(client):
    """
    Registering the same username twice should fail with HTTP 400.

    Ensures username uniqueness is enforced at the service level.
    """
    username = _u("bob")
    password = "secret123"

    first = _register(client, username, password)
    assert first.status_code == 200, first.text

    dup = _register(client, username, password)
    assert dup.status_code == 400, dup.text

    detail = dup.json().get("detail")
    assert "Username already exists" in str(detail)


def test_login_success(client):
    """
    Logging in with valid credentials should return a bearer token.

    This test verifies the full register → login flow.
    """
    username = _u("charlie")
    password = "secret123"

    resp_register = _register(client, username, password)
    assert resp_register.status_code == 200, resp_register.text

    resp_login = _login(client, username, password)
    assert resp_login.status_code == 200, resp_login.text

    data = resp_login.json()
    assert isinstance(data.get("access_token"), str)
    assert data["access_token"]

    if "token_type" in data:
        assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client):
    """
    Logging in with invalid credentials should fail with HTTP 401.

    Ensures incorrect username/password combinations are rejected.
    """
    username = _u("ghost")
    resp = _login(client, username, "wrong")

    assert resp.status_code == 401, resp.text
    assert "Invalid username or password" in str(resp.json().get("detail"))
