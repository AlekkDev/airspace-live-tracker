"""`python -m ingest.admin add-collector`: creates a collector and prints its key once.

Only the key goes to stdout, so it can be piped straight into the collector's `.env`.
"""

import argparse
import secrets

import psycopg
from argon2 import PasswordHasher

from airspace_common.settings import AdminSettings


def add_collector(conninfo: str, collector_id: str, owner: str, offset_seconds: int) -> str:
    key = secrets.token_urlsafe(32)
    with psycopg.connect(conninfo) as conn:
        conn.execute(
            "INSERT INTO ops.collectors (collector_id, owner, offset_seconds, api_key_hash)"
            " VALUES (%s, %s, %s, %s)",
            (collector_id, owner, offset_seconds, PasswordHasher().hash(key)),
        )
    return key


def main() -> None:
    parser = argparse.ArgumentParser(prog="ingest.admin")
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("add-collector")
    add.add_argument("--id", required=True)
    add.add_argument("--owner", required=True)
    add.add_argument("--offset", type=int, default=0, choices=[0, 45])
    args = parser.parse_args()
    conninfo = AdminSettings().admin_database_url.get_secret_value()
    print(add_collector(conninfo, args.id, args.owner, args.offset))


if __name__ == "__main__":
    main()
