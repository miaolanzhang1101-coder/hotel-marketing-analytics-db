"""Integrity tests against a seeded database.

Skipped unless DATABASE_URL is set. Run the seed first:
    python -m src.seed
"""

import os

import pytest

psycopg = pytest.importorskip("psycopg")

DATABASE_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; skipping database tests"
)


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(DATABASE_URL) as connection:
        schema = os.environ.get("DB_SCHEMA")
        if schema:
            with connection.cursor() as cur:
                cur.execute(f'set search_path to "{schema}"')
        yield connection


def one(conn, sql):
    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchone()


def test_tables_populated(conn):
    for table, minimum in [
        ("bookings", 15000),
        ("daily_property_metrics", 720),
        ("daily_channel_metrics", 5000),
        ("daily_campaign_metrics", 700),
        ("daily_market_metrics", 8000),
    ]:
        (count,) = one(conn, f"select count(*) from {table}")
        assert count >= minimum, table


def test_date_coverage(conn):
    _, _, days = one(
        conn, "select min(date), max(date), count(*) from daily_property_metrics"
    )
    assert days >= 720


def test_no_orphaned_foreign_keys(conn):
    (orphans,) = one(conn, """
        select (select count(*) from bookings b
                left join markets m on m.id = b.market_id where m.id is null)
             + (select count(*) from bookings b
                left join channels c on c.id = b.channel_id where c.id is null)
             + (select count(*) from daily_campaign_metrics d
                left join campaigns c on c.id = d.campaign_id where c.id is null)
    """)
    assert orphans == 0


def test_channel_facts_reconcile_with_bookings(conn):
    (mismatched,) = one(conn, """
        select count(*) from (
            select b.booking_date
            from bookings b
            where b.booking_date between
                  (select min(date) from daily_property_metrics)
              and (select max(date) from daily_property_metrics)
            group by b.booking_date
            having count(*) <> (select sum(bookings) from daily_channel_metrics c
                                where c.date = b.booking_date)) x
    """)
    assert mismatched == 0


def test_views_return_rows(conn):
    for view in ["v_monthly_summary", "v_campaign_summary",
                 "v_market_summary", "v_channel_monthly"]:
        (count,) = one(conn, f"select count(*) from {view}")
        assert count > 0, view
