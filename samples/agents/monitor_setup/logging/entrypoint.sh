#!/bin/bash

# Start Ollama in the background
/bin/ollama serve &
# Record Process ID
pid=$!

# Pause for Ollama to start
sleep 5

echo "Retrieving Ollama models..."
ollama pull llama3.1
ollama pull qwen2.5
echo "Done!"

# Wait for Ollama process to finish
wait $pid

