def _token(client, username="lines_user", password="secret123") -> str:
    resp = client.post("/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def test_create_line_requires_auth(client):
    resp = client.post("/lines/", json={"name": "Line 1", "plant_id": None})
    assert resp.status_code == 401


def test_create_and_list_lines(client):
    token = _token(client)

    create_resp = client.post(
        "/lines/",
        json={"name": "Line 1", "plant_id": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 200

    line = create_resp.json()
    assert line["name"] == "Line 1"
    assert "id" in line

    list_resp = client.get(
        "/lines/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200

    lines = list_resp.json()
    assert any(l["name"] == "Line 1" for l in lines)