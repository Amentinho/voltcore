"""
VOLTCORE Meter v0.1
====================
Handles energy data ingestion for both ON-GRID and OFF-GRID communities.

ON-GRID  → SIPS API (Spain's official smart meter standard)
           Every Spanish home built post-2018 has a mandatory smart meter.
           Distributors (Endesa, Iberdrola, Naturgy) expose data via SIPS.
           Homeowners authorize VOLTCORE via OAuth-style flow.

OFF-GRID → IoT inverter APIs (SolarEdge, Fronius, Shelly)
           Community installs any standard solar inverter.
           VOLTCORE reads local REST API — no proprietary hardware needed.
           Also supports Home Assistant as unified aggregator.

In production:
  - ON-GRID:  HTTP calls to distributor SIPS endpoints (authorized)
  - OFF-GRID: Local network calls to inverter REST API every 15 min
  
In demo/hackathon:
  - Both modes use realistic mock data from mock/ JSON files
  - Anomaly detection runs on mock data to show AI layer working
"""

import json
import random
import math
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from pathlib import Path


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

READING_INTERVAL_MINUTES = 15       # Settlement reads every 15 min
ANOMALY_THRESHOLD_PCT    = 0.25     # Flag readings >25% above expected
BATTERY_EFFICIENCY       = 0.92     # 92% round-trip efficiency (LFP batteries)


# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────

class MeterSource(Enum):
    SIPS      = "SIPS"        # On-grid: Spain smart meter
    SOLAR_EDGE = "SOLAREDGE"  # Off-grid: SolarEdge inverter API
    SHELLY    = "SHELLY"      # Off-grid: Shelly energy monitor
    MOCK      = "MOCK"        # Demo mode


@dataclass
class MemberReading:
    """Energy reading for a single community member."""
    member_id: str
    timestamp: datetime
    production_kwh: float       # Solar produced (0 if not a producer)
    consumption_kwh: float      # Energy consumed
    battery_soc_pct: float      # Battery state of charge (off-grid only, else 0)
    net_kwh: float              # production - consumption (+ = surplus, - = deficit)
    source: MeterSource
    anomaly_flag: bool = False
    anomaly_reason: str = ""


@dataclass
class CommunityReading:
    """Aggregated energy reading for the whole community."""
    community_id: str
    period_start: datetime
    period_end: datetime
    total_production_kwh: float
    total_consumption_kwh: float
    total_excess_kwh: float         # Sold to grid (on-grid) or stored (off-grid)
    self_consumption_kwh: float     # Directly consumed from solar
    battery_soc_avg_pct: float      # Off-grid only
    member_readings: list
    anomalies_detected: int
    source: MeterSource


# ─────────────────────────────────────────────
# SOLAR PRODUCTION MODEL
# ─────────────────────────────────────────────

class SolarModel:
    """
    Physics-based solar production estimator.
    Uses PVGIS data (EU Solar Atlas — free public API).
    In production: cross-validates IoT readings against PVGIS forecast.
    """

    # Barcelona peak sun hours by month (PVGIS data)
    BARCELONA_PSH = {
        1: 3.2, 2: 4.1, 3: 5.3, 4: 6.2, 5: 7.1, 6: 7.8,
        7: 7.9, 8: 7.2, 9: 6.0, 10: 4.8, 11: 3.5, 12: 3.0
    }

    # Extremadura peak sun hours (highest in Spain)
    EXTREMADURA_PSH = {
        1: 3.8, 2: 4.7, 3: 6.0, 4: 7.0, 5: 8.0, 6: 8.7,
        7: 9.0, 8: 8.3, 9: 6.8, 10: 5.4, 11: 4.0, 12: 3.5
    }

    @staticmethod
    def expected_daily_kwh(panel_kwp: float, month: int, location: str = "barcelona") -> float:
        """Expected daily production in kWh given panel size and location."""
        psh_data = SolarModel.EXTREMADURA_PSH if location == "extremadura" else SolarModel.BARCELONA_PSH
        psh = psh_data.get(month, 5.0)
        efficiency = 0.82  # System efficiency (inverter + cable losses)
        return round(panel_kwp * psh * efficiency, 2)

    @staticmethod
    def hourly_profile(daily_kwh: float, hour: int) -> float:
        """Distribute daily production across daylight hours (bell curve)."""
        if hour < 6 or hour > 20:
            return 0.0
        # Peak at solar noon (~13h in Spain)
        peak_hour = 13
        sigma = 3.5
        profile = math.exp(-0.5 * ((hour - peak_hour) / sigma) ** 2)
        # Normalize so sum across day ≈ 1
        normalization = sum(
            math.exp(-0.5 * ((h - peak_hour) / sigma) ** 2)
            for h in range(6, 21)
        )
        return round(daily_kwh * (profile / normalization), 3)


