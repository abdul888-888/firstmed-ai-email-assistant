#!/usr/bin/env python3
"""One-time script to run Alembic migrations and exit."""

import sys
from alembic import command
from alembic.config import Config

def main():
    print("Starting migrations...")
    
    # Create Alembic config
    alembic_cfg = Config("alembic.ini")
    
    try:
        # Run migrations
        command.upgrade(alembic_cfg, "head")
        print("✅ Migrations completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
