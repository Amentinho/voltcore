"""
VOLTCORE Oracle v0.1
=====================
Simulates Chainlink price feed for REE PVPC (Spain's official energy spot price).
In production: reads from Solana on-chain Chainlink feed every hour.

Real endpoint (production):
  Chainlink Solana devnet → REE PVPC feed
  https://docs.chain.link/data-feeds/price-feeds/addresses?network=solana

Mock behavior:
  - Base price: €0.15/kWh (REE average 2024)
  - Hourly variance: ±8% (realistic PVPC volatility)
  - Peak hours (9-21h): +12% premium
  - Night hours (0-8h): -15% discount
  - Weekend: -5% average
"""

import random
import math
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass


# ─────────────────────────────────────────────
# CONSTANTS — REE PVPC 2024 averages
# ─────────────────────────────────────────────

BASE_PRICE_EUR_KWH   = 0.1487   # REE PVPC annual average 2024
PEAK_PREMIUM         = 0.12     # +12% during peak hours
NIGHT_DISCOUNT       = 0.15     # -15% during valley hours
WEEKEND_DISCOUNT     = 0.05     # -5% on weekends
MAX_VOLATILITY       = 0.08     # ±8% random variance

# Spain REE peak/valley hours
PEAK_HOURS    = range(9, 22)    # 9am - 9pm
VALLEY_HOURS  = range(0, 8)     # midnight - 8am


# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────

@dataclass
class PriceTick:
    timestamp: datetime
    price_eur_kwh: float
    period_type: str        # PEAK | VALLEY | FLAT
    source: str             # MOCK | CHAINLINK


@dataclass
class MonthlyPriceStats:
    period: str
    avg_price: float
    min_price: float
    max_price: float
    peak_avg: float
    valley_avg: float
    ticks: int


# ─────────────────────────────────────────────
# ORACLE ENGINE
# ─────────────────────────────────────────────

