# Monitor Agent Testing Setup (MockPLC Service + Loki + Grafana)

This sample demonstrates how to test the **Monitor Agent** using a mock PLC service that generates realistic log patterns. The Monitor Agent can convert natural language queries into LogQL queries for Loki and analyze logs.

## Overview

This setup includes:
- **MockPLC Service**: Simulates a PLC controller with realistic log patterns (scans, errors, defects)
- **Loki**: Log storage and indexing
- **Grafana**: Log visualization dashboard
- **Promtail**: Log collection agent
- **Monitor Agent**: AI-powered log querying and analysis

## Prerequisites

- Docker and Docker Compose
- Python environment with `mindtrace` installed

## Quick Start

### 1) Start Loki, Grafana, and Promtail

From this directory:

```bash
# Copy environment file if it doesn't exist
cd samples/agents/monitor_setup/plc_service/
cp env.example .env  # Edit .env if needed (optional)

# Start the logging stack
docker compose up -d
```

**Services:**
- **Grafana**: http://localhost:3000 (admin / admin)
- **Loki API**: http://localhost:3100

**Verify services are running:**
```bash
docker compose ps
```

### 2) Launch MockPLC Service

The MockPLC service simulates an industrial automation system that generates structured logs:

```bash
# Basic launch (service only)
python launch.py

# Launch with demo (generates sample logs automatically)
python launch.py --demo
```

**Service Options:**
```bash
python launch.py \
  --host 0.0.0.0 \
  --port 8080 \
  --plc-id PLC_001 \
  --error-rate 0.1 \
  --scan-interval 5.0 \
  --demo
```

**Service Endpoints:**
- `POST /trigger_scan` - Manually trigger a scan operation
- `GET /status` - Get service statistics
- `POST /ml_response` - Submit ML inference result

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
      "base_url": "http://localhost:11434",
      "default_model": "llama3.1"
    }
  }
}'
```

#### Query Logs with Natural Language

```bash
# Basic query - check for errors
mindtrace agents monitor query \
  -s MockPLCService \
  -q "show me all error logs"

# Query specific scan types
mindtrace agents monitor query \
  -s MockPLCService \
  -q "show all robot vision scans that completed successfully"

# Query for defects
mindtrace agents monitor query \
  -s MockPLCService \
  -q "find all defective parts detected in the last hour"

# Query with filters
mindtrace agents monitor query \
  -s MockPLCService \
  -q "show me timeout errors for static scans"

# Complex query
mindtrace agents monitor query \
  -s MockPLCService \
  -q "analyze all failed scans and tell me what went wrong"
```

**Service Name:** The service name in logs is `MockPLCService` (from the service class name).

#### Example Queries

```bash
# Check if any errors exist
mindtrace agents monitor query -s MockPLCService -q "do you see any error"

# Analyze scan 
mindtrace agents monitor query -s MockPLCService -q "do you see any logs for request id : f2f7f02d-0504-404d-8024-99a504622de5"
# Check for timeouts
mindtrace agents monitor query -s MockPLCService -q "show all timeout errors"
```

### 5) View Logs in Grafana (Optional)

1. Open Grafana at http://localhost:3000 and log in (admin / admin)
2. Go to **Explore** → select datasource **"Loki"**
3. Try LogQL queries:
   - `{service_name="MockPLCService"}`
   - `{service_name="MockPLCService"} |= "error"`
   - `{service_name="MockPLCService"} |~ "defect|timeout"`
   - `{service_name="MockPLCService", level="ERROR"}`
