def test_list_roles_shape(client):
    """
    GET /roles should always return a stable list response shape.

    Verifies:
    - response is a dictionary
    - `items` is a list
    - `total` is an integer
    - `total` matches len(items)
    """
    resp = client.get("/roles")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert isinstance(payload["total"], int)
    assert payload["total"] == len(payload["items"])


def test_create_role(client):
    """
    POST /roles should create a new role and return its representation.

    Verifies:
    - role creation succeeds
    - returned payload contains expected fields
    - a non-empty role ID is generated
    """
    resp = client.post(
        "/roles",
        json={
            "name": "admin",
            "description": "Administrator role",
            "permissions": None,
        },
    )
    assert resp.status_code == 200, resp.text

    role = resp.json()
    assert role["name"] == "admin"
    assert role["description"] == "Administrator role"
    assert "id" in role


def test_create_and_list_roles(client):
    """
    Creating a role should increase the total count and appear in listings.

    Verifies:
    - roles can be listed before creation
    - POST /roles persists the role
    - subsequent GET /roles includes the new role
    - total count increments correctly
    """
    before = client.get("/roles")
    assert before.status_code == 200, before.text
    before_payload = before.json()
    before_total = before_payload["total"]

    create_resp = client.post(
        "/roles",
        json={
            "name": "admin",
            "description": "Administrator role",
            "permissions": None,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()
    created_id = created["id"]

    after = client.get("/roles")
    assert after.status_code == 200, after.text
    payload = after.json()

    assert payload["total"] == len(payload["items"])
    assert payload["total"] == before_total + 1
    assert any(r["id"] == created_id for r in payload["items"])
    assert any(r["name"] == "admin" for r in payload["items"])
