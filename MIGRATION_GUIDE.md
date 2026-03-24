# Database Migration Guide - Email Infrastructure Update

## Overview
The email infrastructure improvements require two new columns in the `email_events` table:
- `html_body` (VARCHAR 8000): Stores HTML versions of emails
- `retry_count` (INTEGER): Tracks delivery retry attempts

## Error
If you see this error in logs:
```
UndefinedColumn: column email_events.html_body does not exist
```

The production database is missing these columns and needs to be migrated.

---

## Option 1: Using Migration Script (Recommended)

### Step 1: Install Alembic Dependency
```bash
pip install alembic
```

### Step 2: Run Quick Migration Script
```bash
python migrate_email_columns.py
```

This script safely adds the missing columns using `IF NOT EXISTS` clause.

---

## Option 2: Using Alembic (Full Migration Management)

### Step 1: List Pending Migrations
```bash
alembic current
alembic history
```

### Step 2: Run Migration
```bash
alembic upgrade head
```

This will run all pending migrations including the email columns.

---

## Option 3: Direct SQL (For Render Dashboard or psql)

If you need to run SQL directly on your production database:

```sql
-- Add html_body column
ALTER TABLE email_events 
ADD COLUMN IF NOT EXISTS html_body VARCHAR(8000) NULL;

-- Add retry_count column  
ALTER TABLE email_events 
ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
```

### How to Execute on Render:
1. Go to your Render PostgreSQL database dashboard
2. Open the query editor or connect via psql
3. Run the SQL statements above
4. Verify the columns exist: `\d email_events`

---

## Verification

After migration, verify the columns exist:

```sql
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'email_events' 
AND column_name IN ('html_body', 'retry_count');
```

Should return:
```
column_name  | data_type
html_body    | character varying
retry_count  | integer
```

---

## Future Migrations

For future schema changes:
1. Update the model in `app/models.py`
2. Create new migration file in `alembic/versions/`
3. Run `alembic upgrade head`

Or auto-generate migrations:
```bash
alembic revision --autogenerate -m "description of change"
alembic upgrade head
```

---

## Troubleshooting

### Migration fails with "column already exists"
The columns may already be in the database. Verify with:
```sql
\d email_events
```

### Alembic history is empty
This is the first migration. Alembic will track all future migrations from this point.

### Need to rollback?
```bash
alembic downgrade -1
```

---

## Files Added
- `alembic/` - Alembic migration framework
- `alembic/versions/001_add_email_columns.py` - Email columns migration
- `migrate_email_columns.py` - Quick migration script
- `MIGRATION_GUIDE.md` - This guide
- Updated `requirements.txt` with alembic and requests

## Next Steps
1. Run migration on production
2. Commit and push these migration files to git
3. Monitor logs for any email delivery issues
4. All subsequent migrations should use Alembic
