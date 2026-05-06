"""
VOLTCORE AI Simulation Engine v1.0
====================================
Generates realistic real-time energy consumption and production data
for both ON-GRID and OFF-GRID communities.

Uses:
- Physics-based solar production model (PVGIS data)
- Statistical consumption patterns (Spanish household data INE 2024)
- AI anomaly injection for realistic variance
- Real-time settlement loop

Run: python3 agent/simulate.py
"""

import time
import random
import math
import json
import threading
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Optional
from pathlib import Path

# Import our existing modules
from oracle import REEOracle
from settlement import (
    SettlementEngine, Community, Member,
    CommunityMode, SettlementInput
)

# ─────────────────────────────────────────────
# CONSTANTS — Spanish household data (INE 2024)
# ─────────────────────────────────────────────

AVG_MONTHLY_KWH_SPAIN   = 300     # kWh/month average Spanish household
PEAK_HOURS              = range(9, 22)
MORNING_HOURS           = range(7, 13)
EVENING_HOURS           = range(18, 23)
NIGHT_HOURS             = range(0, 7)

# Seasonal production multipliers for Spain
SEASONAL_FACTOR = {
    1: 0.65, 2: 0.72, 3: 0.88, 4: 1.00,
    5: 1.12, 6: 1.20, 7: 1.25, 8: 1.18,
    9: 1.05, 10: 0.90, 11: 0.72, 12: 0.60
}

# ─────────────────────────────────────────────
# SOLAR PRODUCTION SIMULATOR
# ─────────────────────────────────────────────

class SolarSimulator:
    """
    Physics-based solar production with realistic variance.
    Based on PVGIS data for Barcelona and Extremadura.
    """

    LOCATIONS = {
        "barcelona": {
            "lat": 41.38,
            "peak_sun_hours": {
                1: 3.2, 2: 4.1, 3: 5.3, 4: 6.2,
                5: 7.1, 6: 7.8, 7: 7.9, 8: 7.2,
                9: 6.0, 10: 4.8, 11: 3.5, 12: 3.0
            },
            "cloud_probability": 0.35,
        },
        "extremadura": {
            "lat": 39.47,
            "peak_sun_hours": {
                1: 3.8, 2: 4.7, 3: 6.0, 4: 7.0,
                5: 8.0, 6: 8.7, 7: 9.0, 8: 8.3,
                9: 6.8, 10: 5.4, 11: 4.0, 12: 3.5
            },
            "cloud_probability": 0.25,
        }
    }

    def __init__(self, location: str, panel_kwp: float, seed: int = None):
        self.location   = self.LOCATIONS[location]
        self.panel_kwp  = panel_kwp
        self.efficiency = 0.82  # System efficiency
        self._cloud_factor = 1.0
        self._cloud_duration = 0
        if seed:
            random.seed(seed)

    def _update_clouds(self):
        """Simulate cloud cover with realistic persistence."""
        if self._cloud_duration > 0:
            self._cloud_duration -= 1
        else:
            if random.random() < self.location["cloud_probability"] / 24:
                self._cloud_factor  = random.uniform(0.2, 0.7)
                self._cloud_duration = random.randint(1, 4)
            else:
                self._cloud_factor = random.uniform(0.90, 1.05)

    def get_production_kwh(self, dt: datetime) -> float:
        """Get production for a 15-minute interval."""
        hour  = dt.hour + dt.minute / 60
        month = dt.month

        # Solar elevation angle (simplified)
        solar_noon = 13.5
        if hour < 6 or hour > 21:
            return 0.0

        # Bell curve around solar noon
        sigma = 3.8
        sun_factor = math.exp(-0.5 * ((hour - solar_noon) / sigma) ** 2)

        # Daily production base
        psh   = self.location["peak_sun_hours"][month]
        daily = self.panel_kwp * psh * self.efficiency

        # 15-min interval factor
        interval_kwh = daily * sun_factor / (
            sum(math.exp(-0.5 * ((h - solar_noon) / sigma) ** 2)
                for h in [6 + i*0.25 for i in range(60)])
        )

        # Apply cloud factor and random noise
        self._update_clouds()
        noise    = random.gauss(1.0, 0.04)  # ±4% gaussian noise
        result   = interval_kwh * self._cloud_factor * noise
        return max(0.0, round(result, 4))


# ─────────────────────────────────────────────
# CONSUMPTION SIMULATOR
# ─────────────────────────────────────────────

