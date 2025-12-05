def _token(client, username="plants_user", password="secret123") -> str:
    resp = client.post("/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]

def test_create_plant_requires_auth(client):
    resp = client.post("/plants/", json={"name": "Plant A", "location": "Factory 1"})
    assert resp.status_code == 401  # unauthorized

def test_create_and_list_plants(client):
    token = _token(client)

    create_resp = client.post(
        "/plants/",
        json={"name": "Plant A", "location": "Factory 1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_resp.status_code == 200

    plant = create_resp.json()
    assert plant["name"] == "Plant A"
    assert plant["location"] == "Factory 1"
    assert "id" in plant

    list_resp = client.get(
        "/plants/",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_resp.status_code == 200

    plants = list_resp.json()
    assert isinstance(plants, list)
    assert any(p["name"] == "Plant A" for p in plants)
