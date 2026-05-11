#!/usr/bin/env bash
# Pull the vision model into both Ollama containers.
# Usage: ./pull_models.sh [model_name]
#   model_name defaults to gemma3:4b

set -e
MODEL="${1:-gemma4:latest}"

echo "Pulling '$MODEL' into ollama1 (port 11434)..."
docker exec ollama1 ollama pull "$MODEL"

echo "Pulling '$MODEL' into ollama2 (port 11435)..."
docker exec ollama2 ollama pull "$MODEL"

echo "Done. Both instances ready."
