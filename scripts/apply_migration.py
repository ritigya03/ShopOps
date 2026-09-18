"""Apply a SQL migration file to the database pointed at by DATABASE_URL.

Usage:
    python scripts/apply_migration.py db/migrations/005_fix_view_fanouts.sql
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from sqlalchemy.engine import make_url

load_dotenv()


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/apply_migration.py <path-to-migration.sql>")
        sys.exit(1)

    migration_path = Path(sys.argv[1])
    url = make_url(os.environ["DATABASE_URL"])

    print(f"Applying {migration_path} to {url.host}:{url.port}/{url.database} ...")
    conn = psycopg2.connect(
        host=url.host, port=url.port, dbname=url.database,
        user=url.username, password=url.password, sslmode="require",
        connect_timeout=10,
    )
    conn.autocommit = True
    conn.cursor().execute(migration_path.read_text())
    conn.close()
    print("applied")


if __name__ == "__main__":
    main()
