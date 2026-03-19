"""
Migration script: adds new Profile columns introduced in the 4-feature update.
Safe to run multiple times (uses try/except for each ALTER TABLE).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db

app = create_app()

NEW_COLUMNS = [
    "ALTER TABLE profiles ADD COLUMN auto_apply_match_threshold INTEGER DEFAULT 85",
    "ALTER TABLE profiles ADD COLUMN company_blacklist TEXT DEFAULT '[]'",
    "ALTER TABLE profiles ADD COLUMN company_whitelist TEXT DEFAULT '[]'",
    "ALTER TABLE profiles ADD COLUMN keyword_blockers TEXT DEFAULT '[]'",
    "ALTER TABLE profiles ADD COLUMN stealth_mode INTEGER DEFAULT 0",
]

with app.app_context():
    with db.engine.connect() as conn:
        for sql in NEW_COLUMNS:
            col = sql.split("ADD COLUMN")[1].strip().split()[0]
            try:
                conn.execute(db.text(sql))
                conn.commit()
                print(f"  + Added column: {col}")
            except Exception as e:
                err = str(e)
                if "duplicate column" in err.lower() or "already exists" in err.lower():
                    print(f"  = Column {col!r} already exists — skipped.")
                else:
                    print(f"  ! Error adding {col}: {e}")
    print("Migration complete.")
