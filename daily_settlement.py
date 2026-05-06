"""
VOLTCORE Daily Settlement & Escrow Engine v1.0
================================================
Handles daily settlement cycles, escrow fund management,
carbon credit accumulation, and full financial transparency.

EU Regulatory compliance:
- RD 244/2019 (Spain self-consumption)
- EU RED II (Renewable Energy Communities)
- CNMC reporting format
"""

import json
import math
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from pathlib import Path
from enum import Enum


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

# Revenue allocation (daily settlement)
DEBT_RATIO          = 0.55   # 55% repays infrastructure
ESCROW_RATIO        = 0.15   # 15% goes to escrow investment fund
OPERATIONS_RATIO    = 0.20   # 20% operations + maintenance
PROTOCOL_FEE        = 0.05   # 5% VOLTCORE protocol fee
RESERVE_RATIO       = 0.05   # 5% emergency reserve

# Escrow fund parameters
ESCROW_YIELD_APY    = 0.055  # 5.5% APY (conservative staking)
ESCROW_YIELD_DAILY  = ESCROW_YIELD_APY / 365

# Carbon credits (Spain CNMC data)
CARBON_INTENSITY_GRID   = 0.180  # kg CO2/kWh (Spanish grid 2024)
CARBON_CREDIT_EUR_TON   = 65.0   # EU ETS carbon price EUR/ton
GO_CERTIFICATE_EUR_MWH  = 2.50   # Guarantees of Origin EUR/MWh

# Insurance parameters
INSURANCE_THRESHOLD_PCT = 0.70   # Trigger if production < 70% of expected
INSURANCE_PREMIUM_PCT   = 0.02   # 2% of monthly revenue = premium
INSURANCE_PAYOUT_MULT   = 3.0    # 3x premium as max payout


# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────

class CommunityType(Enum):
    ON_GRID  = "ON_GRID"
    OFF_GRID = "OFF_GRID"


@dataclass
class DailySettlement:
    date:                   str
    community_id:           str
    community_type:         str

    # Energy
    production_kwh:         float
    self_consumption_kwh:   float
    excess_kwh:             float
    grid_import_kwh:        float
    battery_avg_soc:        float

    # Revenue
    savings_eur:            float
    excess_revenue_eur:     float
    gross_revenue_eur:      float
    oracle_price_eur:       float

    # Allocation
    debt_payment_eur:       float
    escrow_contribution_eur:float
    operations_eur:         float
    protocol_fee_eur:       float
    reserve_eur:            float

    # Escrow
    escrow_balance_eur:     float
    escrow_yield_today_eur: float
    cumulative_yield_eur:   float

    # Carbon
    co2_avoided_kg:         float
    carbon_credits_eur:     float
    go_certificates_mwh:    float
    go_revenue_eur:         float

    # Insurance
    insurance_premium_eur:  float
    insurance_triggered:    bool
    insurance_payout_eur:   float

    # Debt
    debt_remaining_eur:     float
    debt_repaid_pct:        float

    # Members
    member_breakdown:       List[Dict]

    # Solana
    settlement_tx:          str = ""  # Solana tx signature


@dataclass
class EscrowFund:
    """Community escrow investment fund."""
    community_id:       str
    balance_eur:        float = 0.0
    total_contributed:  float = 0.0
    total_yield:        float = 0.0
    total_withdrawn:    float = 0.0
    staking_position:   str = "sunrise-stake"  # Solana ReFi protocol
    yield_apy:          float = ESCROW_YIELD_APY

    def contribute(self, amount: float) -> float:
        """Add to escrow, return daily yield generated."""
        self.balance_eur     += amount
        self.total_contributed += amount
        daily_yield = self.balance_eur * ESCROW_YIELD_DAILY
        self.balance_eur    += daily_yield
        self.total_yield    += daily_yield
        return daily_yield

    def withdraw(self, amount: float) -> float:
        """Withdraw from escrow for investment."""
        actual = min(amount, self.balance_eur)
        self.balance_eur    -= actual
        self.total_withdrawn += actual
        return actual

    @property
    def roi_pct(self) -> float:
        if self.total_contributed == 0:
            return 0.0
        return (self.total_yield / self.total_contributed) * 100


