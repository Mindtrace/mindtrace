"""Stable Mongo URIs for datalake unit tests (offline, mock-backed).

MongoDB client's default ``serverSelectionTimeoutMS`` is typically ~30s. When a Motor
construction slips past unit-test mocks that should fully stub the ODM, tests can hang
near that ceiling. Use aggressive, low timeouts so failures remain obvious and cheap.
"""

# loopback discard port — not expected to serve Mongo in unit runs
DATALAKE_UNIT_MONGO_URI: str = (
    "mongodb://127.0.0.1:9/?directConnection=true&serverSelectionTimeoutMS=200&connectTimeoutMS=200&socketTimeoutMS=200"
)
