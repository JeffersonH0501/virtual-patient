#!/bin/bash

# Development server with auto-reload
# Similar to nodemon for Node.js

echo "🚀 Starting development server with auto-reload..."
echo "📁 Watching: app/, scripts/, main.py"
echo "🔄 Auto-reload: ENABLED"
echo "============================================================"

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run with uvicorn and reload
python dev.py