# ─────────────────────────────────────────────
# ANOMALY DETECTOR
# ─────────────────────────────────────────────

class AnomalyDetector:
    """
    AI anomaly detection layer.
    Flags readings that are inconsistent with:
    - Historical patterns
    - Solar irradiance data
    - Neighboring meter readings
    """

    def __init__(self, sensitivity: float = 0.25):
        self.sensitivity = sensitivity
        self.history: list[float] = []

    def check(self, reading: float, expected: float, label: str = "") -> tuple[bool, str]:
        self.history.append(reading)

        # Check vs expected (physics-based)
        if expected > 0:
            deviation = abs(reading - expected) / expected
            if deviation > self.sensitivity:
                return True, f"{label} deviation {deviation:.0%} from expected {expected:.2f} kWh"

        # Check vs historical average (if enough history)
        if len(self.history) >= 3:
            avg = sum(self.history[-6:]) / len(self.history[-6:])
            if avg > 0 and abs(reading - avg) / avg > self.sensitivity * 1.5:
                hist_dev = abs(reading - avg) / avg
                return True, f"{label} {hist_dev:.0%} deviation from 6-period average {avg:.2f}"

        return False, ""


# ─────────────────────────────────────────────
# ON-GRID METER (SIPS)
# ─────────────────────────────────────────────

class SIPSMeter:
    """
    Simulates Spain SIPS smart meter API.
    
    In production:
    POST https://www.{distributor}.es/api/sips/v2/consumption
    Authorization: Bearer {oauth_token}
    Body: { cups: "ES...", startDate: "...", endDate: "..." }
    
    CUPS = Código Unificado de Punto de Suministro
    (Spain's unique meter ID — like an IBAN for energy)
    """

    def __init__(self, community_id: str, panel_kwp: float = 20.0):
        self.community_id = community_id
        self.panel_kwp = panel_kwp
        self.solar_model = SolarModel()
        self.anomaly_detector = AnomalyDetector()
        print(f"  [SIPS] Meter initialized for {community_id}")
        print(f"  [SIPS] Panel capacity: {panel_kwp} kWp")
        print(f"  [SIPS] Mode: MOCK (replace with distributor OAuth in production)")

    def read_member(self, member_id: str, cups: str, dt: datetime) -> MemberReading:
        """Read 15-minute interval data for one member."""
        month = dt.month
        hour = dt.hour

        # Expected production (physics-based)
        daily_expected = self.solar_model.expected_daily_kwh(
            self.panel_kwp / 10,  # Each member has 1/10 of panels
            month,
            "barcelona"
        )
        expected_15min = self.solar_model.hourly_profile(daily_expected, hour) / 4

        # Add realistic noise (±5%)
        noise = random.uniform(0.95, 1.05)
        production = round(expected_15min * noise, 3)

        # Consumption: base load + random (avg 300 kWh/month per household)
        base_consumption_15min = 300 / (30 * 24 * 4)
        consumption_noise = random.uniform(0.6, 2.0)  # High variance in consumption
        consumption = round(base_consumption_15min * consumption_noise, 3)

        net = round(production - consumption, 3)

        # Anomaly check
        anomaly, reason = self.anomaly_detector.check(
            production, expected_15min, f"Member {member_id} production"
        )

        return MemberReading(
            member_id=member_id,
            timestamp=dt,
            production_kwh=production,
            consumption_kwh=consumption,
            battery_soc_pct=0.0,  # No battery on-grid
            net_kwh=net,
            source=MeterSource.SIPS,
            anomaly_flag=anomaly,
            anomaly_reason=reason
        )

    def read_community(self, member_ids: list[str], dt: datetime) -> CommunityReading:
        """Aggregate 15-minute reading for entire community."""
        readings = [
            self.read_member(mid, f"ES{mid}CUPS", dt)
            for mid in member_ids
        ]

        total_production = sum(r.production_kwh for r in readings)
        total_consumption = sum(r.consumption_kwh for r in readings)
        self_consumption = min(total_production, total_consumption)
        excess = max(0, total_production - total_consumption)
        anomalies = sum(1 for r in readings if r.anomaly_flag)

        return CommunityReading(
            community_id=self.community_id,
            period_start=dt,
            period_end=dt + timedelta(minutes=15),
            total_production_kwh=round(total_production, 3),
            total_consumption_kwh=round(total_consumption, 3),
            total_excess_kwh=round(excess, 3),
            self_consumption_kwh=round(self_consumption, 3),
            battery_soc_avg_pct=0.0,
            member_readings=readings,
            anomalies_detected=anomalies,
            source=MeterSource.SIPS
        )


