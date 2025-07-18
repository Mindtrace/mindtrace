# Database Seeding

This directory contains the database seeding functionality for MindTrace. The seed file creates the initial organization and superadmin user required for the system to function.

## What gets created

- **Organization**: `mindtrace` (Enterprise plan with unlimited users and projects)
- **Superadmin User**: `mindtracesuperadmin` with email `superadmin@mindtrace.com`
- **Role**: Super Admin with full system access

## Usage

### Option 1: Standalone Script (Recommended)

Run the standalone script from the poseidon directory:

```bash
cd mindtrace/ui/mindtrace/ui/poseidon
python seed_db.py
```

This will show an interactive menu with options:
1. **Safe seed** - Creates initial data without overwriting existing records
2. **Reset and seed** - ⚠️ **WARNING**: Deletes ALL data and creates fresh initial data
3. **Exit** - Quit the seeding tool

### Option 2: Direct Import

```python
import asyncio
from poseidon.backend.database.seed import seed_database, reset_and_seed

# Safe seed (won't overwrite existing data)
asyncio.run(seed_database())

# Reset and seed (deletes all data first)
asyncio.run(reset_and_seed())
```

### Option 3: Command Line Module

```bash
cd mindtrace/ui/mindtrace/ui/poseidon
python -m poseidon.backend.database.seed
```

## Important Notes

### Password Security
- The script generates a **secure random password** for the superadmin user
- **SAVE THE PASSWORD** shown in the output - it's only displayed once
- The password is hashed using SHA-256 before storage

### Safe Operations
- Running the seed multiple times is safe
- The script checks for existing data and won't create duplicates
- Only use the "reset and seed" option if you want to start fresh

### Generated Data Example
```
✓ Created organization 'mindtrace' (ID: 687a0a02729546165b913abf)
  - Admin registration key: ORG_eZJRFioOpE8574tFgePKmAhJL3VgzsniNupryNxL1KU

✓ Created superadmin user 'mindtracesuperadmin' (ID: 687a0a02729546165b913ac0)
  - Email: superadmin@mindtrace.com
  - Default password: nFNfL7FckLsE1guyA6ZGEw  # ⚠️ SAVE THIS PASSWORD!
  - Role: OrgRole.SUPER_ADMIN
  - Organization: mindtrace
```

## Database Schema

The seeding process creates data that follows the Link field structure:

- **Organization**: Standard organization with enterprise features
- **User**: Linked to the organization with `OrgRole.SUPER_ADMIN` role
- **Relationships**: Proper Link field connections between models

## Verification

The script includes automatic verification that:
- Organization was created successfully
- User was created successfully
- User is properly linked to organization
- User has correct super admin role
- All data is active and accessible

## Troubleshooting

If seeding fails:
1. Ensure database connection is available
2. Check that all models are properly defined
3. Verify the database initialization completes successfully
4. Check the error output for specific issues

For database connection issues, ensure your MongoDB instance is running and accessible via the configured connection string in your settings. 