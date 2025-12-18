def test_list_lines_shape(client):
    """
    GET /lines should return a stable, predictable response shape.

    The endpoint must return:
    - a JSON object (dict)
    - an `items` list
    - a numeric `total`
    - `total` must always match len(items)
    """
    resp = client.get("/lines")
    print(resp.text)

    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert isinstance(payload["total"], int)
    assert payload["total"] == len(payload["items"])


def test_list_lines_empty(client):
    """
    GET /lines on an empty database should return an empty collection.

    This test ensures the API:
    - does NOT return null
    - does NOT omit fields
    - returns a consistent empty structure
    """
    resp = client.get("/lines")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert payload == {
        "items": [],
        "total": 0,
    }


def test_create_and_list_lines(client):
    """
    Creating a line should make it visible in subsequent list calls.

    This test verifies:
    - POST /lines persists data
    - GET /lines reflects newly created lines
    - returned IDs and fields remain consistent
    """
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
    """
    POST /lines should create a single line and return its representation.

    Verifies:
    - request succeeds without auth
    - response contains generated ID
    - optional plant_id can be null
    """
    resp = client.post(
        "/lines",
        json={"name": "Line 1", "plant_id": None},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["name"] == "Line 1"
    assert body["plant_id"] is None
    assert isinstance(body["id"], str)
    assert body["id"]
