"""Integration tests for Inspectra organizations API (SUPER_ADMIN)."""


def test_list_organizations_empty(client, auth_headers):
    """GET /organizations returns list (empty or with seeded org)."""
    resp = client.get("/organizations", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


def test_create_organization(client, auth_headers):
    """POST /organizations creates an org and returns it."""
    resp = client.post(
        "/organizations",
        headers=auth_headers,
        json={"name": "NewOrg"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "NewOrg"
    assert "id" in data
    org_id = data["id"]
    get_resp = client.get(f"/organizations/{org_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "NewOrg"


def test_update_organization(client, auth_headers):
    """PUT /organizations/:id updates name and/or is_active."""
    create_resp = client.post(
        "/organizations",
        headers=auth_headers,
        json={"name": "ToUpdate"},
    )
    assert create_resp.status_code == 200
    org_id = create_resp.json()["id"]
    resp = client.put(
        f"/organizations/{org_id}",
        headers=auth_headers,
        json={"name": "UpdatedName"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "UpdatedName"


def test_organizations_require_super_admin(client, auth_headers_admin):
    """GET /organizations as admin returns 403 (require_super_admin)."""
    resp = client.get("/organizations", headers=auth_headers_admin)
    assert resp.status_code == 403, resp.text
    assert "super admin" in resp.json().get("detail", "").lower()


def test_create_organization_duplicate_name_returns_400(client, auth_headers):
    """POST /organizations with existing name returns 400."""
    client.post("/organizations", headers=auth_headers, json={"name": "DupOrg"})
    resp = client.post("/organizations", headers=auth_headers, json={"name": "DupOrg"})
    assert resp.status_code == 400, resp.text
    assert "already exists" in resp.json().get("detail", "").lower()


def test_get_organization_not_found_returns_404(client, auth_headers):
    """GET /organizations/:id with bad id returns 404."""
    resp = client.get(
        "/organizations/507f1f77bcf86cd799439011",
        headers=auth_headers,
    )
    assert resp.status_code == 404, resp.text


def test_update_organization_not_found_returns_404(client, auth_headers):
    """PUT /organizations/:id with bad id returns 404."""
    resp = client.put(
        "/organizations/507f1f77bcf86cd799439011",
        headers=auth_headers,
        json={"name": "X"},
    )
    assert resp.status_code == 404, resp.text