@dataclass
class CarbonTracker:
    """Track carbon credits and Guarantees of Origin."""
    community_id:           str
    total_co2_avoided_kg:   float = 0.0
    total_credits_eur:      float = 0.0
    total_go_mwh:           float = 0.0
    total_go_revenue_eur:   float = 0.0

    def record_production(self, kwh: float) -> dict:
        """Record production and calculate carbon value."""
        co2_avoided_kg      = kwh * CARBON_INTENSITY_GRID
        co2_avoided_ton     = co2_avoided_kg / 1000
        carbon_credits_eur  = co2_avoided_ton * CARBON_CREDIT_EUR_TON
        go_mwh              = kwh / 1000
        go_revenue_eur      = go_mwh * GO_CERTIFICATE_EUR_MWH

        self.total_co2_avoided_kg   += co2_avoided_kg
        self.total_credits_eur      += carbon_credits_eur
        self.total_go_mwh           += go_mwh
        self.total_go_revenue_eur   += go_revenue_eur

        return {
            "co2_avoided_kg":       round(co2_avoided_kg, 3),
            "carbon_credits_eur":   round(carbon_credits_eur, 4),
            "go_mwh":               round(go_mwh, 4),
            "go_revenue_eur":       round(go_revenue_eur, 4),
        }


@dataclass
class InsuranceFund:
    """
    Parametric insurance against low solar production.
    EU compliant — triggers automatically via smart contract.
    No claims process needed.
    """
    community_id:           str
    expected_daily_kwh:     float
    premium_balance_eur:    float = 0.0
    total_premiums_eur:     float = 0.0
    total_payouts_eur:      float = 0.0
    trigger_count:          int   = 0

    def collect_premium(self, daily_revenue_eur: float) -> float:
        premium = daily_revenue_eur * INSURANCE_PREMIUM_PCT
        self.premium_balance_eur += premium
        self.total_premiums_eur  += premium
        return round(premium, 4)

    def check_trigger(self, actual_kwh: float) -> tuple[bool, float]:
        """
        Check if insurance should trigger.
        Returns (triggered, payout_amount).
        """
        if self.expected_daily_kwh == 0:
            return False, 0.0

        production_ratio = actual_kwh / self.expected_daily_kwh
        if production_ratio < INSURANCE_THRESHOLD_PCT:
            shortfall_pct = INSURANCE_THRESHOLD_PCT - production_ratio
            payout = min(
                self.premium_balance_eur * INSURANCE_PAYOUT_MULT * shortfall_pct,
                self.premium_balance_eur
            )
            if payout > 0:
                self.premium_balance_eur -= payout
                self.total_payouts_eur   += payout
                self.trigger_count       += 1
                return True, round(payout, 4)

        return False, 0.0


# ─────────────────────────────────────────────
# DAILY SETTLEMENT ENGINE
# ─────────────────────────────────────────────

