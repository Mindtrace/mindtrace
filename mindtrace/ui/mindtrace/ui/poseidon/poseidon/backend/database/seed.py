#!/usr/bin/env python3
"""
Database seed file to create the initial organization and superadmin user.
"""

import asyncio
import hashlib
import secrets

from .init import initialize_database
from .models.organization import Organization
from .models.user import User
from .models.enums import OrgRole, SubscriptionPlan


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 (simple hashing for demo purposes)"""
    return hashlib.sha256(password.encode()).hexdigest()


async def create_initial_organization() -> Organization:
    """Create the initial 'mindtrace' organization"""
    print("Creating initial organization...")
    
    # Check if organization already exists
    existing_org = await Organization.find_one(Organization.name == "mindtrace")
    if existing_org:
        print(f"✓ Organization 'mindtrace' already exists (ID: {existing_org.id})")
        return existing_org
    
    # Create the mindtrace organization
    org_data = {
        "name": "mindtrace",
        "description": "MindTrace main organization",
        "subscription_plan": SubscriptionPlan.ENTERPRISE,
        "max_users": None,  # Unlimited users
        "max_projects": None,  # Unlimited projects
        "is_active": True
    }
    
    organization = Organization(**org_data)
    await organization.save()
    
    print(f"✓ Created organization 'mindtrace' (ID: {organization.id})")
    print(f"  - Admin registration key: {organization.admin_registration_key}")
    return organization


async def create_superadmin_user(organization: Organization) -> User:
    """Create the initial superadmin user"""
    print("Creating superadmin user...")
    
    # Generate a secure default password
    default_password = secrets.token_urlsafe(16)
    password_hash = hash_password(default_password)
    
    # Create the superadmin user
    user_data = {
        "first_name": "MindTrace",
        "last_name": "SuperAdmin",
        "email": "superadmin@mindtrace.com",
        "password_hash": password_hash,
        "organization": organization,
        "org_role": OrgRole.SUPER_ADMIN,
        "is_active": True
    }
    
    user = User(**user_data)
    await user.save()
    
    print(f"✓ Created superadmin user 'mindtracesuperadmin' (ID: {user.id})")
    print(f"  - Email: {user.email}")
    print(f"  - Default password: {default_password}")
    print(f"  - Role: {user.org_role}")
    print(f"  - Organization: {organization.name}")
    
    return user


async def update_organization_user_count(organization: Organization):
    """Update the organization's user count"""
    user_count = await User.find(User.organization.id == organization.id).count()
    organization.user_count = user_count
    await organization.save()
    print(f"✓ Updated organization user count to {user_count}")


async def verify_setup():
    """Verify the setup was successful"""
    print("\nVerifying setup...")
    
    # Check organization
    org = await Organization.find_one(Organization.name == "mindtrace")
    if not org:
        print("❌ Organization 'mindtrace' not found!")
        return False
    
    # Fetch user's organization link
    await user.fetch_all_links()
    
    # Verify user is linked to organization
    if not user.organization or str(user.organization.id) != str(org.id):
        print("❌ User is not properly linked to organization!")
        return False
    
    # Verify user has super admin role
    if user.org_role != OrgRole.SUPER_ADMIN:
        print(f"❌ User role is {user.org_role}, expected {OrgRole.SUPER_ADMIN}!")
        return False
    
    print("✓ Setup verification successful!")
    print(f"  - Organization: {org.name} (ID: {org.id})")
    print(f"  - User: {user.first_name} {user.last_name} (ID: {user.id})")
    print(f"  - Role: {user.org_role}")
    print(f"  - Active: {user.is_active}")
    
    return True


async def seed_database():
    """Main seed function"""
    print("=" * 60)
    print("Starting database seeding...")
    print("=" * 60)
    
    try:
        # Initialize database
        print("Initializing database...")
        await initialize_database()
        print("✓ Database initialized successfully")
        print("-" * 60)
        
        # Create initial organization
        organization = await create_initial_organization()
        
        # Create superadmin user
        user = await create_superadmin_user(organization)
        
        # Update organization user count
        await update_organization_user_count(organization)
        
        # Verify setup
        if await verify_setup():
            print("-" * 60)
            print("🎉 Database seeding completed successfully!")
            print("\nIMPORTANT: Save the generated password above for the superadmin user!")
        else:
            print("❌ Setup verification failed!")
            return False
            
    except Exception as e:
        print(f"❌ Database seeding failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


async def reset_and_seed():
    """Reset and seed the database (WARNING: This will delete existing data)"""
    print("⚠️  WARNING: This will delete all existing organizations and users!")
    
    try:
        await initialize_database()
        
        # Delete all users and organizations
        await User.delete_all()
        await Organization.delete_all()
        
        print("✓ Cleared existing data")
        
        # Run seed
        return await seed_database()
        
    except Exception as e:
        print(f"❌ Reset and seed failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("MindTrace Database Seeding Tool")
    print("Choose an option:")
    print("1. Seed database (safe - won't overwrite existing data)")
    print("2. Reset and seed database (WARNING - will delete all data)")
    
    choice = input("Enter your choice (1 or 2): ").strip()
    
    if choice == "1":
        asyncio.run(seed_database())
    elif choice == "2":
        confirm = input("Are you sure you want to delete all data? Type 'yes' to confirm: ").strip().lower()
        if confirm == "yes":
            asyncio.run(reset_and_seed())
        else:
            print("Operation cancelled.")
    else:
        print("Invalid choice. Exiting.") 