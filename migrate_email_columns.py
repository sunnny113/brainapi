#!/usr/bin/env python
"""
Quick migration script to add missing columns to email_events table.
Run this on production if Alembic is not set up yet.

Usage:
    python migrate_email_columns.py
"""

import os
import sys
from sqlalchemy import create_engine, text

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.config import settings

def migrate_email_columns():
    """Add html_body and retry_count columns to email_events table."""
    
    engine = create_engine(settings.database_url)
    
    sql_statements = [
        # Add html_body column if it doesn't exist
        """
        ALTER TABLE email_events 
        ADD COLUMN IF NOT EXISTS html_body VARCHAR(8000) NULL;
        """,
        # Add retry_count column if it doesn't exist
        """
        ALTER TABLE email_events 
        ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
        """
    ]
    
    with engine.begin() as connection:
        for sql in sql_statements:
            try:
                connection.execute(text(sql))
                print(f"✓ Executed: {sql.strip()}")
            except Exception as e:
                print(f"✗ Error executing: {sql.strip()}")
                print(f"  Error: {e}")
                return False
    
    print("\n✅ Migration completed successfully!")
    return True

if __name__ == "__main__":
    try:
        success = migrate_email_columns()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
