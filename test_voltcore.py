"""
VOLTCORE Test Runner v0.1
==========================
Tests all components end-to-end:
  1. Oracle — price feed
  2. Meter  — energy readings (on-grid + off-grid)
  3. Settlement — full allocation (on-grid + off-grid)
  4. Integration — meter feeds into settlement via oracle

Run: python3 test_voltcore.py
"""

import sys
import json
import traceback
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────
# TEST UTILITIES
# ─────────────────────────────────────────────

PASS = "✅ PASS"
FAIL = "❌ FAIL"
results = []

def test(name: str, fn):
    try:
        fn()
        results.append((name, True, ""))
        print(f"  {PASS}  {name}")
        return True
    except Exception as e:
        results.append((name, False, str(e)))
        print(f"  {FAIL}  {name}")
        print(f"          → {e}")
        return False

def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ─────────────────────────────────────────────
# IMPORT MODULES
# ─────────────────────────────────────────────

section("0. IMPORTING MODULES")

try:
    from agent.oracle import REEOracle, PriceTick, MonthlyPriceStats
    print(f"  {PASS}  oracle.py imported")
except Exception as e:
    print(f"  {FAIL}  oracle.py — {e}")
    sys.exit(1)

try:
    from agent.meter import SIPSMeter, IoTMeter, CommunityReading, MeterSource
    print(f"  {PASS}  meter.py imported")
except Exception as e:
    print(f"  {FAIL}  meter.py — {e}")
    sys.exit(1)

try:
    from agent.settlement import (
        SettlementEngine, Community, Member,
        CommunityMode, SettlementInput
    )
    print(f"  {PASS}  settlement.py imported")
except Exception as e:
    print(f"  {FAIL}  settlement.py — {e}")
    sys.exit(1)

# ─────────────────────────────────────────────
# TEST 1 — ORACLE
# ─────────────────────────────────────────────

section("1. ORACLE TESTS")

oracle = REEOracle(seed=42)

def test_oracle_current_price():
    tick = oracle.get_current_price()
    assert isinstance(tick, PriceTick), "Should return PriceTick"
    assert 0.05 <= tick.price_eur_kwh <= 0.40, f"Price out of range: {tick.price_eur_kwh}"
    assert tick.period_type in ["PEAK", "VALLEY", "FLAT"], f"Invalid period: {tick.period_type}"

def test_oracle_monthly_average():
    stats = oracle.get_monthly_average(2025, 6)
    assert stats.avg_price > 0, "Average price should be positive"
    assert stats.min_price < stats.avg_price, "Min should be below average"
    assert stats.max_price > stats.avg_price, "Max should be above average"
    assert stats.peak_avg > stats.valley_avg, "Peak should cost more than valley"
    print(f"          → June 2025 avg: €{stats.avg_price:.4f}/kWh | peak: €{stats.peak_avg:.4f} | valley: €{stats.valley_avg:.4f}")

def test_oracle_peak_premium():
    from datetime import datetime
    peak_tick   = oracle.get_price_at(datetime(2025, 6, 13, 14, 0))  # 2pm peak
    valley_tick = oracle.get_price_at(datetime(2025, 6, 13, 3, 0))   # 3am valley
    assert peak_tick.price_eur_kwh > valley_tick.price_eur_kwh, \
        f"Peak ({peak_tick.price_eur_kwh}) should cost more than valley ({valley_tick.price_eur_kwh})"
    print(f"          → Peak: €{peak_tick.price_eur_kwh:.4f} | Valley: €{valley_tick.price_eur_kwh:.4f}")

def test_oracle_seasonal():
    winter = oracle.get_monthly_average(2025, 1)
    spring = oracle.get_monthly_average(2025, 4)
    assert winter.avg_price > spring.avg_price, \
        f"Winter ({winter.avg_price}) should be more expensive than spring ({spring.avg_price})"
    print(f"          → Winter avg: €{winter.avg_price:.4f} | Spring avg: €{spring.avg_price:.4f}")

def test_oracle_hourly_profile():
    profile = oracle.get_hourly_profile(2025, 6, 15)
    assert len(profile) == 24, f"Should return 24 ticks, got {len(profile)}"

test("Current price is valid", test_oracle_current_price)
test("Monthly average has correct structure", test_oracle_monthly_average)
test("Peak hours cost more than valley hours", test_oracle_peak_premium)
test("Winter is more expensive than spring", test_oracle_seasonal)
test("24-hour profile returns 24 ticks", test_oracle_hourly_profile)

# ─────────────────────────────────────────────
# TEST 2 — METER (ON-GRID)
# ─────────────────────────────────────────────

section("2. METER TESTS — ON-GRID (SIPS)")

