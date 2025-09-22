#!/usr/bin/env python3
"""Startup script for Camera Configurator app."""

import sys
import os
import subprocess

def main():
    """Run the camera configurator app."""
    print("🚀 Starting Camera Configurator...")
    print("📷 Connecting to camera API at http://192.168.50.32:8001")
    print("🌐 App will be available at http://localhost:3001")
    print()
    
    try:
        # Run the reflex app
        subprocess.run([sys.executable, "-m", "reflex", "run"], check=True)
    except KeyboardInterrupt:
        print("\n👋 Camera Configurator stopped")
    except subprocess.CalledProcessError as e:
        print(f"❌ Error running app: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())