class ConsumptionSimulator:
    """
    Realistic Spanish household consumption patterns.
    Based on REE and INE 2024 data.
    """

    # Consumption profile by hour (relative weights, INE data)
    HOURLY_PROFILE = {
        0: 0.30, 1: 0.25, 2: 0.22, 3: 0.20, 4: 0.20, 5: 0.22,
        6: 0.35, 7: 0.65, 8: 0.80, 9: 0.75, 10: 0.70, 11: 0.72,
        12: 0.85, 13: 0.90, 14: 0.85, 15: 0.70, 16: 0.68, 17: 0.75,
        18: 0.95, 19: 1.00, 20: 1.00, 21: 0.95, 22: 0.80, 23: 0.55
    }

    def __init__(self, n_households: int, avg_monthly_kwh: float = AVG_MONTHLY_KWH_SPAIN):
        self.n_households    = n_households
        self.monthly_kwh     = avg_monthly_kwh * n_households
        self.daily_kwh       = self.monthly_kwh / 30
        self._appliance_spikes = []

    def _maybe_spike(self, hour: int) -> float:
        """Simulate occasional appliance spikes (washing machine, oven, AC)."""
        spike = 0.0
        # Morning: washing machine / coffee
        if hour in range(7, 10) and random.random() < 0.15:
            spike += random.uniform(0.3, 0.8)
        # Midday: cooking
        if hour in range(13, 15) and random.random() < 0.25:
            spike += random.uniform(0.5, 1.2)
        # Evening: cooking + TV + AC/heating
        if hour in range(19, 22) and random.random() < 0.30:
            spike += random.uniform(0.4, 1.0)
        # AC in summer (June-September)
        month = datetime.now().month
        if month in [6, 7, 8, 9] and hour in range(14, 20):
            if random.random() < 0.40:
                spike += random.uniform(0.5, 1.5) * (self.n_households / 4)
        return spike

    def get_consumption_kwh(self, dt: datetime) -> float:
        """Get consumption for a 15-minute interval."""
        hour   = dt.hour
        weight = self.HOURLY_PROFILE.get(hour, 0.5)

        # Base consumption for this interval (15 min = 1/96 of day)
        base   = self.daily_kwh * weight / sum(self.HOURLY_PROFILE.values()) * len(self.HOURLY_PROFILE)
        base   = base / 4  # 15-minute interval

        # Add noise ±15%
        noise  = random.gauss(1.0, 0.08)
        base   *= noise

        # Add appliance spikes
        base   += self._maybe_spike(hour)

        return max(0.1, round(base, 4))


# ─────────────────────────────────────────────
# BATTERY SIMULATOR (Off-Grid)
# ─────────────────────────────────────────────

class BatterySimulator:
    """LFP Battery simulation with realistic charge/discharge curves."""

    def __init__(self, capacity_kwh: float, initial_soc: float = 0.75):
        self.capacity       = capacity_kwh
        self.soc            = initial_soc
        self.charge_eff     = 0.97   # LFP charge efficiency
        self.discharge_eff  = 0.97   # LFP discharge efficiency
        self.max_c_rate     = 0.5    # 0.5C max charge rate
        self.min_soc        = 0.10   # 10% minimum SOC
        self.max_soc        = 0.95   # 95% maximum SOC

    @property
    def soc_pct(self) -> float:
        return round(self.soc * 100, 1)

    @property
    def energy_available_kwh(self) -> float:
        return (self.soc - self.min_soc) * self.capacity * self.discharge_eff

    def charge(self, available_kwh: float) -> float:
        """Charge battery with available surplus. Returns actual stored kWh."""
        max_charge = min(
            self.capacity * self.max_c_rate / 4,  # C-rate limit per 15min
            (self.max_soc - self.soc) * self.capacity  # Headroom
        )
        actual = min(available_kwh, max_charge) * self.charge_eff
        self.soc = min(self.max_soc, self.soc + actual / self.capacity)
        return round(actual, 4)

    def discharge(self, needed_kwh: float) -> float:
        """Discharge battery to cover deficit. Returns actual discharged kWh."""
        available = self.energy_available_kwh
        actual    = min(needed_kwh, available) / self.discharge_eff
        self.soc  = max(self.min_soc, self.soc - actual / self.capacity)
        return round(actual * self.discharge_eff, 4)


