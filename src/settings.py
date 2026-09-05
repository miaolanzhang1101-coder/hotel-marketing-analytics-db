"""Typed configuration loading.

All business and environment parameters live in config.yaml; secrets live in
.env (loaded here if present). Paths in the config are resolved relative to
the project root. Environment overrides:

    CONFIG_PATH   alternate config file
    DATA_DIR      alternate data directory
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Window:
    start: date
    end: date
    warmup_days: int
    lookahead_days: int

    @property
    def gen_start(self) -> date:
        return self.start - timedelta(days=self.warmup_days)

    @property
    def gen_end(self) -> date:
        return self.end + timedelta(days=self.lookahead_days)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class Property:
    rooms: int
    base_arrivals_per_day: float
    base_adr: float
    yoy_demand_growth: float
    yoy_adr_growth: float
    cancel_rate: float


@dataclass(frozen=True)
class Seasonality:
    annual_amplitude: float
    annual_peak_doy: int
    secondary_amplitude: float
    secondary_offset_doy: int
    holiday_decay_days: int
    dow_arrival: list[float]
    holidays: dict[date, float]


@dataclass(frozen=True)
class Behavior:
    nights_geometric_p: float
    max_nights: int
    weekend_max_nights: int
    max_guests: int
    lead_time_summer_mean: float
    lead_time_other_mean: float
    lead_time_ota_factor: float
    lead_time_cap: int
    adr_stddev: float
    adr_min: float
    adr_max: float
    weekend_adr_factor: float
    attribution_rate: float
    lift_bookings: float
    lift_awareness: float


@dataclass(frozen=True)
class Funnel:
    baseline_site_sessions: float
    session_noise_sd: float
    users_ratio_min: float
    users_ratio_max: float


@dataclass(frozen=True)
class Media:
    spend_noise_sd: float
    email_clicks_mean: float
    email_clicks_sd: float
    campaign_session_ratio_min: float
    campaign_session_ratio_max: float


@dataclass(frozen=True)
class Channel:
    id: int
    name: str
    is_paid: bool
    is_website_channel: bool
    conversion_rate: float | None
    base_share: float
    share_drift: float = 0.0
    adr_factor: float = 1.0
    cpc: float | None = None
    ctr: float | None = None


@dataclass(frozen=True)
class Market:
    id: int
    name: str
    region: str
    country: str
    weight: float
    summer_idx: float
    winter_idx: float


@dataclass(frozen=True)
class Campaign:
    id: int
    name: str
    channel: str
    objective: str
    start: date
    end: date
    budget: float
    market_boost: dict | None = None


@dataclass(frozen=True)
class Settings:
    random_seed: int
    window: Window
    property: Property
    seasonality: Seasonality
    behavior: Behavior
    funnel: Funnel
    media: Media
    channels: list[Channel]
    markets: list[Market]
    campaigns: list[Campaign]
    data_dir: Path
    schema_path: Path
    load_order: list[tuple[str, str]] = field(default_factory=list)

    def channel_by_name(self, name: str) -> Channel:
        return next(c for c in self.channels if c.name == name)


def load_settings(config_path: str | Path | None = None) -> Settings:
    path = Path(config_path or os.getenv("CONFIG_PATH", PROJECT_ROOT / "config.yaml"))
    raw = yaml.safe_load(path.read_text())

    data_dir = Path(os.getenv("DATA_DIR", raw["paths"]["data_dir"]))
    if not data_dir.is_absolute():
        data_dir = PROJECT_ROOT / data_dir
    schema_path = Path(raw["paths"]["schema_file"])
    if not schema_path.is_absolute():
        schema_path = PROJECT_ROOT / schema_path

    return Settings(
        random_seed=int(raw["random_seed"]),
        window=Window(**raw["window"]),
        property=Property(**raw["property"]),
        seasonality=Seasonality(**raw["seasonality"]),
        behavior=Behavior(**raw["behavior"]),
        funnel=Funnel(**raw["funnel"]),
        media=Media(**raw["media"]),
        channels=[Channel(**c) for c in raw["channels"]],
        markets=[Market(**m) for m in raw["markets"]],
        campaigns=[Campaign(**c) for c in raw["campaigns"]],
        data_dir=data_dir,
        schema_path=schema_path,
        load_order=[(t["table"], t["file"]) for t in raw["load_order"]],
    )
