"""Daily fact tables, all derived from the bookings table.

Deriving aggregates from row-level bookings (rather than generating them
independently) guarantees that property KPIs, channel funnels, campaign
metrics, and market splits reconcile with each other.
"""

from datetime import timedelta

import numpy as np
import pandas as pd

from src.bookings import SUMMER_MONTHS, WINTER_MONTHS
from src.model import DemandModel
from src.settings import Settings


def build_aggregates(bookings: pd.DataFrame, rng: np.random.Generator,
                     settings: Settings):
    s = settings
    model = DemandModel(s)
    days = pd.date_range(s.window.start, s.window.end, freq="D").date
    confirmed = bookings[bookings.status == "confirmed"]
    made = bookings[(bookings.booking_date >= s.window.start)
                    & (bookings.booking_date <= s.window.end)]

    prop = _property_daily(confirmed, made, days, s)
    chan = _channel_daily(made, days, rng, model, s)
    camp = _campaign_daily(made, chan, rng, s)
    mkt = _market_daily(made, chan, days, rng, s)
    return prop, chan, camp, mkt


def _property_daily(confirmed, made, days, s: Settings) -> pd.DataFrame:
    """Occupancy/ADR/RevPAR from expanded stay-nights; pace from booking dates."""
    stay = confirmed.loc[:, ["checkin_date", "nights", "adr"]]
    nights_idx = stay.index.repeat(stay["nights"])
    occupied = pd.DataFrame({
        "date": [
            checkin + timedelta(days=k)
            for checkin, n in zip(stay["checkin_date"], stay["nights"])
            for k in range(n)
        ],
        "adr": stay.loc[nights_idx, "adr"].values,
    })
    occupied = occupied[(occupied.date >= s.window.start)
                        & (occupied.date <= s.window.end)]
    by_day = occupied.groupby("date").agg(rooms_occupied=("adr", "size"),
                                          adr=("adr", "mean"))
    by_day["rooms_occupied"] = by_day["rooms_occupied"].clip(upper=s.property.rooms)

    pace = made.groupby("booking_date").agg(
        bookings_made=("id", "size"),
        cancellations=("status", lambda col: int((col == "cancelled").sum())),
    )

    prop = (pd.DataFrame({"date": days}).set_index("date")
            .join(by_day).join(pace).fillna(0))
    prop["rooms_available"] = s.property.rooms
    prop["occupancy_rate"] = (prop.rooms_occupied / s.property.rooms).round(4)
    prop["adr"] = prop["adr"].round(2)
    prop["room_revenue"] = (prop.rooms_occupied * prop.adr).round(2)
    prop["revpar"] = (prop.room_revenue / s.property.rooms).round(2)
    prop = prop.reset_index()[[
        "date", "rooms_available", "rooms_occupied", "occupancy_rate", "adr",
        "revpar", "room_revenue", "bookings_made", "cancellations",
    ]]
    int_cols = ["rooms_occupied", "bookings_made", "cancellations"]
    prop[int_cols] = prop[int_cols].astype(int)
    return prop


def _channel_daily(made, days, rng, model: DemandModel, s: Settings) -> pd.DataFrame:
    """Bookings/revenue by channel with a session funnel above them.

    Sessions are inverted from bookings via per-channel conversion rates, plus
    a baseline of non-converting traffic. Media columns are filled in by
    _campaign_daily so the two tables reconcile.
    """
    grouped = made.groupby(["booking_date", "channel_id"]).agg(
        bookings=("id", "size"), revenue=("room_revenue", "sum")).reset_index()
    lookup = {(r.booking_date, r.channel_id): (r.bookings, r.revenue)
              for r in grouped.itertuples()}

    rows = []
    for d in days:
        season = model.annual_curve(d) * model.yoy_mult(d, s.property.yoy_demand_growth)
        for channel in s.channels:
            b, rev = lookup.get((d, channel.id), (0, 0.0))
            if channel.is_website_channel:
                converted = b / channel.conversion_rate if b else 0
                noise = rng.normal(1, s.funnel.session_noise_sd)
                baseline = (s.funnel.baseline_site_sessions * season
                            * model.channel_share(channel.name, d))
                sessions = int(max(0, converted * noise + baseline))
                users = int(sessions * rng.uniform(s.funnel.users_ratio_min,
                                                   s.funnel.users_ratio_max))
            else:
                sessions, users = 0, 0
            rows.append((d, channel.id, sessions, users, b, round(rev, 2),
                         0.0, 0, 0))

    return pd.DataFrame(rows, columns=[
        "date", "channel_id", "sessions", "users", "bookings", "revenue",
        "spend", "impressions", "clicks",
    ])


