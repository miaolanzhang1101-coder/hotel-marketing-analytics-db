"""Row-level booking generation.

Demand is modeled per arrival date; booking dates are back-computed from a
lead-time distribution so occupancy and booking-pace curves stay consistent.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.model import DemandModel
from src.settings import Settings

SUMMER_MONTHS = (6, 7, 8)
WINTER_MONTHS = (12, 1, 2)
WEEKEND_ARRIVAL_DAYS = (4, 5)  # Friday, Saturday

COLUMNS = [
    "id", "booking_date", "checkin_date", "checkout_date", "nights",
    "rooms", "guests", "market_id", "channel_id", "campaign_id",
    "room_revenue", "adr", "lead_time_days", "status",
]


def generate_bookings(
    rng: np.random.Generator,
    settings: Settings,
    start: date | None = None,
    end: date | None = None,
) -> pd.DataFrame:
    """Generate bookings with arrivals in [start, end] (defaults from config)."""
    s = settings
    model = DemandModel(s)
    start = start or s.window.gen_start
    end = end or s.window.gen_end

    market_weights = np.array([m.weight for m in s.markets], dtype=float)
    rows: list[tuple] = []
    booking_id = 1

    d = start
    while d <= end:
        season = model.annual_curve(d) * model.holiday_mult(d) * model.dow_mult(d)
        demand = (s.property.base_arrivals_per_day * season
                  * model.yoy_mult(d, s.property.yoy_demand_growth))

        for channel in s.channels:
            lift, campaign = model.campaign_lift(channel.name, d)
            expected = demand * model.channel_share(channel.name, d) * lift
            n = rng.poisson(expected)
            if n == 0:
                continue

            weights = _market_weights(market_weights, s, d.month, campaign)
            market_idx = rng.choice(len(s.markets), size=n, p=weights)

            nights = np.clip(rng.geometric(s.behavior.nights_geometric_p, size=n),
                             1, s.behavior.max_nights)
            if d.weekday() in WEEKEND_ARRIVAL_DAYS:
                nights = np.clip(nights, 1, s.behavior.weekend_max_nights)

            leads = _lead_times(rng, n, d.month, channel.name, s)
            adrs = _adrs(rng, n, d, channel.adr_factor, model, s)
            cancelled = rng.random(n) < s.property.cancel_rate
            attributed = (rng.random(n) < s.behavior.attribution_rate) if campaign \
                else np.zeros(n, dtype=bool)

            for i in range(n):
                stay_nights = int(nights[i])
                rows.append((
                    booking_id,
                    d - timedelta(days=int(leads[i])),
                    d,
                    d + timedelta(days=stay_nights),
                    stay_nights,
                    1,
                    int(rng.integers(1, s.behavior.max_guests + 1)),
                    s.markets[market_idx[i]].id,
                    channel.id,
                    campaign.id if (campaign and attributed[i]) else None,
                    round(float(adrs[i]) * stay_nights, 2),
                    float(adrs[i]),
                    int(leads[i]),
                    "cancelled" if cancelled[i] else "confirmed",
                ))
                booking_id += 1
        d += timedelta(days=1)

    df = pd.DataFrame(rows, columns=COLUMNS)
    touches_window = ((df["booking_date"] <= s.window.end)
                      & (df["checkout_date"] >= s.window.start))
    return df[touches_window].reset_index(drop=True)


def _market_weights(base: np.ndarray, s: Settings, month: int, campaign) -> np.ndarray:
    """Feeder-market mix adjusted for season and geo-targeted flights."""
    w = base.copy()
    for i, market in enumerate(s.markets):
        if month in SUMMER_MONTHS:
            w[i] *= market.summer_idx
        elif month in WINTER_MONTHS:
            w[i] *= market.winter_idx
    if campaign and campaign.market_boost:
        boost = campaign.market_boost
        idx = next(i for i, m in enumerate(s.markets) if m.id == boost["market_id"])
        w[idx] *= boost["factor"]
    return w / w.sum()


def _lead_times(rng, n: int, month: int, channel_name: str, s: Settings) -> np.ndarray:
    """Gamma-distributed lead times: longer for summer stays, shorter for OTA."""
    b = s.behavior
    mean = b.lead_time_summer_mean if month in (5, *SUMMER_MONTHS) else b.lead_time_other_mean
    if channel_name == "OTA":
        mean *= b.lead_time_ota_factor
    return np.clip(rng.gamma(2.0, mean / 2.0, size=n), 0, b.lead_time_cap).astype(int)


def _adrs(rng, n: int, d: date, channel_factor: float,
          model: DemandModel, s: Settings) -> np.ndarray:
    """Rates carry seasonal, weekend, channel, and year-over-year effects."""
    b = s.behavior
    seasonal = 1 + 0.30 * (model.annual_curve(d) - 1) / s.seasonality.annual_amplitude
    base = s.property.base_adr * seasonal * model.yoy_mult(d, s.property.yoy_adr_growth)
    if d.weekday() in WEEKEND_ARRIVAL_DAYS:
        base *= b.weekend_adr_factor
    base *= channel_factor
    return np.clip(np.round(rng.normal(base, b.adr_stddev, size=n), 2),
                   b.adr_min, b.adr_max)
