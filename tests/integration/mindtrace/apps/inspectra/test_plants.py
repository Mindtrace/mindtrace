def test_create_plant(client):
    """
    POST /plants should create a new plant and return its full representation.

    Verifies:
    - request succeeds
    - all provided fields are persisted
    - a non-empty string ID is generated
    """
    resp = client.post(
        "/plants",
        json={
            "name": "Plant A",
            "code": "PA",
            "location": "Factory 1",
            "is_active": True,
        },
    )
    assert resp.status_code == 200, resp.text

    plant = resp.json()
    assert plant["name"] == "Plant A"
    assert plant["code"] == "PA"
    assert plant["location"] == "Factory 1"
    assert plant["is_active"] is True
    assert isinstance(plant["id"], str) and plant["id"]


def test_list_plants_shape(client):
    """
    GET /plants should always return a stable list response shape.

    The response must include:
    - an `items` array
    - a numeric `total`
    - total must equal len(items)
    """
    resp = client.get("/plants")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert isinstance(payload["total"], int)
    assert payload["total"] == len(payload["items"])


def test_create_and_list_plants(client):
    """
    Creating a plant should increase the total count and appear in listings.

    Verifies:
    - list endpoint is callable before creation
    - POST /plants persists data
    - subsequent GET /plants reflects the new plant
    - returned IDs are consistent
    """
    before = client.get("/plants")
    assert before.status_code == 200, before.text
    before_total = before.json()["total"]

    create_resp = client.post(
        "/plants",
        json={
            "name": "Plant A",
            "code": "PA",
            "location": "Factory 1",
            "is_active": True,
        },
    )
    assert create_resp.status_code == 200, create_resp.text
    created = create_resp.json()
    created_id = created["id"]

    after = client.get("/plants")
    assert after.status_code == 200, after.text
    payload = after.json()

    assert payload["total"] == len(payload["items"])
    assert payload["total"] == before_total + 1
    assert any(p["id"] == created_id for p in payload["items"])
    assert any(
        p["name"] == "Plant A" and p["location"] == "Factory 1"
        for p in payload["items"]
    )