sips = SIPSMeter("barcelona-gracia-solar", panel_kwp=20.0)
member_ids = [f"M{i:02d}" for i in range(1, 11)]
dt_peak   = datetime(2025, 6, 13, 13, 0)   # Peak solar
dt_night  = datetime(2025, 6, 13, 2, 0)    # Night

def test_sips_member_reading():
    r = sips.read_member("M01", "ES001CUPS", dt_peak)
    assert r.production_kwh >= 0, "Production should be non-negative"
    assert r.consumption_kwh >= 0, "Consumption should be non-negative"
    assert r.net_kwh == round(r.production_kwh - r.consumption_kwh, 3), "Net should be prod - cons"
    assert r.source == MeterSource.SIPS
    assert r.battery_soc_pct == 0.0, "On-grid has no battery"

def test_sips_peak_production():
    r_peak  = sips.read_member("M01", "ES001CUPS", dt_peak)
    r_night = sips.read_member("M01", "ES001CUPS", dt_night)
    assert r_peak.production_kwh > r_night.production_kwh, \
        f"Peak production ({r_peak.production_kwh}) should exceed night ({r_night.production_kwh})"
    print(f"          → Peak prod: {r_peak.production_kwh:.3f} kWh | Night prod: {r_night.production_kwh:.3f} kWh")

def test_sips_community_aggregation():
    reading = sips.read_community(member_ids, dt_peak)
    assert isinstance(reading, CommunityReading)
    assert reading.total_production_kwh > 0
    assert reading.total_consumption_kwh > 0
    assert reading.self_consumption_kwh <= reading.total_production_kwh
    assert reading.self_consumption_kwh <= reading.total_consumption_kwh
    assert reading.total_excess_kwh >= 0
    # Verify: self_consumption + excess = total_production
    assert abs((reading.self_consumption_kwh + reading.total_excess_kwh) - reading.total_production_kwh) < 0.01, \
        "Energy balance: self_consumption + excess should equal total production"
    print(f"          → Prod: {reading.total_production_kwh:.3f} | Cons: {reading.total_consumption_kwh:.3f} | Excess: {reading.total_excess_kwh:.3f} kWh")

def test_sips_energy_balance():
    """Golden rule: energy in = energy out"""
    reading = sips.read_community(member_ids, dt_peak)
    balance = reading.total_production_kwh - reading.self_consumption_kwh - reading.total_excess_kwh
    assert abs(balance) < 0.01, f"Energy balance violation: {balance:.4f} kWh unaccounted"

test("Member reading has correct structure", test_sips_member_reading)
test("Peak production > night production", test_sips_peak_production)
test("Community aggregation is consistent", test_sips_community_aggregation)
test("Energy balance holds (prod = self + excess)", test_sips_energy_balance)

# ─────────────────────────────────────────────
# TEST 3 — METER (OFF-GRID)
# ─────────────────────────────────────────────

section("3. METER TESTS — OFF-GRID (IoT)")

iot = IoTMeter("extremadura-valle-verde", panel_kwp=25.0, battery_kwh=48.0)
members = [{"id": f"M{i:02d}", "share_pct": 12.5} for i in range(1, 9)]

def test_iot_battery_charges():
    """Battery SOC should increase at peak solar hours"""
    dt_morning = datetime(2025, 6, 15, 8, 0)
    dt_noon    = datetime(2025, 6, 15, 13, 0)
    r_morning = iot.read_community(members, dt_morning)
    r_noon    = iot.read_community(members, dt_noon)
    # Battery should have more charge at noon (peak production)
    assert r_noon.battery_soc_avg_pct >= r_morning.battery_soc_avg_pct, \
        f"Battery should increase from morning ({r_morning.battery_soc_avg_pct}%) to noon ({r_noon.battery_soc_avg_pct}%)"
    print(f"          → Morning SOC: {r_morning.battery_soc_avg_pct:.1f}% | Noon SOC: {r_noon.battery_soc_avg_pct:.1f}%")

def test_iot_no_grid_export():
    """Off-grid community cannot export to grid"""
    for hour in [8, 12, 16]:
        dt = datetime(2025, 6, 15, hour, 0)
        reading = iot.read_community(members, dt)
        # All excess goes to battery, not grid
        assert reading.source == MeterSource.SHELLY

def test_iot_member_count():
    reading = iot.read_community(members, dt_peak)
    assert len(reading.member_readings) == 8, f"Expected 8 members, got {len(reading.member_readings)}"

def test_iot_equal_shares():
    """Equal investment = equal production share"""
    reading = iot.read_community(members, dt_peak)
    productions = [r.production_kwh for r in reading.member_readings]
    avg = sum(productions) / len(productions)
    for p in productions:
        deviation = abs(p - avg) / avg if avg > 0 else 0
        assert deviation < 0.20, f"Member production deviation too high: {deviation:.0%}"

