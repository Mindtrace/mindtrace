"""Integration tests for Inspectra auth API (email/password login, refresh, me)."""


def _login(client, email: str, password: str):
    """POST /auth/login with email and password."""
    return client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )


def test_login_rejects_invalid_credentials(client):
    """Login with unknown email or wrong password returns 401."""
    resp = _login(client, "nobody@example.com", "wrong")
    assert resp.status_code == 401, resp.text
    assert "Invalid email or password" in str(resp.json().get("detail"))


def test_login_requires_valid_body(client):
    """Login with missing or invalid body returns 422."""
    resp = client.post("/auth/login", json={"username": "alice", "password": "x"})
    assert resp.status_code == 422, resp.text


def test_login_success(client, auth_headers):
    """Login with seeded user returns tokens."""
    # auth_headers fixture creates user and logs in; we only need to assert token shape
    assert "Authorization" in auth_headers
    assert auth_headers["Authorization"].startswith("Bearer ")


def test_refresh(client, auth_headers):
    """POST /auth/refresh with valid refresh token returns new tokens."""
    login_resp = client.post(
        "/auth/login",
        json={"email": "super@inspectra-test.example.com", "password": "SuperAdminPass12!"},
    )
    assert login_resp.status_code == 200
    refresh_token = login_resp.json().get("refresh_token")
    assert refresh_token
    resp = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("access_token")
    assert data.get("refresh_token")


def test_get_me(client, auth_headers):
    """GET /auth/me with valid token returns current user."""
    resp = client.get("/auth/me", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["email"] == "super@inspectra-test.example.com"
    assert data["role"] == "super_admin"


def test_get_me_without_auth_returns_401(client):
    """GET /auth/me without Authorization header returns 401 (require_user)."""
    resp = client.get("/auth/me")
    assert resp.status_code == 401, resp.text
    assert (
        "Authorization" in resp.json().get("detail", "").lower() or "required" in resp.json().get("detail", "").lower()
    )