# ─────────────────────────────────────────────
# COMMUNITY SIMULATOR
# ─────────────────────────────────────────────

@dataclass
class IntervalReading:
    timestamp:          str
    community_id:       str
    mode:               str
    production_kwh:     float
    consumption_kwh:    float
    self_consumption:   float
    excess_kwh:         float
    grid_import_kwh:    float
    battery_soc_pct:    float
    net_kwh:            float
    oracle_price:       float
    interval_revenue:   float


class CommunitySimulator:

    def __init__(
        self,
        community_id:   str,
        mode:           str,
        location:       str,
        panel_kwp:      float,
        n_members:      int,
        battery_kwh:    float = 0.0,
    ):
        self.community_id  = community_id
        self.mode          = mode
        self.solar         = SolarSimulator(location, panel_kwp)
        self.consumption   = ConsumptionSimulator(n_members)
        self.battery       = BatterySimulator(battery_kwh) if battery_kwh > 0 else None
        self.oracle        = REEOracle(seed=42)
        self.readings: List[IntervalReading] = []

    def read_interval(self, dt: datetime) -> IntervalReading:
        """Simulate one 15-minute interval."""
        production  = self.solar.get_production_kwh(dt)
        consumption = self.consumption.get_consumption_kwh(dt)
        net         = production - consumption

        grid_import     = 0.0
        excess          = 0.0
        battery_soc     = 0.0
        self_consumption = min(production, consumption)

        if self.mode == "ON_GRID":
            if net >= 0:
                excess = net  # Surplus goes to grid
            else:
                grid_import = abs(net)  # Deficit from grid
            battery_soc = 0.0

        else:  # OFF_GRID
            if self.battery:
                if net >= 0:
                    stored  = self.battery.charge(net)
                    excess  = net - stored  # Any truly unabsorbable excess
                else:
                    discharged = self.battery.discharge(abs(net))
                    remaining  = abs(net) - discharged
                    grid_import = 0  # Off-grid — no grid backup
                battery_soc = self.battery.soc_pct

        # Oracle price for this interval
        price_tick = self.oracle.get_price_at(dt)
        oracle_price = price_tick.price_eur_kwh

        # Interval revenue
        savings_eur = self_consumption * 0.22 / (30 * 24 * 4)  # Proportional
        excess_rev  = excess * oracle_price if self.mode == "ON_GRID" else 0.0
        interval_revenue = savings_eur + excess_rev

        reading = IntervalReading(
            timestamp       = dt.isoformat(),
            community_id    = self.community_id,
            mode            = self.mode,
            production_kwh  = round(production, 4),
            consumption_kwh = round(consumption, 4),
            self_consumption= round(self_consumption, 4),
            excess_kwh      = round(excess, 4),
            grid_import_kwh = round(grid_import, 4),
            battery_soc_pct = battery_soc,
            net_kwh         = round(net, 4),
            oracle_price    = oracle_price,
            interval_revenue= round(interval_revenue, 6),
        )

        self.readings.append(reading)
        return reading

    def aggregate_monthly(self, readings: List[IntervalReading]) -> dict:
        """Aggregate interval readings into monthly settlement input."""
        total_production    = sum(r.production_kwh for r in readings)
        total_consumption   = sum(r.consumption_kwh for r in readings)
        total_self          = sum(r.self_consumption for r in readings)
        total_excess        = sum(r.excess_kwh for r in readings)
        avg_oracle          = sum(r.oracle_price for r in readings) / len(readings)

        return {
            "production_kwh":      round(total_production, 2),
            "self_consumption_kwh":round(total_self, 2),
            "excess_kwh":          round(total_excess, 2),
            "oracle_price":        round(avg_oracle, 4),
            "n_intervals":         len(readings),
        }


# ─────────────────────────────────────────────
# REAL-TIME LOOP
# ─────────────────────────────────────────────

