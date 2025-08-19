#!/bin/bash

# Start Ollama in the background.
/bin/ollama serve &
# Record Process ID.
pid=$!

# Pause for Ollama to start.
sleep 5

echo "Retrieve qwen2.5 model..."
ollama pull qwen2.5:7b
echo "Done!"

# Wait for Ollama process to finish.
wait $pid