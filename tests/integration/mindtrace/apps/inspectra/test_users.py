"""Integration tests for Inspectra users API (list, create, get, update)."""


def test_list_users(client, auth_headers):
    """GET /users returns list (at least the super_admin)."""
    resp = client.get("/users", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)
    assert data["total"] >= 1


def test_create_user(client, auth_headers):
    """POST /users creates a user in an org."""
    orgs_resp = client.get("/organizations", headers=auth_headers)
    assert orgs_resp.status_code == 200
    items = orgs_resp.json().get("items") or []
    if not items:
        create_org = client.post(
            "/organizations",
            headers=auth_headers,
            json={"name": "UserTestOrg"},
        )
        assert create_org.status_code == 200
        org_id = create_org.json()["id"]
    else:
        org_id = items[0]["id"]

    resp = client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": "newuser@inspectra-test.example.com",
            "password": "NewUserPass12!",
            "role": "user",
            "organization_id": org_id,
            "first_name": "New",
            "last_name": "User",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["email"] == "newuser@inspectra-test.example.com"
    assert data["role"] == "user"
    user_id = data["id"]

    get_resp = client.get(f"/users/{user_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["email"] == "newuser@inspectra-test.example.com"


def test_update_user(client, auth_headers):
    """PUT /users/:id updates name, role, or status."""
    me_resp = client.get("/auth/me", headers=auth_headers)
    assert me_resp.status_code == 200
    user_id = me_resp.json()["id"]

    resp = client.put(
        f"/users/{user_id}",
        headers=auth_headers,
        json={"first_name": "UpdatedFirst", "last_name": "UpdatedLast"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["first_name"] == "UpdatedFirst"
    assert resp.json()["last_name"] == "UpdatedLast"


def test_users_require_admin_or_super(client, auth_headers_user):
    """GET /users as regular user returns 403 (require_admin_or_super)."""
    resp = client.get("/users", headers=auth_headers_user)
    assert resp.status_code == 403, resp.text


def test_create_user_admin_cannot_create_super_admin(client, auth_headers_admin):
    """Admin cannot create super_admin user."""
    me = client.get("/auth/me", headers=auth_headers_admin).json()
    org_id = me.get("organization_id") or "507f1f77bcf86cd799439011"
    resp = client.post(
        "/users",
        headers=auth_headers_admin,
        json={
            "email": "new@inspectra-test.example.com",
            "password": "NewUserPass12!",
            "role": "super_admin",
            "organization_id": org_id,
            "first_name": "N",
            "last_name": "U",
        },
    )
    assert resp.status_code == 403, resp.text
    assert "super_admin" in resp.json().get("detail", "").lower()


def test_create_user_weak_password_returns_400(client, auth_headers):
    """POST /users with weak password returns 400."""
    orgs_resp = client.get("/organizations", headers=auth_headers)
    org_id = orgs_resp.json()["items"][0]["id"] if orgs_resp.json().get("items") else None
    if not org_id:
        cr = client.post("/organizations", headers=auth_headers, json={"name": "PwOrg"})
        org_id = cr.json()["id"]
    resp = client.post(
        "/users",
        headers=auth_headers,
        json={
            "email": "weak@inspectra-test.example.com",
            "password": "short",
            "role": "user",
            "organization_id": org_id,
            "first_name": "W",
            "last_name": "U",
        },
    )
    assert resp.status_code == 400, resp.text
    data = resp.json()
    detail = data.get("detail")
    if isinstance(detail, dict):
        assert "message" in detail or "errors" in detail
    else:
        assert "password" in (detail or "").lower() or "errors" in data


def test_create_user_duplicate_email_returns_400(client, auth_headers):
    """POST /users with existing email returns 400."""
    org_id = client.get("/organizations", headers=auth_headers).json()["items"][0]["id"]
    payload = {
        "email": "dup@inspectra-test.example.com",
        "password": "DupUserPass12!",
        "role": "user",
        "organization_id": org_id,
        "first_name": "D",
        "last_name": "U",
    }
    client.post("/users", headers=auth_headers, json=payload)
    resp = client.post("/users", headers=auth_headers, json=payload)
    assert resp.status_code == 400, resp.text
    assert "email" in resp.json().get("detail", "").lower() or "already" in str(resp.json()).lower()


def test_get_user_not_found_returns_404(client, auth_headers):
    """GET /users/:id with bad id returns 404."""
    resp = client.get("/users/507f1f77bcf86cd799439011", headers=auth_headers)
    assert resp.status_code == 404, resp.text


def test_update_user_not_found_returns_404(client, auth_headers):
    """PUT /users/:id with bad id returns 404."""
    resp = client.put(
        "/users/507f1f77bcf86cd799439011",
        headers=auth_headers,
        json={"first_name": "X"},
    )
    assert resp.status_code == 404, resp.text
