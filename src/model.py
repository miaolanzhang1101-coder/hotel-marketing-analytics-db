"""Demand model: seasonality, growth, channel mix, and campaign lift.

Every coefficient comes from Settings; nothing here is property-specific.
"""

from datetime import date

import numpy as np

from src.settings import Campaign, Settings


class DemandModel:
    def __init__(self, settings: Settings):
        self.s = settings

    def annual_curve(self, d: date) -> float:
        cfg = self.s.seasonality
        doy = d.timetuple().tm_yday
        primary = np.cos(2 * np.pi * (doy - cfg.annual_peak_doy) / 365.25)
        secondary = np.cos(4 * np.pi * (doy - cfg.secondary_offset_doy) / 365.25)
        return 1.0 + cfg.annual_amplitude * primary + cfg.secondary_amplitude * secondary

    def holiday_mult(self, d: date) -> float:
        cfg = self.s.seasonality
        m = 1.0
        for holiday, boost in cfg.holidays.items():
            gap = abs((d - holiday).days)
            if gap <= cfg.holiday_decay_days:
                m = max(m, 1 + (boost - 1) * (1 - gap / (cfg.holiday_decay_days + 1)))
        return m

    def dow_mult(self, d: date) -> float:
        return self.s.seasonality.dow_arrival[d.weekday()]

    def yoy_mult(self, d: date, annual_rate: float) -> float:
        years = (d - self.s.window.start).days / 365.25
        return (1 + annual_rate) ** years

    def channel_share(self, channel_name: str, d: date) -> float:
        channel = self.s.channel_by_name(channel_name)
        t = (d - self.s.window.start).days / self.s.window.days
        return channel.base_share + channel.share_drift * t

    def campaign_lift(self, channel_name: str, d: date) -> tuple[float, Campaign | None]:
        """Demand lift for a channel while one of its flights is live."""
        for campaign in self.s.campaigns:
            if campaign.channel == channel_name and campaign.start <= d <= campaign.end:
                lift = (self.s.behavior.lift_bookings
                        if campaign.objective == "bookings"
                        else self.s.behavior.lift_awareness)
                return lift, campaign
        return 1.0, None
