# Monitor Agent Testing Setup (Logging Service + Loki + Grafana)

This sample demonstrates how to test the **Monitor Agent** using a Logging service that generates realistic log patterns. The Monitor Agent can convert natural language queries into LogQL queries for Loki and analyze logs.

## Overview

This setup includes:
- **Logging Service**: Simulates a Logging controller with realistic log patterns (scans, errors, defects)
- **Loki**: Log storage and indexing
- **Grafana**: Log visualization dashboard
- **Promtail**: Log collection agent
- **Monitor Agent**: AI-powered log querying and analysis

## Prerequisites

- Docker and Docker Compose
- Python environment with `mindtrace` installed

## Quick Start

### 1) Start Loki, Grafana, and Promtail


```bash
# Copy environment file if it doesn't exist
cp samples/agents/monitor_setup/logging/env.example samples/agents/monitor_setup/logging/.env

# Start the logging stack
sudo docker compose -f samples/agents/monitor_setup/logging/docker-compose.yml up -d  
```

**Services:**
- **Grafana**: http://localhost:3000 (admin / admin)
- **Loki API**: http://localhost:3100

**Verify services are running:**
```bash
sudo docker ps
```

### 2) Launch Logging Service

The Logging service simulates an industrial automation system that generates structured logs:

```bash
python -m samples.agents.monitor_setup.logging.launch
```


**Log Types Generated:**
- `static_scan_started/complete`
- `robot_vision_scan_started/complete`
- `thread_check_scan_started/complete`
- `capture_timeout` (errors)
- `defect_detected` (warnings)
- `plc_communication_error` (errors)

### 3) Generate Logs

The service automatically generates logs via background scanning.


**Wait 10-15 seconds** after starting the service for logs to accumulate in Loki.

### 4) Test Monitor Agent

The Monitor Agent converts natural language queries into LogQL and analyzes logs:

#### Configure Monitor Agent (Optional)

```bash
# Configure Loki URL and agent settings
mindtrace agents monitor configure --config '{
  "LOKI_URL": "http://localhost:3100",
  "MT_LLM_PROVIDERS": {
    "ollama": {
      "type": "ollama",
      "base_url": "http://localhost:11435",
      "default_model": "llama3.1"
    }
  }
}'
```

#### Query Logs with Natural Language

```bash
mindtrace agents monitor query -s LoggingService -q "analyze all errors and tell me what went wrong"
```

### 5) View Logs in Grafana (Optional)

1. Open Grafana at http://localhost:3000 and log in (admin / admin)
2. Go to **Explore** → select datasource **"Loki"**
3. Try LogQL queries:
   - `{service_name="Lo"}`
   - `{service_name="LoggingService"} |= "error"`
   - `{service_name="LoggingService"} |~ "defect|timeout"`
   - `{service_name="LoggingService", level="ERROR"}`
