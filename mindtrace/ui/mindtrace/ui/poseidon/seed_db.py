#!/usr/bin/env python3
"""
Standalone script to seed the database with initial data.
Usage: python seed_db.py
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from poseidon.backend.database.seed import seed_database, reset_and_seed

def main():
    """Main function for standalone script"""
    print("MindTrace Database Seeding Tool")
    print("=" * 40)
    print("This will create:")
    print("- Organization: 'mindtrace' (Enterprise plan)")
    print("- Superadmin user: 'mindtracesuperadmin'")
    print("- Email: superadmin@mindtrace.com")
    print("=" * 40)
    
    print("\nChoose an option:")
    print("1. Seed database (safe - won't overwrite existing data)")
    print("2. Reset and seed database (WARNING - will delete all data)")
    print("3. Exit")
    
    while True:
        choice = input("\nEnter your choice (1, 2, or 3): ").strip()
        
        if choice == "1":
            print("\nRunning safe seed...")
            success = asyncio.run(seed_database())
            if success:
                print("\n✅ Seeding completed successfully!")
            else:
                print("\n❌ Seeding failed!")
                sys.exit(1)
            break
            
        elif choice == "2":
            print("\n⚠️  WARNING: This will delete ALL existing data!")
            confirm = input("Are you sure you want to delete all data? Type 'yes' to confirm: ").strip().lower()
            if confirm == "yes":
                print("\nRunning reset and seed...")
                success = asyncio.run(reset_and_seed())
                if success:
                    print("\n✅ Reset and seed completed successfully!")
                else:
                    print("\n❌ Reset and seed failed!")
                    sys.exit(1)
            else:
                print("Operation cancelled.")
            break
            
        elif choice == "3":
            print("Exiting...")
            sys.exit(0)
            
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    main() 