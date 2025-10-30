# Mindtrace Logging Sample (Loki + Grafana + Promtail)

This sample demonstrates structured logging from a Mindtrace service using `structlog`, collected by Promtail and visualized in Grafana via Loki.

## Prerequisites
- Docker and Docker Compose
- Python environment with `mindtrace` installed

## Paths
This setup tails logs from these absolute directories (configured in Mindtrace `Config`):
- Struct logs (JSON): `${HOME}/.cache/mindtrace/structlogs`
- Plain logs: `${HOME}/.cache/mindtrace/logs`

## 1) Start Loki, Grafana, and Promtail
From this directory:

```bash
cd samples/core/logging/service_log_setup/logging
cp env.example .env  # then edit .env if needed
docker compose --env-file .env up -d
```

- Grafana: http://localhost:3000 (admin / admin)
- Loki API: http://localhost:3100

## 2) Run the demo service
Run the example FastAPI service that uses `Service` and `RequestLoggingMiddleware`:

```bash
python launch.py
```

The service starts on `http://localhost:8080`.

## 3) Generate some logs
Send a few requests:

```bash
curl -sS -X POST http://localhost:8080/echo -H 'Content-Type: application/json' -d '{"message":"hello"}'
curl -sS -X POST http://localhost:8080/status
curl -sS -X POST http://localhost:8080/heartbeat
```

These produce structured logs under `structlogs/modules/*.log` and request envelopes from the middleware.

## 4) View logs in Grafana
1. Open Grafana at http://localhost:3000 and log in (admin / admin).
2. Go to Explore → select datasource "Loki".
3. Try queries:
   - `{job="mindtrace-structlogs"}`
   - `{job="mindtrace-structlogs", logger=~"mindtrace.*LoggingDemoService.*"}`
   - `{job="mindtrace-plain-logs"}`

Useful labels: `level`, `logger`, `event`, `service`, `operation`, `request_id`.

## 5) Stop everything
```bash
docker compose down
```

## Notes
- Struct logging is enabled by default (`MINDTRACE_LOGGER_USE_STRUCTLOG=True`).
- Promtail config parses JSON logs and promotes common keys to labels for easy filtering in Grafana. 