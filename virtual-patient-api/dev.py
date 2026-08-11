#!/usr/bin/env python3
"""
Development server with auto-reload
Similar to nodemon for Node.js

Usage:
    python dev.py
"""

import uvicorn

if __name__ == "__main__":
    print("🚀 Starting development server with auto-reload...")
    print("📁 Watching: app/, scripts/, main.py")
    print("🔄 Auto-reload: ENABLED")
    print("=" * 60)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload
        reload_dirs=["app", "scripts"],  # Watch these directories
        reload_includes=["*.py"],  # Only watch Python files
        log_level="info"
    )

