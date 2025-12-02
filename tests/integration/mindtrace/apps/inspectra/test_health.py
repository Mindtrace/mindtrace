def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_config_endpoint(client):
    resp = client.get("/config")
    assert resp.status_code == 200
    data = resp.json()

    # Minimal sanity checks; actual values come from .env
    assert "name" in data
    assert "version" in data
    assert "author" in data
    assert "author_email" in data
    assert "url" in data