class REEOracle:
    """
    Simulates Chainlink → REE PVPC price feed.
    
    In production this class is replaced by a Solana on-chain
    Chainlink price feed reader using solana-py.
    """

    def __init__(self, seed: Optional[int] = None):
        self.seed = seed
        self._cache: dict[str, PriceTick] = {}
        print("  [Oracle] REE PVPC price feed initialized")
        print(f"  [Oracle] Base price: €{BASE_PRICE_EUR_KWH:.4f}/kWh")
        print(f"  [Oracle] Mode: MOCK (replace with Chainlink on devnet)")

    def _period_type(self, dt: datetime) -> str:
        if dt.hour in PEAK_HOURS:
            return "PEAK"
        elif dt.hour in VALLEY_HOURS:
            return "VALLEY"
        return "FLAT"

    def _calculate_price(self, dt: datetime) -> float:
        """Calculate realistic REE price for a given datetime."""
        # Deterministic seed per hour for reproducibility
        if self.seed:
            random.seed(self.seed + dt.hour + dt.day * 24 + dt.month * 720)

        price = BASE_PRICE_EUR_KWH

        # Time-of-day adjustment
        period = self._period_type(dt)
        if period == "PEAK":
            price *= (1 + PEAK_PREMIUM)
        elif period == "VALLEY":
            price *= (1 - NIGHT_DISCOUNT)

        # Weekend discount
        if dt.weekday() >= 5:
            price *= (1 - WEEKEND_DISCOUNT)

        # Seasonal adjustment (Spain: expensive winter/summer, cheap spring)
        month = dt.month
        if month in [12, 1, 2]:     # Winter
            price *= 1.10
        elif month in [6, 7, 8]:    # Summer
            price *= 1.08
        elif month in [3, 4, 5]:    # Spring (cheapest)
            price *= 0.92

        # Random volatility
        volatility = random.uniform(-MAX_VOLATILITY, MAX_VOLATILITY)
        price *= (1 + volatility)

        return round(max(0.05, price), 4)  # floor at €0.05

    def get_current_price(self) -> PriceTick:
        """Get current REE spot price."""
        now = datetime.now()
        price = self._calculate_price(now)
        tick = PriceTick(
            timestamp=now,
            price_eur_kwh=price,
            period_type=self._period_type(now),
            source="MOCK"
        )
        print(f"  [Oracle] Current price: €{price:.4f}/kWh [{tick.period_type}] @ {now.strftime('%H:%M')}")
        return tick

    def get_price_at(self, dt: datetime) -> PriceTick:
        """Get REE price at a specific datetime."""
        cache_key = dt.strftime("%Y%m%d%H")
        if cache_key in self._cache:
            return self._cache[cache_key]

        price = self._calculate_price(dt)
        tick = PriceTick(
            timestamp=dt,
            price_eur_kwh=price,
            period_type=self._period_type(dt),
            source="MOCK"
        )
        self._cache[cache_key] = tick
        return tick

    def get_monthly_average(self, year: int, month: int) -> MonthlyPriceStats:
        """
        Calculate average REE price for a full month.
        Used by settlement engine for monthly excess energy valuation.
        """
        ticks = []
        peak_ticks = []
        valley_ticks = []

        # Sample every hour of the month
        dt = datetime(year, month, 1)
        while dt.month == month:
            tick = self.get_price_at(dt)
            ticks.append(tick.price_eur_kwh)
            if tick.period_type == "PEAK":
                peak_ticks.append(tick.price_eur_kwh)
            elif tick.period_type == "VALLEY":
                valley_ticks.append(tick.price_eur_kwh)
            dt += timedelta(hours=1)

        stats = MonthlyPriceStats(
            period=f"{year}-{month:02d}",
            avg_price=round(sum(ticks) / len(ticks), 4),
            min_price=round(min(ticks), 4),
            max_price=round(max(ticks), 4),
            peak_avg=round(sum(peak_ticks) / len(peak_ticks), 4) if peak_ticks else 0,
            valley_avg=round(sum(valley_ticks) / len(valley_ticks), 4) if valley_ticks else 0,
            ticks=len(ticks)
        )
        return stats

    def get_hourly_profile(self, year: int, month: int, day: int) -> list[PriceTick]:
        """Get full 24-hour price profile for a given day."""
        ticks = []
        for hour in range(24):
            dt = datetime(year, month, day, hour)
            ticks.append(self.get_price_at(dt))
        return ticks


# ─────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────

def demo():
    print("\n" + "="*60)
    print("  VOLTCORE ORACLE DEMO")
    print("="*60)

    oracle = REEOracle(seed=42)

    print("\n  📡 CURRENT PRICE")
    tick = oracle.get_current_price()

    print("\n  📅 MONTHLY AVERAGES — 2025")
    print(f"\n  {'Month':<12} {'Avg':>8} {'Min':>8} {'Max':>8} {'Peak':>8} {'Valley':>8}")
    print(f"  {'-'*56}")
    for month in range(1, 13):
        stats = oracle.get_monthly_average(2025, month)
        print(f"  {stats.period:<12} "
              f"€{stats.avg_price:>6.4f} "
              f"€{stats.min_price:>6.4f} "
              f"€{stats.max_price:>6.4f} "
              f"€{stats.peak_avg:>6.4f} "
              f"€{stats.valley_avg:>6.4f}")

    print("\n  🕐 24-HOUR PRICE PROFILE — 2025-06-15 (Sunday)")
    print(f"\n  {'Hour':<8} {'Price':>10} {'Period':<8}")
    print(f"  {'-'*30}")
    profile = oracle.get_hourly_profile(2025, 6, 15)
    for tick in profile:
        bar = "█" * int(tick.price_eur_kwh / 0.01)
        print(f"  {tick.timestamp.strftime('%H:00'):<8} "
              f"€{tick.price_eur_kwh:>8.4f} "
              f"[{tick.period_type:<6}] {bar}")


if __name__ == "__main__":
    demo()