# ─────────────────────────────────────────────
# OFF-GRID METER (IoT Inverter)
# ─────────────────────────────────────────────

class IoTMeter:
    """
    Simulates SolarEdge / Shelly inverter REST API.
    
    In production:
    GET http://{inverter_local_ip}/api/v1/currentPowerFlow
    GET http://{shelly_local_ip}/meter/0
    
    No cloud dependency — reads directly from local network.
    Compatible with Home Assistant for unified aggregation.
    """

    def __init__(self, community_id: str, panel_kwp: float = 25.0, battery_kwh: float = 48.0):
        self.community_id = community_id
        self.panel_kwp = panel_kwp
        self.battery_kwh = battery_kwh
        self.battery_soc = 0.75  # Start at 75% charge
        self.solar_model = SolarModel()
        self.anomaly_detector = AnomalyDetector()
        print(f"  [IoT] Inverter initialized for {community_id}")
        print(f"  [IoT] Panel capacity: {panel_kwp} kWp")
        print(f"  [IoT] Battery capacity: {battery_kwh} kWh")
        print(f"  [IoT] Mode: MOCK (replace with inverter REST API in production)")

    def _update_battery(self, surplus_kwh: float) -> float:
        """Update battery state of charge, return actual stored/discharged amount."""
        if surplus_kwh > 0:
            # Charging
            storable = min(surplus_kwh * BATTERY_EFFICIENCY,
                         self.battery_kwh * (1 - self.battery_soc))
            self.battery_soc += storable / self.battery_kwh
            self.battery_soc = min(1.0, self.battery_soc)
            return storable
        else:
            # Discharging
            needed = abs(surplus_kwh)
            available = self.battery_kwh * self.battery_soc * BATTERY_EFFICIENCY
            discharged = min(needed, available)
            self.battery_soc -= discharged / self.battery_kwh
            self.battery_soc = max(0.0, self.battery_soc)
            return -discharged

    def read_member(self, member_id: str, member_share_pct: float, dt: datetime) -> MemberReading:
        """Read 15-minute interval data for one member (proportional to share)."""
        month = dt.month
        hour = dt.hour

        daily_expected = self.solar_model.expected_daily_kwh(
            self.panel_kwp * (member_share_pct / 100),
            month,
            "extremadura"
        )
        expected_15min = self.solar_model.hourly_profile(daily_expected, hour) / 4

        noise = random.uniform(0.93, 1.07)
        production = round(expected_15min * noise, 3)

        # Off-grid consumption slightly higher (more appliances, no grid backup)
        base_consumption_15min = 375 / (30 * 24 * 4)
        consumption_noise = random.uniform(0.5, 2.2)
        consumption = round(base_consumption_15min * consumption_noise, 3)

        net = round(production - consumption, 3)

        anomaly, reason = self.anomaly_detector.check(
            production, expected_15min, f"Member {member_id} production"
        )

        return MemberReading(
            member_id=member_id,
            timestamp=dt,
            production_kwh=production,
            consumption_kwh=consumption,
            battery_soc_pct=round(self.battery_soc * 100, 1),
            net_kwh=net,
            source=MeterSource.SHELLY,
            anomaly_flag=anomaly,
            anomaly_reason=reason
        )

    def read_community(self, members: list[dict], dt: datetime) -> CommunityReading:
        """Aggregate 15-minute reading for entire off-grid community."""
        readings = [
            self.read_member(m["id"], m["share_pct"], dt)
            for m in members
        ]

        total_production = sum(r.production_kwh for r in readings)
        total_consumption = sum(r.consumption_kwh for r in readings)
        surplus = total_production - total_consumption

        # Battery handles surplus/deficit
        battery_delta = self._update_battery(surplus)
        actual_self_consumption = min(total_production, total_consumption)
        excess_stored = max(0, battery_delta)  # What went into battery

        anomalies = sum(1 for r in readings if r.anomaly_flag)

        return CommunityReading(
            community_id=self.community_id,
            period_start=dt,
            period_end=dt + timedelta(minutes=15),
            total_production_kwh=round(total_production, 3),
            total_consumption_kwh=round(total_consumption, 3),
            total_excess_kwh=round(excess_stored, 3),
            self_consumption_kwh=round(actual_self_consumption, 3),
            battery_soc_avg_pct=round(self.battery_soc * 100, 1),
            member_readings=readings,
            anomalies_detected=anomalies,
            source=MeterSource.SHELLY
        )