test("Battery charges during peak solar hours", test_iot_battery_charges)
test("Off-grid has no grid export", test_iot_no_grid_export)
test("Community has correct member count", test_iot_member_count)
test("Equal shares produce roughly equal energy", test_iot_equal_shares)

# ─────────────────────────────────────────────
# TEST 4 — SETTLEMENT ENGINE
# ─────────────────────────────────────────────

section("4. SETTLEMENT ENGINE TESTS")

def make_on_grid_community():
    members = [Member(f"Member {i}", f"wallet_{i}", 3000) for i in range(10)]
    return Community(
        name="Test On-Grid",
        mode=CommunityMode.ON_GRID,
        members=members,
        total_investment_eur=30000,
        reference_price_eur_kwh=0.22,
    )

def make_off_grid_community():
    members = [Member(f"Member {i}", f"wallet_{i}", 5000) for i in range(8)]
    return Community(
        name="Test Off-Grid",
        mode=CommunityMode.OFF_GRID,
        members=members,
        total_investment_eur=40000,
        reference_price_eur_kwh=0.20,
    )

def test_settlement_on_grid_revenue():
    c = make_on_grid_community()
    engine = SettlementEngine(c)
    result = engine.settle(SettlementInput(
        period="2025-06",
        production_kwh=2400,
        self_consumption_kwh=1600,
        excess_kwh=800,
        oracle_spot_price=0.15,
    ))
    assert result.savings_eur == round(1600 * 0.22, 2), f"Savings wrong: {result.savings_eur}"
    assert result.excess_revenue_eur == round(800 * 0.15, 2), f"Excess revenue wrong: {result.excess_revenue_eur}"
    assert result.gross_revenue_eur == round(result.savings_eur + result.excess_revenue_eur, 2)
    print(f"          → Savings: €{result.savings_eur} | Excess: €{result.excess_revenue_eur} | Gross: €{result.gross_revenue_eur}")

def test_settlement_off_grid_no_excess_revenue():
    c = make_off_grid_community()
    engine = SettlementEngine(c)
    result = engine.settle(SettlementInput(
        period="2025-06",
        production_kwh=3000,
        self_consumption_kwh=3000,
        excess_kwh=0,
        oracle_spot_price=None,
    ))
    assert result.excess_revenue_eur == 0.0, "Off-grid should have zero excess revenue"
    assert result.savings_eur == round(3000 * 0.20, 2), f"Savings wrong: {result.savings_eur}"
    print(f"          → Off-grid savings: €{result.savings_eur} | Excess revenue: €{result.excess_revenue_eur}")

def test_settlement_allocation_sums_to_gross():
    c = make_on_grid_community()
    engine = SettlementEngine(c)
    result = engine.settle(SettlementInput("2025-06", 2400, 1600, 800, 0.15))
    total_allocated = round(
        result.debt_repayment_eur +
        result.treasury_contribution_eur +
        result.operations_eur +
        result.protocol_fee_eur, 2
    )
    assert abs(total_allocated - result.gross_revenue_eur) < 0.05, \
        f"Allocation {total_allocated} doesn't sum to gross {result.gross_revenue_eur}"
    print(f"          → Gross: €{result.gross_revenue_eur} | Allocated: €{total_allocated} | Diff: €{abs(total_allocated - result.gross_revenue_eur):.4f}")

def test_settlement_debt_decreases():
    c = make_on_grid_community()
    engine = SettlementEngine(c)
    initial_debt = c.total_debt_eur
    engine.settle(SettlementInput("2025-06", 2400, 1600, 800, 0.15))
    assert c.total_debt_eur < initial_debt, "Debt should decrease after settlement"
    print(f"          → Debt: €{initial_debt} → €{c.total_debt_eur} (repaid €{initial_debt - c.total_debt_eur:.2f})")

def test_settlement_member_shares_sum_to_100():
    c = make_on_grid_community()
    engine = SettlementEngine(c)
    result = engine.settle(SettlementInput("2025-06", 2400, 1600, 800, 0.15))
    total_shares = sum(mb["share_pct"] for mb in result.member_breakdown)
    assert abs(total_shares - 100.0) < 0.01, f"Member shares should sum to 100%, got {total_shares}"
    print(f"          → Total shares: {total_shares:.4f}%")

def test_settlement_treasury_grows():
    c = make_on_grid_community()
    engine = SettlementEngine(c)
    engine.settle(SettlementInput("2025-01", 2400, 1600, 800, 0.15))
    balance_1 = c.treasury_eur
    engine.settle(SettlementInput("2025-02", 2400, 1600, 800, 0.15))
    balance_2 = c.treasury_eur
    assert balance_2 > balance_1, "Treasury should grow each month"
    print(f"          → Treasury month 1: €{balance_1:.2f} | month 2: €{balance_2:.2f}")

