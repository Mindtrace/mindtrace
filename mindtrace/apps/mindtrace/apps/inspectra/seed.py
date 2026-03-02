"""
Seed the Inspectra database: create default organization "mindtrace" and a SUPER_ADMIN user.

Run after DB is up (e.g. docker compose up -d mongo) and before or after starting the API.

  From repo root (with env set):
    uv run python -m mindtrace.apps.inspectra.seed

  Loads .env from the inspectra app dir and from the current directory (so MONGO_URI is set).
  If Mongo requires auth, set MONGO_URI with credentials (see README).
"""

import asyncio
import os
import sys
from pathlib import Path

import dotenv

from mindtrace.apps.inspectra.core import get_inspectra_config, hash_password
from mindtrace.apps.inspectra.db import get_odm, init_db
from mindtrace.apps.inspectra.models.enums import OrganizationStatus, UserRole
from mindtrace.apps.inspectra.models.organization import Organization
from mindtrace.apps.inspectra.models.user import User


# Load .env so MONGO_URI (and other vars) are set when running the seed from any directory
def _load_dotenv() -> None:
    """Load .env from the inspectra app dir and from the current working directory."""
    # 1) Inspectra app dir (mindtrace/apps/mindtrace/apps/inspectra/.env)
    app_dir = Path(__file__).resolve().parent
    dotenv.load_dotenv(app_dir / ".env")
    # 2) Current working directory (e.g. docker/inspectra/.env when run from there)
    dotenv.load_dotenv()


_load_dotenv()


async def run_seed() -> None:
    """Create default organization and SUPER_ADMIN user from env (SEED_ORG_NAME, SEED_SUPER_ADMIN_*)."""
    get_inspectra_config()  # ensure config (and .env) loaded
    org_name = os.environ.get("SEED_ORG_NAME", "mindtrace")
    email = os.environ.get("SEED_SUPER_ADMIN_EMAIL", "superadmin@mindtrace.ai")
    password = os.environ.get("SEED_SUPER_ADMIN_PASSWORD", "ChangeMe123!")
    first_name = os.environ.get("SEED_SUPER_ADMIN_FIRST_NAME", "Mindtrace")
    last_name = os.environ.get("SEED_SUPER_ADMIN_LAST_NAME", "SuperAdmin")

    await init_db()
    odm = get_odm()

    # Create organization if not exists
    existing_orgs = await odm.organization.find(Organization.name == org_name)
    if existing_orgs:
        org = existing_orgs[0]
        print(f"Organization '{org_name}' already exists (id={org.id})")
    else:
        org = Organization(name=org_name, status=OrganizationStatus.ACTIVE)
        org = await odm.organization.insert(org)
        print(f"Created organization '{org_name}' (id={org.id})")

    # Create SUPER_ADMIN user if not exists (by email)
    email_norm = email.casefold()
    existing_users = await odm.user.find({"email_norm": email_norm})
    if existing_users:
        existing = existing_users[0]
        force_update = os.environ.get("SEED_FORCE_UPDATE_PASSWORD", "").strip().lower() in ("1", "true", "yes")
        if force_update:
            existing.pw_hash = hash_password(password)
            await odm.user.update(existing)
            print(f"Updated password for existing super admin user '{email}' (id={existing.id})")
        else:
            print(
                f"Super admin user '{email}' already exists (id={existing.id}). To set password to current .env, run with SEED_FORCE_UPDATE_PASSWORD=1"
            )
        return

    pw_hash = hash_password(password)
    user = User(
        organization=org,
        email=email,
        email_norm=email_norm,
        role=UserRole.SUPER_ADMIN,
        first_name=first_name,
        last_name=last_name,
        pw_hash=pw_hash,
    )
    user = await odm.user.insert(user)
    print(f"Created SUPER_ADMIN user '{email}' (id={user.id})")
    print("Seed completed successfully.")


def main() -> None:
    """Entry point: run the seed script (default org + SUPER_ADMIN user)."""
    try:
        asyncio.run(run_seed())
    except Exception as e:
        err = str(e).lower()
        print(f"Seed failed: {e}", file=sys.stderr)
        if "authentication" in err or "unauthorized" in err or "auth" in err:
            print(
                "\nMongoDB auth failed. Check:\n"
                "  1. MONGO_URI in .env has the same user/password as docker/inspectra/.env (MONGO_INITDB_ROOT_USERNAME, MONGO_INITDB_ROOT_PASSWORD).\n"
                "  2. If you changed those after first starting Mongo, the DB was already initialized. Reset the volume and recreate:\n"
                "       cd docker/inspectra && docker compose down -v && docker compose up -d mongo\n"
                "     Then run this seed again.",
                file=sys.stderr,
            )
        sys.exit(1)


if __name__ == "__main__":
    main()
