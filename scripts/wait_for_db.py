#!/usr/bin/env python
"""
Blocks until PostgreSQL accepts connections, or exits non-zero after a
timeout. Used by docker/django/entrypoint.sh before running migrations,
so a Django worker never starts against a database that isn't ready yet
-- this is a startup-ordering guard, not a substitute for the
`/health/ready` endpoint's ongoing checks.
"""
from __future__ import annotations

import os
import sys
import time

import psycopg

MAX_ATTEMPTS = 30
DELAY_SECONDS = 2


def main() -> None:
    dsn = {
        "dbname": os.environ.get("POSTGRES_DB", "nutrizone"),
        "user": os.environ.get("POSTGRES_USER", "nutrizone"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "host": os.environ.get("POSTGRES_HOST", "localhost"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
    }

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with psycopg.connect(**dsn, connect_timeout=3):
                print("[wait_for_db] PostgreSQL is ready.")
                return
        except psycopg.OperationalError as exc:
            print(f"[wait_for_db] Attempt {attempt}/{MAX_ATTEMPTS} failed: {exc}")
            time.sleep(DELAY_SECONDS)

    print("[wait_for_db] PostgreSQL did not become ready in time.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
