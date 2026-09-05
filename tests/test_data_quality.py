"""Data quality tests against the committed CSVs in data/.

Fast checks: no database and no regeneration required.
"""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src.settings import load_settings

SETTINGS = load_settings()
DATA = SETTINGS.data_dir


@pytest.fixture(scope="module")
def bookings():
    return pd.read_csv(
        DATA / "bookings.csv",
        parse_dates=["booking_date", "checkin_date", "checkout_date"],
    )


@pytest.fixture(scope="module")
def prop():
    return pd.read_csv(DATA / "daily_property_metrics.csv", parse_dates=["date"])


@pytest.fixture(scope="module")
def chan():
    return pd.read_csv(DATA / "daily_channel_metrics.csv", parse_dates=["date"])


def test_date_coverage(prop):
    assert len(prop) >= 720
    assert prop.date.min().date() == SETTINGS.window.start
    assert prop.date.max().date() == SETTINGS.window.end
    assert prop.date.is_unique
    assert (prop.date.diff().dropna().dt.days == 1).all()


def test_booking_invariants(bookings):
    assert bookings.id.is_unique
    assert bookings.status.isin(["confirmed", "cancelled"]).all()
    assert (bookings.checkout_date == bookings.checkin_date
            + pd.to_timedelta(bookings.nights, unit="D")).all()
    assert (bookings.room_revenue - bookings.adr * bookings.nights).abs().max() < 0.02
    assert (bookings.lead_time_days >= 0).all()
    assert bookings.nights.between(1, 30).all()


def test_foreign_keys(bookings):
    market_ids = {m.id for m in SETTINGS.markets}
    channel_ids = {c.id for c in SETTINGS.channels}
    campaign_ids = {c.id for c in SETTINGS.campaigns}
    assert set(bookings.market_id).issubset(market_ids)
    assert set(bookings.channel_id).issubset(channel_ids)
    assert set(bookings.campaign_id.dropna().astype(int)).issubset(campaign_ids)


def test_occupancy_bounds(prop):
    assert (prop.rooms_occupied <= SETTINGS.property.rooms).all()
    assert prop.occupancy_rate.between(0, 1).all()
    assert (prop.revpar <= prop.adr + 0.01).all()


def test_channel_facts_reconcile_with_bookings(bookings, chan):
    in_window = bookings[
        (bookings.booking_date >= pd.Timestamp(SETTINGS.window.start))
        & (bookings.booking_date <= pd.Timestamp(SETTINGS.window.end))
    ]
    by_day = in_window.groupby("booking_date").size()
    chan_by_day = chan.groupby("date").bookings.sum()
    joined = pd.concat([by_day, chan_by_day], axis=1).fillna(0)
    assert (joined.iloc[:, 0] == joined.iloc[:, 1]).all()


def test_seasonality_direction(prop):
    monthly = prop.set_index("date").occupancy_rate.resample("ME").mean()
    july = monthly[monthly.index.month == 7].mean()
    january = monthly[monthly.index.month == 1].mean()
    assert july > january * 1.5


def test_year_over_year_growth(prop):
    year1 = prop[prop.date < "2025-09-01"].room_revenue.sum()
    year2 = prop[prop.date >= "2025-09-01"].room_revenue.sum()
    assert year2 > year1


def test_campaign_flights_within_budget_tolerance():
    camp = pd.read_csv(DATA / "daily_campaign_metrics.csv")
    spend = camp.groupby("campaign_id").spend.sum()
    for campaign in SETTINGS.campaigns:
        if not SETTINGS.channel_by_name(campaign.channel).cpc:
            continue  # no media spend on this channel
        assert abs(spend[campaign.id] - campaign.budget) / campaign.budget < 0.15


@pytest.mark.slow
def test_generation_is_deterministic(tmp_path):
    """Regenerating with the same config reproduces the committed CSVs exactly."""
    from src.generate import run

    run(SETTINGS, out_dir=tmp_path)
    for name in ["bookings.csv", "daily_property_metrics.csv"]:
        assert (tmp_path / name).read_bytes() == (DATA / name).read_bytes()