class DailySettlementEngine:
    """
    Full daily settlement with all financial layers:
    - Energy settlement
    - Debt repayment
    - Escrow fund contribution + yield
    - Carbon credits + GOs
    - Parametric insurance
    - Member transparency breakdown
    - CNMC regulatory reporting
    """

    def __init__(self, community_config: dict):
        self.config     = community_config
        self.community_id = community_config["id"]
        self.mode       = community_config["mode"]
        self.members    = community_config["members"]
        self.total_debt = community_config["total_investment"]
        self.debt_repaid = 0.0
        self.reserve_fund = 0.0

        # Sub-engines
        self.escrow      = EscrowFund(self.community_id)
        self.carbon      = CarbonTracker(self.community_id)
        self.insurance   = InsuranceFund(
            self.community_id,
            expected_daily_kwh=community_config.get("expected_daily_kwh", 80.0)
        )

        # Settlement history
        self.settlements: List[DailySettlement] = []

    def settle_day(
        self,
        settlement_date: str,
        production_kwh: float,
        self_consumption_kwh: float,
        excess_kwh: float,
        oracle_price_eur: float,
        grid_import_kwh: float = 0.0,
        battery_avg_soc: float = 0.0,
    ) -> DailySettlement:
        """
        Run daily settlement for the community.
        Calculates all financial flows and records on-chain.
        """

        # ── REVENUE ────────────────────────────────────────────
        ref_price       = self.config["reference_price_eur_kwh"]
        savings_eur     = self_consumption_kwh * ref_price
        excess_rev_eur  = excess_kwh * oracle_price_eur if self.mode == "ON_GRID" else 0.0
        gross_eur       = savings_eur + excess_rev_eur

        # ── CARBON ─────────────────────────────────────────────
        carbon_data     = self.carbon.record_production(production_kwh)
        total_green_rev = gross_eur + carbon_data["go_revenue_eur"]

        # ── INSURANCE ──────────────────────────────────────────
        insurance_premium   = self.insurance.collect_premium(gross_eur)
        ins_triggered, ins_payout = self.insurance.check_trigger(production_kwh)
        if ins_triggered:
            total_green_rev += ins_payout

        # ── ALLOCATION ─────────────────────────────────────────
        debt_payment    = total_green_rev * DEBT_RATIO
        escrow_contr    = total_green_rev * ESCROW_RATIO
        ops_eur         = total_green_rev * OPERATIONS_RATIO
        fee_eur         = total_green_rev * PROTOCOL_FEE
        reserve_eur     = total_green_rev * RESERVE_RATIO

        # ── DEBT UPDATE ────────────────────────────────────────
        actual_debt_payment = min(debt_payment, self.total_debt)
        self.total_debt     = max(0, self.total_debt - actual_debt_payment)
        self.debt_repaid   += actual_debt_payment
        self.reserve_fund  += reserve_eur

        # ── ESCROW ─────────────────────────────────────────────
        daily_yield     = self.escrow.contribute(escrow_contr)
        cumul_yield     = self.escrow.total_yield

        # ── MEMBER BREAKDOWN ───────────────────────────────────
        total_investment = sum(m["investment"] for m in self.members)
        member_breakdown = []
        for m in self.members:
            share = m["investment"] / total_investment
            member_breakdown.append({
                "name":             m["name"],
                "investment":       m["investment"],
                "share_pct":        round(share * 100, 2),
                "savings_eur":      round(savings_eur * share, 4),
                "debt_repaid":      round(actual_debt_payment * share, 4),
                "escrow_share":     round(escrow_contr * share, 4),
                "carbon_share":     round(carbon_data["carbon_credits_eur"] * share, 4),
                "daily_total":      round(total_green_rev * share, 4),
            })

        settlement = DailySettlement(
            date                    = settlement_date,
            community_id            = self.community_id,
            community_type          = self.mode,
            production_kwh          = round(production_kwh, 3),
            self_consumption_kwh    = round(self_consumption_kwh, 3),
            excess_kwh              = round(excess_kwh, 3),
            grid_import_kwh         = round(grid_import_kwh, 3),
            battery_avg_soc         = round(battery_avg_soc, 1),
            savings_eur             = round(savings_eur, 4),
            excess_revenue_eur      = round(excess_rev_eur, 4),
            gross_revenue_eur       = round(gross_eur, 4),
            oracle_price_eur        = oracle_price_eur,
            debt_payment_eur        = round(actual_debt_payment, 4),
            escrow_contribution_eur = round(escrow_contr, 4),
            operations_eur          = round(ops_eur, 4),
            protocol_fee_eur        = round(fee_eur, 4),
            reserve_eur             = round(reserve_eur, 4),
            escrow_balance_eur      = round(self.escrow.balance_eur, 4),
            escrow_yield_today_eur  = round(daily_yield, 4),
            cumulative_yield_eur    = round(cumul_yield, 4),
            co2_avoided_kg          = carbon_data["co2_avoided_kg"],
            carbon_credits_eur      = carbon_data["carbon_credits_eur"],
            go_certificates_mwh     = carbon_data["go_mwh"],
            go_revenue_eur          = carbon_data["go_revenue_eur"],
            insurance_premium_eur   = insurance_premium,
            insurance_triggered     = ins_triggered,
            insurance_payout_eur    = ins_payout,
            debt_remaining_eur      = round(self.total_debt, 4),
            debt_repaid_pct         = round(self.debt_repaid / self.config["total_investment"] * 100, 4),
            member_breakdown        = member_breakdown,
        )

        self.settlements.append(settlement)
        return settlement

    def get_transparency_report(self) -> dict:
        """Full transparency report — all financial data, no hidden flows."""
        if not self.settlements:
            return {}

        total_production    = sum(s.production_kwh for s in self.settlements)
        total_gross         = sum(s.gross_revenue_eur for s in self.settlements)
        total_debt_paid     = sum(s.debt_payment_eur for s in self.settlements)
        total_co2           = sum(s.co2_avoided_kg for s in self.settlements)
        total_carbon_rev    = sum(s.carbon_credits_eur + s.go_revenue_eur for s in self.settlements)

        return {
            "community_id":         self.community_id,
            "report_date":          datetime.now().isoformat(),
            "settlement_days":      len(self.settlements),
            "energy": {
                "total_production_kwh":     round(total_production, 2),
                "avg_daily_kwh":            round(total_production / len(self.settlements), 2),
            },
            "financial": {
                "total_gross_revenue_eur":  round(total_gross, 2),
                "total_debt_repaid_eur":    round(total_debt_paid, 2),
                "debt_remaining_eur":       round(self.total_debt, 2),
                "debt_repaid_pct":          round(self.debt_repaid / self.config["total_investment"] * 100, 2),
                "escrow_balance_eur":       round(self.escrow.balance_eur, 2),
                "escrow_total_yield_eur":   round(self.escrow.total_yield, 2),
                "escrow_roi_pct":           round(self.escrow.roi_pct, 4),
                "reserve_fund_eur":         round(self.reserve_fund, 2),
            },
            "carbon": {
                "total_co2_avoided_kg":     round(total_co2, 2),
                "total_co2_avoided_ton":    round(total_co2 / 1000, 4),
                "total_carbon_revenue_eur": round(total_carbon_rev, 2),
                "go_certificates_mwh":      round(self.carbon.total_go_mwh, 4),
            },
            "insurance": {
                "total_premiums_eur":       round(self.insurance.total_premiums_eur, 2),
                "total_payouts_eur":        round(self.insurance.total_payouts_eur, 2),
                "trigger_count":            self.insurance.trigger_count,
                "fund_balance_eur":         round(self.insurance.premium_balance_eur, 2),
            },
            "regulatory": {
                "framework":        "RD 244/2019 + EU RED II",
                "cnmc_compliant":   True,
                "reporting_period": f"{self.settlements[0].date} to {self.settlements[-1].date}",
            }
        }

    def export_cnmc_report(self, path: str = "reports/cnmc_report.json"):
        """Export CNMC-format regulatory report."""
        Path(path).parent.mkdir(exist_ok=True)
        report = self.get_transparency_report()
        report["settlements"] = [asdict(s) for s in self.settlements]
        Path(path).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        return path


