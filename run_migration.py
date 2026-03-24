#!/usr/bin/env python
"""
Direct SQL execution to add missing email columns.
This executes raw SQL directly without ORM - perfect for production fixes.
"""

import os
import sys

def run_migration_sql():
    """Execute SQL to add missing columns using psycopg directly."""
    try:
        import psycopg
    except ImportError:
        print("psycopg not installed, installing...")
        os.system("pip install psycopg[binary]")
        import psycopg
    
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ DATABASE_URL environment variable not set")
        return False
    
    try:
        # Connect using the connection string
        with psycopg.connect(database_url) as conn:
            with conn.cursor() as cur:
                # Add html_body column
                cur.execute("""
                    ALTER TABLE email_events 
                    ADD COLUMN IF NOT EXISTS html_body VARCHAR(8000) NULL;
                """)
                print("✓ Added html_body column")
                
                # Add retry_count column
                cur.execute("""
                    ALTER TABLE email_events 
                    ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
                """)
                print("✓ Added retry_count column")
                
                conn.commit()
        
        print("✅ Migration completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False

if __name__ == "__main__":
    success = run_migration_sql()
    sys.exit(0 if success else 1)
