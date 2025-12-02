def _register_and_get_token(client, username="role_user", password="secret123") -> str:
    resp = client.post("/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_default_user_role_created_and_listed(client):
    token = _register_and_get_token(client)

    resp = client.get(
        "/roles",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    roles = resp.json()
    assert isinstance(roles, list)
    assert any(r["name"] == "user" for r in roles)


def test_create_additional_role(client):
    token = _register_and_get_token(client, username="admin_like")

    payload = {"name": "admin", "description": "Administrator role"}
    resp = client.post(
        "/roles",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    role = resp.json()
    assert role["name"] == "admin"
    assert role["description"] == "Administrator role"
