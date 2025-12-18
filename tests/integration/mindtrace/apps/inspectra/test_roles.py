def test_list_roles_shape(client):
    resp = client.get("/roles")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert isinstance(payload["total"], int)
    assert payload["total"] == len(payload["items"])


def test_create_role(client):
    resp = client.post(
        "/roles",
        json={"name": "admin", "description": "Administrator role", "permissions": None},
    )
    assert resp.status_code == 200, resp.text

    role = resp.json()
    assert role["name"] == "admin"
    assert role["description"] == "Administrator role"
    assert "id" in role


def test_create_and_list_roles(client):
    before = client.get("/roles")
    assert before.status_code == 200, before.text
    before_payload = before.json()
    before_total = before_payload["total"]

    create_resp = client.post(
        "/roles",
        json={"name": "admin", "description": "Administrator role", "permissions": None},
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