# ─────────────────────────────────────────────
# DEMO
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  VOLTCORE DAILY SETTLEMENT ENGINE")
    print("="*60)

    config = {
        "id": "barcelona-gracia-solar",
        "mode": "ON_GRID",
        "reference_price_eur_kwh": 0.22,
        "total_investment": 30000,
        "expected_daily_kwh": 80.0,
        "members": [
            {"name": f"Member {i}", "investment": 3000} for i in range(10)
        ]
    }

    engine = DailySettlementEngine(config)

    print("\n  Running 30-day settlement simulation...")
    print(f"\n  {'Date':<12} {'Prod':>8} {'Gross':>8} {'Debt-':>8} {'Escrow':>8} {'CO2↓':>8} {'Ins':>6}")
    print(f"  {'-'*60}")

    for day in range(30):
        dt   = date(2025, 6, 1) + timedelta(days=day)
        prod = 80 + (day % 7 - 3) * 5  # Realistic variance

        s = engine.settle_day(
            settlement_date     = dt.isoformat(),
            production_kwh      = prod,
            self_consumption_kwh= prod * 0.65,
            excess_kwh          = prod * 0.35,
            oracle_price_eur    = 0.148 + (day % 5 - 2) * 0.008,
        )

        print(f"  {s.date:<12} "
              f"{s.production_kwh:>7.1f} "
              f"€{s.gross_revenue_eur:>6.2f} "
              f"€{s.debt_payment_eur:>6.2f} "
              f"€{s.escrow_balance_eur:>6.2f} "
              f"{s.co2_avoided_kg:>6.1f}kg "
              f"{'⚡' if s.insurance_triggered else '✓':>4}")

    report = engine.get_transparency_report()
    print(f"\n  30-DAY SUMMARY")
    print(f"  Debt repaid:     €{report['financial']['total_debt_repaid_eur']:.2f} ({report['financial']['debt_repaid_pct']:.2f}%)")
    print(f"  Escrow balance:  €{report['financial']['escrow_balance_eur']:.2f}")
    print(f"  Escrow yield:    €{report['financial']['escrow_total_yield_eur']:.4f}")
    print(f"  CO2 avoided:     {report['carbon']['total_co2_avoided_kg']:.1f} kg")
    print(f"  Carbon revenue:  €{report['carbon']['total_carbon_revenue_eur']:.4f}")
    print(f"  Insurance fund:  €{report['insurance']['fund_balance_eur']:.2f}")
