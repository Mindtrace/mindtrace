#!/usr/bin/env python3
"""
Launch script for CRUD Service.

Run this script to start the CRUD service.
"""

from crud_service import CRUDService

if __name__ == "__main__":
    print("=" * 60)
    print("Starting CRUD Service")
    print("=" * 60)
    print("\nService will be available at: http://localhost:8080")
    print("Swagger UI: http://localhost:8080/docs")
    print("ReDoc: http://localhost:8080/redoc")
    print("\nPress Ctrl+C to stop the service")
    print("=" * 60 + "\n")

    CRUDService.launch(
        host="0.0.0.0",  # Listen on all interfaces
        port=8080,
        wait_for_launch=True,
        block=True,  # Keep service running
        timeout=30,
        progress_bar=False,  # Disable progress bar for cleaner output
    )