test("On-grid revenue = savings + excess at oracle price", test_settlement_on_grid_revenue)
test("Off-grid has zero excess revenue", test_settlement_off_grid_no_excess_revenue)
test("Allocation ratios sum to gross revenue", test_settlement_allocation_sums_to_gross)
test("Debt decreases after each settlement", test_settlement_debt_decreases)
test("Member shares sum to 100%", test_settlement_member_shares_sum_to_100)
test("Treasury grows month over month", test_settlement_treasury_grows)

# ─────────────────────────────────────────────
# TEST 5 — INTEGRATION (Meter → Oracle → Settlement)
# ─────────────────────────────────────────────

section("5. INTEGRATION TEST — Full Pipeline")

def test_full_pipeline_on_grid():
    """Simulate a real month: read meters → get oracle price → settle"""

    # 1. Read meter (simulate monthly aggregate from 15-min readings)
    sips_meter = SIPSMeter("integration-test", panel_kwp=20.0)
    member_ids = [f"M{i:02d}" for i in range(1, 11)]

    # Aggregate 30 days of noon readings (simplified)
    monthly_production = 0.0
    monthly_consumption = 0.0
    monthly_excess = 0.0

    for day in range(1, 31):
        try:
            dt = datetime(2025, 6, day, 13, 0)
            reading = sips_meter.read_community(member_ids, dt)
            # Scale 15-min reading to daily (×4 intervals per hour × 8 peak hours)
            monthly_production  += reading.total_production_kwh * 32
            monthly_consumption += reading.total_consumption_kwh * 96
            monthly_excess      += reading.total_excess_kwh * 32
        except:
            pass

    # 2. Get oracle price for the month
    oracle_inst = REEOracle(seed=42)
    price_stats = oracle_inst.get_monthly_average(2025, 6)
    spot_price = price_stats.avg_price

    # 3. Settle
    members = [Member(f"Member {i}", f"wallet_{i}", 3000) for i in range(10)]
    community = Community(
        name="Integration Test Community",
        mode=CommunityMode.ON_GRID,
        members=members,
        total_investment_eur=30000,
        reference_price_eur_kwh=0.22,
    )
    engine = SettlementEngine(community)
    result = engine.settle(SettlementInput(
        period="2025-06",
        production_kwh=round(monthly_production, 1),
        self_consumption_kwh=round(monthly_consumption * 0.6, 1),
        excess_kwh=round(monthly_excess, 1),
        oracle_spot_price=spot_price,
    ))

    assert result.gross_revenue_eur > 0
    assert result.debt_repayment_eur > 0
    assert result.treasury_balance > 0
    assert len(result.member_breakdown) == 10

    print(f"          → Meter read: {monthly_production:.1f} kWh produced")
    print(f"          → Oracle price: €{spot_price:.4f}/kWh")
    print(f"          → Settlement gross: €{result.gross_revenue_eur}")
    print(f"          → Debt repaid: €{result.debt_repayment_eur}")
    print(f"          → Treasury: €{result.treasury_balance}")

def test_mock_data_loads():
    """Verify mock JSON files are valid and complete"""
    on_grid_path  = Path("agent/mock/on_grid_mock.json")
    off_grid_path = Path("agent/mock/off_grid_mock.json")

    assert on_grid_path.exists(), "on_grid_mock.json missing"
    assert off_grid_path.exists(), "off_grid_mock.json missing"

    with open(on_grid_path) as f:
        on_grid = json.load(f)
    with open(off_grid_path) as f:
        off_grid = json.load(f)

    assert on_grid["mode"] == "ON_GRID"
    assert off_grid["mode"] == "OFF_GRID"
    assert len(on_grid["members"]) == 10
    assert len(off_grid["members"]) == 8
    assert on_grid["financials"]["total_investment_eur"] == 30000
    assert off_grid["financials"]["total_investment_eur"] == 40000

    print(f"          → on_grid_mock.json: {len(on_grid['members'])} members, €{on_grid['financials']['total_investment_eur']}")
    print(f"          → off_grid_mock.json: {len(off_grid['members'])} members, €{off_grid['financials']['total_investment_eur']}")

test("Full pipeline: meter → oracle → settlement", test_full_pipeline_on_grid)
test("Mock data files load and validate correctly", test_mock_data_loads)

# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────

section("TEST SUMMARY")

passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
total  = len(results)

print(f"\n  Total:  {total} tests")
print(f"  Passed: {passed} ✅")
print(f"  Failed: {failed} ❌")
print(f"\n  Score:  {passed}/{total} ({100*passed//total}%)\n")

if failed > 0:
    print("  Failed tests:")
    for name, ok, err in results:
        if not ok:
            print(f"    ❌ {name}")
            print(f"       {err}")
    sys.exit(1)
else:
    print("  🎉 All tests passing — VOLTCORE engine is ready!\n")
    sys.exit(0)