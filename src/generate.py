"""Entry point: generate the full dataset into the configured data directory.

Deterministic for a given config and seed: re-running produces identical
output.

Usage:
    python -m src.generate [--config PATH] [--out-dir PATH] [--seed N]
                           [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""

import argparse
import dataclasses
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.aggregates import build_aggregates
from src.bookings import generate_bookings
from src.settings import Settings, load_settings


def write_dimensions(settings: Settings, out_dir: Path) -> None:
    pd.DataFrame(
        [(m.id, m.name, m.region, m.country, m.summer_idx, m.winter_idx)
         for m in settings.markets],
        columns=["id", "name", "region", "country", "summer_idx", "winter_idx"],
    ).to_csv(out_dir / "markets.csv", index=False)

    pd.DataFrame(
        [(c.id, c.name, c.is_paid, c.is_website_channel) for c in settings.channels],
        columns=["id", "name", "is_paid", "is_website_channel"],
    ).to_csv(out_dir / "channels.csv", index=False)

    pd.DataFrame(
        [(c.id, c.name, settings.channel_by_name(c.channel).id, c.objective,
          c.start, c.end, c.budget) for c in settings.campaigns],
        columns=["id", "name", "channel_id", "objective", "start_date",
                 "end_date", "total_budget"],
    ).to_csv(out_dir / "campaigns.csv", index=False)


def run(settings: Settings, out_dir: Path | None = None) -> None:
    out_dir = out_dir or settings.data_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(settings.random_seed)

    print("Generating bookings...")
    bookings = generate_bookings(rng, settings)
    print(f"  {len(bookings):,} bookings "
          f"({bookings.booking_date.min()} .. {bookings.booking_date.max()})")

    print("Building daily aggregates...")
    prop, chan, camp, mkt = build_aggregates(bookings, rng, settings)

    write_dimensions(settings, out_dir)
    bookings["campaign_id"] = bookings["campaign_id"].astype("Int64")
    bookings.to_csv(out_dir / "bookings.csv", index=False)
    prop.to_csv(out_dir / "daily_property_metrics.csv", index=False)
    chan.to_csv(out_dir / "daily_channel_metrics.csv", index=False)
    camp.to_csv(out_dir / "daily_campaign_metrics.csv", index=False)
    mkt.to_csv(out_dir / "daily_market_metrics.csv", index=False)

    print(f"  property days : {len(prop)}")
    print(f"  channel rows  : {len(chan):,}")
    print(f"  campaign rows : {len(camp):,}")
    print(f"  market rows   : {len(mkt):,}")
    print(f"  avg occupancy : {prop.occupancy_rate.mean():.1%}")
    print(f"  total revenue : ${prop.room_revenue.sum():,.0f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("--out-dir", type=Path, help="output directory")
    parser.add_argument("--seed", type=int, help="override random seed")
    parser.add_argument("--start", type=date.fromisoformat, help="window start")
    parser.add_argument("--end", type=date.fromisoformat, help="window end")
    args = parser.parse_args()

    settings = load_settings(args.config)
    if args.seed is not None:
        settings = dataclasses.replace(settings, random_seed=args.seed)
    if args.start or args.end:
        window = dataclasses.replace(
            settings.window,
            start=args.start or settings.window.start,
            end=args.end or settings.window.end,
        )
        settings = dataclasses.replace(settings, window=window)

    run(settings, out_dir=args.out_dir)


if __name__ == "__main__":
    main()
