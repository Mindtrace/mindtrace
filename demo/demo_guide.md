# Demo Guide — Mindtrace Service Supervisor Agent

## Setup before demo
```bash
# Terminal 1 — start the supervisor chat app
cd mindtrace/apps/mindtrace/apps/supervisor_chat
GEMINI_API_KEY=<key> python launch.py   # opens on http://localhost:8095

# Terminal 2 — keep this ready to trigger an error manually (Step 6)
# You'll run a quick Python snippet here during the demo
```

---

## Story Arc: "From zero running services to full observability in one chat"

---

### Step 1 — Introduction  *(~30 sec)*
**Prompt:**
```
Hi! Who are you and what can you help me with?
```
**What to say:** "The agent introduces itself — it knows its role, stays on topic,
and maintains conversation history across the session."

---

### Step 2 — Service Discovery  *(~45 sec)*
**Prompt:**
```
What services are available in the Mindtrace package?
```
**What to say:** "The Launcher sub-agent scans all installed packages using Python's
`__subclasses__()` registry. It builds a live catalog — no config file, no manual
registration. Works for any package."

**Expected output:** EchoService and DiscordService with descriptions.

---

### Step 3 — Launch a Service  *(~60 sec)*
**Prompt:**
```
Start EchoService on port 8765
```
**Follow-up (launcher asks to confirm):**
```
Yes, go ahead
```
**What to say:** "The agent never starts blindly — it confirms first. Once confirmed,
it uses importlib to dynamically resolve and launch the class as a subprocess.
Watch the chat — you'll see a live system notification when the service comes online."

---

### Step 4 — Check Running Services  *(~30 sec)*
**Prompt:**
```
What services are currently running?
```
**What to say:** "EchoService registered itself automatically on startup via a
lifecycle hook — zero manual registration. The supervisor sees it immediately."

---

### Step 5 — Live Health Check  *(~30 sec)*
**Prompt:**
```
Check if EchoService is healthy right now
```
**What to say:** "This fires a live HTTP heartbeat to the service. The monitor also
polls every 30 seconds in the background automatically."

---

### Step 6 — Inject an Error  *(before asking Step 7)*
**In Terminal 2, run:**
```python
import requests
requests.post("http://localhost:8765/echo", json={"message": "test", "delay": -1})
```
**What to say:** "I'm going to deliberately send a bad request to EchoService —
a negative delay that will cause it to crash internally."

---

### Step 7 — Error Detection  *(~45 sec)*
**Prompt:**
```
Were there any errors in EchoService in the last hour?
```
**What to say:** "The agent searches JSONL error logs written by the service's
own process. It returns the full traceback, the exact file and line number,
and a code snippet showing where the error occurred — in plain English."

---

### Step 8 — Show Service Logs  *(~30 sec)*
**Prompt:**
```
Show me the logs for EchoService
```
**What to say:** "The agent tails the service's structlog file in real time —
application logs, heartbeats, lifecycle events, all in one place."

---

### Step 9 — Restart the Service  *(~45 sec)*
**Prompt:**
```
EchoService seems unstable. Restart it.
```
**What to say:** "Even though EchoService was launched in a separate terminal,
the supervisor can restart it — it stored the module path on registration,
issues an HTTP shutdown, then relaunches the class as a new subprocess."

---

### Step 10 — Final Status  *(~20 sec)*
**Prompt:**
```
Give me a status summary of all services
```
**What to say:** "Clean summary — uptime, error count, restart count, last heartbeat.
Everything the team needs at a glance."

---

## Backup prompts (if anything goes wrong)
```
List all registered services
```
```
What monitoring tools do you have?
```
```
Diagnose EchoService
```

---

## Key talking points
- **No config files** — services self-register on startup, self-deregister on shutdown
- **Cross-process** — supervisor and services are independent OS processes
- **Two error channels** — lifecycle monitor + JSONL error files with full tracebacks
- **Sub-agent architecture** — Supervisor delegates discovery/launch to a dedicated Launcher agent
- **Any package** — add `launcher_roots=["yourpackage.services"]` and all your services appear in the catalog
- **Purple UI** — real-time SSE streaming, tool call activity visible as it happens
