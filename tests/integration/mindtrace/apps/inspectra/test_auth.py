def test_register_returns_token(client):
    payload = {"username": "alice", "password": "secret123"}

    resp = client.post("/auth/register", json=payload)
    assert resp.status_code == 200

    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


def test_register_duplicate_username_fails(client):
    payload = {"username": "bob", "password": "secret123"}

    first = client.post("/auth/register", json=payload)
    assert first.status_code == 200

    dup = client.post("/auth/register", json=payload)
    assert dup.status_code == 400
    assert "Username already exists" in dup.text


def test_login_success(client):
    payload = {"username": "charlie", "password": "secret123"}

    # ensure user exists
    client.post("/auth/register", json=payload)

    resp = client.post("/auth/login", json=payload)
    assert resp.status_code == 200

    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_login_invalid_credentials(client):
    resp = client.post(
        "/auth/login",
        json={"username": "ghost", "password": "wrong"},
    )
    assert resp.status_code == 401
