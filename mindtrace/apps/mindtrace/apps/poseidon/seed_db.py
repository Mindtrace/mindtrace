#!/usr/bin/env python3
"""
Standalone script to seed the database with initial data.
Usage: python seed_db.py

This script is safe to run in production as it only creates data if it doesn't exist.
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from poseidon.backend.database.seed import seed_database

def main():
    """Main function for standalone script"""
    print("MindTrace Database Seeding Tool")
    print("=" * 40)
    print("This will create:")
    print("- Organization: 'mindtrace' (Enterprise plan)")
    print("- Superadmin user: 'mindtracesuperadmin'")
    print("- Email: superadmin@mindtrace.com")
    print("=" * 40)
    print("\n⚠️  This tool is safe to run in production!")
    print("   It only creates data if it doesn't already exist.")
    print("=" * 40)
    
    print("\nStarting safe seed...")
    success = asyncio.run(seed_database())
    if success:
        print("\n✅ Seeding completed successfully!")
    else:
        print("\n❌ Seeding failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 