class VoltcoreSimulation:
    """
    Full end-to-end simulation:
    1. AI generates real-time energy readings every N seconds
    2. Settlement engine calculates allocations
    3. Results written to JSON (picked up by dashboard)
    4. Summary printed to terminal
    """

    def __init__(self, interval_seconds: int = 5, accelerate: bool = True):
        self.interval_seconds = interval_seconds
        self.accelerate       = accelerate  # Simulate 15min per tick for demo
        self.running          = False

        # Communities
        self.og_sim = CommunitySimulator(
            "barcelona-gracia-solar", "ON_GRID", "barcelona",
            panel_kwp=20.0, n_members=10
        )
        self.fg_sim = CommunitySimulator(
            "extremadura-valle-verde", "OFF_GRID", "extremadura",
            panel_kwp=25.0, n_members=8, battery_kwh=48.0
        )

        # Settlement engines
        og_members = [Member(f"Member {i}", f"wallet_{i}", 3000) for i in range(10)]
        fg_members = [Member(f"Member {i}", f"wallet_{i}", 5000) for i in range(8)]

        self.og_community = Community(
            "Barcelona Gràcia Solar", CommunityMode.ON_GRID,
            og_members, 30000, 0.22
        )
        self.fg_community = Community(
            "Extremadura Valle Verde", CommunityMode.OFF_GRID,
            fg_members, 40000, 0.20
        )

        self.og_engine = SettlementEngine(self.og_community)
        self.fg_engine = SettlementEngine(self.fg_community)

        # Accumulator for monthly settlement
        self.og_interval_readings = []
        self.fg_interval_readings = []
        self.sim_time = datetime.now().replace(minute=0, second=0, microsecond=0)
        self.tick_count = 0
        self.settlement_count = 0

        # Output file for dashboard
        self.state_file = Path(__file__).parent / "simulation_state.json"

    def _print_header(self):
        print("\n" + "⚡"*30)
        print("  VOLTCORE END-TO-END SIMULATION")
        print("  Real-time AI energy simulation + settlement")
        print("⚡"*30)
        print(f"\n  Mode: {'ACCELERATED (15min/tick)' if self.accelerate else 'REAL-TIME'}")
        print(f"  Tick interval: {self.interval_seconds}s")
        print(f"  Communities: Barcelona (ON-GRID) + Extremadura (OFF-GRID)")
        print(f"  Starting from: {self.sim_time.strftime('%Y-%m-%d %H:%M')}")
        print("\n  Press Ctrl+C to stop\n")

    def _print_tick(self, og_r: IntervalReading, fg_r: IntervalReading, tick: int):
        sim_time_str = self.sim_time.strftime('%H:%M')
        print(f"\n  {'─'*70}")
        print(f"  TICK #{tick:04d} | Sim time: {sim_time_str} | "
              f"Real: {datetime.now().strftime('%H:%M:%S')}")
        print(f"  {'─'*70}")
        print(f"  🔌 BARCELONA  [ON-GRID]")
        print(f"     ☀  Production:   {og_r.production_kwh:>8.4f} kWh")
        print(f"     🏠 Self-used:    {og_r.self_consumption:>8.4f} kWh")
        print(f"     ⚡ → Grid:       {og_r.excess_kwh:>8.4f} kWh")
        print(f"     📥 ← Grid:       {og_r.grid_import_kwh:>8.4f} kWh")
        print(f"     💶 Oracle price: €{og_r.oracle_price:.4f}/kWh")
        print(f"     💰 Revenue:      €{og_r.interval_revenue:.4f}")
        print(f"     📉 Debt left:    €{self.og_community.total_debt_eur:,.2f}")
        print(f"     🌱 Treasury:     €{self.og_community.treasury_eur:,.2f}")

        print(f"\n  🌿 EXTREMADURA [OFF-GRID]")
        print(f"     ☀  Production:   {fg_r.production_kwh:>8.4f} kWh")
        print(f"     🏠 Self-used:    {fg_r.self_consumption:>8.4f} kWh")
        print(f"     🔋 Battery SOC:  {fg_r.battery_soc_pct:>7.1f}%")
        print(f"     💰 Savings:      €{fg_r.interval_revenue:.4f}")
        print(f"     📉 Debt left:    €{self.fg_community.total_debt_eur:,.2f}")
        print(f"     🌱 Treasury:     €{self.fg_community.treasury_eur:,.2f}")

    def _settle_monthly(self):
        """Fire monthly settlement when we have 30 days of data."""
        self.settlement_count += 1
        period = self.sim_time.strftime("%Y-%m")

        # On-grid settlement
        if self.og_interval_readings:
            og_agg = self.og_sim.aggregate_monthly(self.og_interval_readings)
            og_result = self.og_engine.settle(SettlementInput(
                period              = period,
                production_kwh      = og_agg["production_kwh"],
                self_consumption_kwh= og_agg["self_consumption_kwh"],
                excess_kwh          = og_agg["excess_kwh"],
                oracle_spot_price   = og_agg["oracle_price"],
            ))
            print(f"\n  🔔 MONTHLY SETTLEMENT #{self.settlement_count} — {period}")
            print(f"  Barcelona: gross €{og_result.gross_revenue_eur:.2f} | "
                  f"debt -€{og_result.debt_repayment_eur:.2f} | "
                  f"treasury +€{og_result.treasury_contribution_eur:.2f}")
            self.og_interval_readings = []

        # Off-grid settlement
        if self.fg_interval_readings:
            fg_agg = self.fg_sim.aggregate_monthly(self.fg_interval_readings)
            fg_result = self.fg_engine.settle(SettlementInput(
                period              = period,
                production_kwh      = fg_agg["production_kwh"],
                self_consumption_kwh= fg_agg["self_consumption_kwh"],
                excess_kwh          = fg_agg["excess_kwh"],
                oracle_spot_price   = None,
            ))
            print(f"  Extremadura: gross €{fg_result.gross_revenue_eur:.2f} | "
                  f"debt -€{fg_result.debt_repayment_eur:.2f} | "
                  f"treasury +€{fg_result.treasury_contribution_eur:.2f}")
            self.fg_interval_readings = []

    def _save_state(self, og_r: IntervalReading, fg_r: IntervalReading):
        """Write current state to JSON for dashboard to read."""
        state = {
            "timestamp":        datetime.now().isoformat(),
            "sim_time":         self.sim_time.isoformat(),
            "tick":             self.tick_count,
            "settlements":      self.settlement_count,
            "on_grid": {
                "reading":      asdict(og_r),
                "debt":         self.og_community.total_debt_eur,
                "treasury":     self.og_community.treasury_eur,
                "total_repaid": self.og_community.total_investment_eur - self.og_community.total_debt_eur,
            },
            "off_grid": {
                "reading":      asdict(fg_r),
                "debt":         self.fg_community.total_debt_eur,
                "treasury":     self.fg_community.treasury_eur,
                "total_repaid": self.fg_community.total_investment_eur - self.fg_community.total_debt_eur,
            }
        }
        self.state_file.write_text(json.dumps(state, indent=2))

    def run(self):
        self._print_header()
        self.running = True

        # Ticks per day in accelerated mode (96 x 15min intervals per day)
        ticks_per_month = 96 * 30

        try:
            while self.running:
                self.tick_count += 1

                # Generate readings
                og_r = self.og_sim.read_interval(self.sim_time)
                fg_r = self.fg_sim.read_interval(self.sim_time)

                # Accumulate for monthly settlement
                self.og_interval_readings.append(og_r)
                self.fg_interval_readings.append(fg_r)

                # Print every 4 ticks (every simulated hour)
                if self.tick_count % 4 == 0:
                    self._print_tick(og_r, fg_r, self.tick_count)

                # Save state for dashboard every tick
                self._save_state(og_r, fg_r)

                # Monthly settlement every 2880 ticks (30 days × 96 intervals)
                if self.tick_count % ticks_per_month == 0:
                    self._settle_monthly()

                # Advance simulated time by 15 minutes
                if self.accelerate:
                    self.sim_time += timedelta(minutes=15)
                else:
                    self.sim_time = datetime.now()

                time.sleep(self.interval_seconds)

        except KeyboardInterrupt:
            print(f"\n\n  ⚡ Simulation stopped after {self.tick_count} ticks")
            print(f"  📊 Simulated period: {self.sim_time.strftime('%Y-%m-%d %H:%M')}")
            print(f"  🏦 Barcelona treasury: €{self.og_community.treasury_eur:.2f}")
            print(f"  🏦 Extremadura treasury: €{self.fg_community.treasury_eur:.2f}")
            print(f"  📉 Barcelona debt: €{self.og_community.total_debt_eur:.2f}")
            print(f"  📉 Extremadura debt: €{self.fg_community.total_debt_eur:.2f}\n")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    # Parse args
    interval = 3       # seconds between ticks
    accelerate = True  # simulate 15min per tick

    if "--realtime" in sys.argv:
        accelerate = False
        interval = 900  # real 15 minutes

    if "--fast" in sys.argv:
        interval = 1

    sim = VoltcoreSimulation(
        interval_seconds=interval,
        accelerate=accelerate,
    )
    sim.run()
