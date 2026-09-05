"""Seed a Postgres database with the generated dataset.

Connection details come from the environment (.env is loaded automatically):

    DATABASE_URL   required; standard Postgres connection string
    DB_SCHEMA      optional; target schema (created if missing, default search path)

Applies the schema file (drop and recreate, so re-runs are idempotent), bulk
loads every CSV with COPY in foreign-key order, then runs reconciliation
checks against the loaded data.

Usage:
    python -m src.seed [--config PATH] [--data-dir PATH] [--skip-schema]
"""

import argparse
import os
import sys
import time
from pathlib import Path

import psycopg

from src.settings import Settings, load_settings

VALIDATIONS = [
    ("row counts per table", """
        select 'bookings' t, count(*) n from bookings
        union all select 'daily_property_metrics', count(*) from daily_property_metrics
        union all select 'daily_channel_metrics', count(*) from daily_channel_metrics
        union all select 'daily_campaign_metrics', count(*) from daily_campaign_metrics
        union all select 'daily_market_metrics', count(*) from daily_market_metrics
        order by 1"""),
    ("date coverage", """
        select min(date), max(date), count(*) as days from daily_property_metrics"""),
    ("channel facts reconcile with bookings (expect 0)", """
        select count(*) from (
            select b.booking_date
            from bookings b
            where b.booking_date between (select min(date) from daily_property_metrics)
                                     and (select max(date) from daily_property_metrics)
            group by b.booking_date
            having count(*) <> (select sum(bookings) from daily_channel_metrics c
                                where c.date = b.booking_date)) mismatched"""),
    ("orphaned foreign keys (expect 0)", """
        select (select count(*) from bookings b
                left join markets m on m.id = b.market_id where m.id is null)
             + (select count(*) from bookings b
                left join channels c on c.id = b.channel_id where c.id is null)
             + (select count(*) from daily_campaign_metrics d
                left join campaigns c on c.id = d.campaign_id where c.id is null)"""),
]


def load_table(cur: psycopg.Cursor, table: str, csv_path: Path) -> int:
    with cur.copy(
        f"COPY {table} FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')"
    ) as copy, open(csv_path, "rb") as f:
        while chunk := f.read(65536):
            copy.write(chunk)
    cur.execute(f"select count(*) from {table}")
    return cur.fetchone()[0]


def seed(settings: Settings, database_url: str, data_dir: Path | None = None,
         db_schema: str | None = None, apply_schema: bool = True) -> None:
    data_dir = data_dir or settings.data_dir
    started = time.time()

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            if db_schema:
                cur.execute(f'create schema if not exists "{db_schema}"')
                cur.execute(f'set search_path to "{db_schema}"')
            if apply_schema:
                print("Applying schema...")
                cur.execute(settings.schema_path.read_text())
            for table, csv_name in settings.load_order:
                count = load_table(cur, table, data_dir / csv_name)
                print(f"  {table:<24} {count:>7,} rows")
        conn.commit()

        print("\nValidations:")
        with conn.cursor() as cur:
            if db_schema:
                cur.execute(f'set search_path to "{db_schema}"')
            for label, sql in VALIDATIONS:
                cur.execute(sql)
                print(f"  [{label}]")
                for row in cur.fetchall():
                    print(f"    {row}")

    print(f"\nDone in {time.time() - started:.1f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("--data-dir", type=Path, help="directory containing CSVs")
    parser.add_argument("--skip-schema", action="store_true", help="load data only")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("error: DATABASE_URL is not set (see .env.example)", file=sys.stderr)
        return 1

    settings = load_settings(args.config)
    seed(
        settings,
        database_url=database_url,
        data_dir=args.data_dir,
        db_schema=os.getenv("DB_SCHEMA"),
        apply_schema=not args.skip_schema,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
