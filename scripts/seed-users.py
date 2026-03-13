"""Seed a user into the CRAIC team database."""

import argparse
import sqlite3
import sys
from pathlib import Path

import bcrypt


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a CRAIC team user.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--db", default="/data/team.db")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    password_hash = bcrypt.hashpw(args.password.encode(), bcrypt.gensalt()).decode()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, datetime('now'))",
            (args.username, password_hash),
        )
        conn.commit()
        print(f"User '{args.username}' created.")
    except sqlite3.IntegrityError:
        print(f"User '{args.username}' already exists.", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