# ─────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────

def demo():
    print("\n" + "="*60)
    print("  VOLTCORE METER DEMO")
    print("="*60)

    # ON-GRID demo
    print("\n\n  🔌 ON-GRID — SIPS Smart Meter")
    print("  " + "-"*40)
    sips = SIPSMeter("barcelona-gracia-solar", panel_kwp=20.0)

    member_ids = [f"M{i:02d}" for i in range(1, 11)]
    dt = datetime(2025, 6, 13, 13, 0)  # Peak solar hour

    reading = sips.read_community(member_ids, dt)
    print(f"\n  📊 Community reading @ {dt.strftime('%H:%M')} (peak solar)")
    print(f"     Total production:    {reading.total_production_kwh:.3f} kWh")
    print(f"     Total consumption:   {reading.total_consumption_kwh:.3f} kWh")
    print(f"     Self consumption:    {reading.self_consumption_kwh:.3f} kWh")
    print(f"     Excess (→ grid):     {reading.total_excess_kwh:.3f} kWh")
    print(f"     Anomalies detected:  {reading.anomalies_detected}")
    print(f"\n  👥 Member breakdown:")
    for r in reading.member_readings:
        status = "⚠️ ANOMALY" if r.anomaly_flag else "✅"
        print(f"     {r.member_id}: prod={r.production_kwh:.3f} "
              f"cons={r.consumption_kwh:.3f} "
              f"net={r.net_kwh:+.3f} kWh {status}")

    # OFF-GRID demo
    print("\n\n  🌿 OFF-GRID — IoT Inverter (Shelly/SolarEdge)")
    print("  " + "-"*40)
    iot = IoTMeter("extremadura-valle-verde", panel_kwp=25.0, battery_kwh=48.0)

    members = [{"id": f"M{i:02d}", "share_pct": 12.5} for i in range(1, 9)]

    print(f"\n  📊 24-hour simulation (reading every hour):")
    print(f"\n  {'Time':<8} {'Prod':>8} {'Cons':>8} {'Battery':>10} {'Anomalies':>10}")
    print(f"  {'-'*48}")

    for hour in range(6, 21):  # Daylight hours (6am-8pm)
        dt = datetime(2025, 6, 15, hour, 0)
        r = iot.read_community(members, dt)
        print(f"  {dt.strftime('%H:00'):<8} "
              f"{r.total_production_kwh:>7.3f}  "
              f"{r.total_consumption_kwh:>7.3f}  "
              f"{r.battery_soc_avg_pct:>8.1f}%  "
              f"{'⚠️ '+str(r.anomalies_detected) if r.anomalies_detected else '✅':>10}")


if __name__ == "__main__":
    demo()