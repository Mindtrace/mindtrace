#!/usr/bin/env python3
"""Launch the SupervisorChat backend service.

Run from repo root:

  # With Gemini (recommended):
  GEMINI_API_KEY=AIza... \\
  PYTHONPATH=mindtrace/agents:mindtrace/services:mindtrace/core:mindtrace/apps \\
  .venv/bin/python mindtrace/apps/mindtrace/apps/supervisor_chat/launch.py

  # With Ollama (no API key required — run `ollama serve` first):
  OLLAMA_MODEL=llama3.2 \\
  PYTHONPATH=mindtrace/agents:mindtrace/services:mindtrace/core:mindtrace/apps \\
  .venv/bin/python mindtrace/apps/mindtrace/apps/supervisor_chat/launch.py

  # With JSONL error log persistence:
  GEMINI_API_KEY=AIza... \\
  PYTHONPATH=mindtrace/agents:mindtrace/services:mindtrace/core:mindtrace/apps \\
  .venv/bin/python mindtrace/apps/mindtrace/apps/supervisor_chat/launch.py

Then start the frontend (separate terminal):
  cd mindtrace/apps/mindtrace/apps/supervisor_chat/frontend
  npm install && npm run dev
  # Open http://localhost:5173
"""

import os
from urllib.parse import urlparse

from mindtrace.apps.supervisor_chat.backend import SupervisorChatService
from mindtrace.core import CoreConfig

os.environ["GEMINI_API_KEY"] = "AIzaSyB06067y8ihOHjEK5XdwkoE7w2RiEZRM80"
config = CoreConfig()
_supervisor_url = config.MINDTRACE_SUPERVISOR.SUPERVISOR_URL
HOST = urlparse(_supervisor_url).hostname
PORT = urlparse(_supervisor_url).port

if __name__ == "__main__":
    SupervisorChatService.launch(host=HOST, port=PORT, block=True)
