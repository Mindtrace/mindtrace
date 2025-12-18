def test_list_lines_shape(client):
    resp = client.get("/lines")
    print(resp.text)
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert isinstance(payload["total"], int)
    assert payload["total"] == len(payload["items"])


def test_list_lines_empty(client):
    resp = client.get("/lines")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert payload == {
        "items": [],
        "total": 0,
    }


def test_create_and_list_lines(client):
    # create
    create_resp = client.post(
        "/lines",
        json={"name": "Assembly Line A", "plant_id": "plant-123"},
    )
    assert create_resp.status_code == 200, create_resp.text

    created = create_resp.json()
    created_id = created["id"]

    # list
    list_resp = client.get("/lines")
    assert list_resp.status_code == 200, list_resp.text

    payload = list_resp.json()
    assert payload["total"] == 1
    assert len(payload["items"]) == 1

    item = payload["items"][0]
    assert item["id"] == created_id
    assert item["name"] == "Assembly Line A"
    assert item["plant_id"] == "plant-123"

def test_create_line(client):
    resp = client.post(
        "/lines",
        json={"name": "Line 1", "plant_id": None},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["name"] == "Line 1"
    assert body["plant_id"] is None
    assert isinstance(body["id"], str)
    assert body["id"]  # non-empty