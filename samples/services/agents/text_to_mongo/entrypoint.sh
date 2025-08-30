#!/bin/bash

# Start Ollama in the background.
/bin/ollama serve &
# Record Process ID.
pid=$!

# Pause for Ollama to start.
sleep 5

echo "Retrieve qwen3:32b model..."
ollama pull qwen3:32b
echo "Done!"

# Wait for Ollama process to finish.
wait $pid