def _campaign_daily(made, chan, rng, s: Settings) -> pd.DataFrame:
    """Daily flight metrics per campaign; media cost rolls up into channels."""
    attributed = made[made.campaign_id.notna()].groupby(
        ["booking_date", "campaign_id"]).agg(
        bookings=("id", "size"), revenue=("room_revenue", "sum")).reset_index()
    lookup = {(r.booking_date, int(r.campaign_id)): (r.bookings, r.revenue)
              for r in attributed.itertuples()}

    rows = []
    for campaign in s.campaigns:
        channel = s.channel_by_name(campaign.channel)
        flight = pd.date_range(max(campaign.start, s.window.start),
                               min(campaign.end, s.window.end)).date
        daily_budget = campaign.budget / ((campaign.end - campaign.start).days + 1)
        for d in flight:
            if channel.cpc:  # media-buying channel
                spend = round(max(0, rng.normal(daily_budget,
                                                daily_budget * s.media.spend_noise_sd)), 2)
                clicks = int(spend / channel.cpc)
            else:  # email: no media cost, clicks come from sends
                spend = 0.0
                clicks = int(rng.normal(s.media.email_clicks_mean,
                                        s.media.email_clicks_sd))
            impressions = int(clicks / channel.ctr) if channel.ctr else 0
            b, rev = lookup.get((d, campaign.id), (0, 0.0))
            sessions = int(clicks * rng.uniform(s.media.campaign_session_ratio_min,
                                                s.media.campaign_session_ratio_max))
            rows.append((d, campaign.id, spend, impressions, clicks, sessions,
                         b, round(rev, 2)))

            mask = (chan.date == d) & (chan.channel_id == channel.id)
            chan.loc[mask, "spend"] += spend
            chan.loc[mask, "impressions"] += impressions
            chan.loc[mask, "clicks"] += clicks

    chan["spend"] = chan["spend"].round(2)
    return pd.DataFrame(rows, columns=[
        "date", "campaign_id", "spend", "impressions", "clicks", "sessions",
        "bookings", "revenue",
    ])


def _market_daily(made, chan, days, rng, s: Settings) -> pd.DataFrame:
    """Feeder-market bookings/revenue plus sessions split by seasonal mix."""
    by_market = made.groupby(["booking_date", "market_id"]).agg(
        bookings=("id", "size"), revenue=("room_revenue", "sum")).reset_index()
    by_market.columns = ["date", "market_id", "bookings", "revenue"]

    total_sessions = chan.groupby("date")["sessions"].sum()
    base = pd.Series({m.id: m.weight for m in s.markets})

    rows = []
    for d in days:
        sessions = total_sessions.get(d, 0)
        w = base.copy()
        for market in s.markets:
            if d.month in SUMMER_MONTHS:
                w[market.id] *= market.summer_idx
            elif d.month in WINTER_MONTHS:
                w[market.id] *= market.winter_idx
        w /= w.sum()
        for market in s.markets:
            rows.append((d, market.id,
                         int(sessions * w[market.id]
                             * rng.normal(1, s.funnel.session_noise_sd * 0.75))))

    mkt = pd.DataFrame(rows, columns=["date", "market_id", "sessions"])
    mkt = mkt.merge(by_market, on=["date", "market_id"], how="left").fillna(0)
    mkt["bookings"] = mkt["bookings"].astype(int)
    mkt["revenue"] = mkt["revenue"].round(2)
    return mkt
