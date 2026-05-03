"""
VOLTCORE Settlement Engine v0.1
================================
Handles both ON-GRID and OFF-GRID community energy settlement flows.
Calculates debt repayment, treasury contributions, and yield distribution.

On-Grid  → savings + excess energy revenue (oracle price) → debt → treasury
Off-Grid → savings only (reference price) → debt → treasury
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from datetime import datetime
import json


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────

DEBT_REPAYMENT_RATIO   = 0.60   # 60% of monthly revenue repays infrastructure debt
TREASURY_RATIO         = 0.15   # 15% goes to community green treasury
OPERATIONS_RATIO       = 0.25   # 25% covers ops + protocol fee
PROTOCOL_FEE_RATIO     = 0.05   # 5% of total revenue = VOLTCORE protocol fee

REFI_YIELD_RATE        = 0.06   # 6% annual yield on staked treasury (conservative)


# ─────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────

class CommunityMode(Enum):
    ON_GRID  = "ON_GRID"
    OFF_GRID = "OFF_GRID"


@dataclass
class Member:
    name: str
    wallet: str
    investment_eur: float
    share_pct: float = 0.0          # calculated on init
    debt_repaid_eur: float = 0.0
    yield_earned_eur: float = 0.0

    def debt_remaining(self, total_debt: float) -> float:
        return max(0, (self.share_pct / 100) * total_debt - self.debt_repaid_eur)


@dataclass
class Community:
    name: str
    mode: CommunityMode
    members: List[Member]
    total_investment_eur: float
    reference_price_eur_kwh: float  # local grid tariff (both modes use this for savings valuation)

    # On-grid only
    spot_price_eur_kwh: float = 0.0     # from oracle
    excess_kwh: float = 0.0

    # Computed on init
    total_debt_eur: float = field(init=False)
    treasury_eur: float = field(init=False)
    months_settled: int = field(init=False)

    def __post_init__(self):
        self.total_debt_eur = self.total_investment_eur
        self.treasury_eur = 0.0
        self.months_settled = 0
        self._assign_shares()

    def _assign_shares(self):
        total = sum(m.investment_eur for m in self.members)
        for m in self.members:
            m.share_pct = round((m.investment_eur / total) * 100, 4)

    @property
    def debt_fully_repaid(self) -> bool:
        return self.total_debt_eur <= 0


@dataclass
class SettlementInput:
    """Raw energy data for one settlement period (monthly)"""
    period: str                         # e.g. "2025-06"
    production_kwh: float
    self_consumption_kwh: float
    excess_kwh: float                   # 0 for off-grid
    oracle_spot_price: Optional[float]  # None for off-grid


@dataclass
class SettlementResult:
    period: str
    mode: CommunityMode
    gross_revenue_eur: float
    savings_eur: float
    excess_revenue_eur: float
    debt_repayment_eur: float
    treasury_contribution_eur: float
    operations_eur: float
    protocol_fee_eur: float
    total_debt_remaining: float
    treasury_balance: float
    monthly_refi_yield: float
    member_breakdown: List[dict]
    debt_fully_repaid: bool


# ─────────────────────────────────────────────
# ORACLE (mock — replace with Chainlink on-chain)
# ─────────────────────────────────────────────

class OracleMock:
    """
    Simulates Chainlink price feed for REE PVPC spot price.
    In production: reads from Solana on-chain Chainlink feed.
    """
    BASE_PRICE = 0.15  # €/kWh baseline

    @staticmethod
    def get_spot_price(period: str) -> float:
        """Returns simulated hourly average spot price for the period."""
        import hashlib
        seed = int(hashlib.md5(period.encode()).hexdigest(), 16) % 100
        variance = (seed - 50) / 1000  # ±5% variance
        price = OracleMock.BASE_PRICE + variance
        print(f"  [Oracle] REE spot price for {period}: €{price:.4f}/kWh")
        return round(price, 4)


# ─────────────────────────────────────────────
# SETTLEMENT ENGINE
# ─────────────────────────────────────────────

class SettlementEngine:

    def __init__(self, community: Community):
        self.community = community
        self.oracle = OracleMock()

    def settle(self, data: SettlementInput) -> SettlementResult:
        c = self.community
        c.months_settled += 1

        print(f"\n{'='*60}")
        print(f"  VOLTCORE SETTLEMENT — {data.period}")
        print(f"  Community: {c.name} [{c.mode.value}]")
        print(f"{'='*60}")

        # ── 1. CALCULATE GROSS REVENUE ──────────────────────────

        savings_eur = data.self_consumption_kwh * c.reference_price_eur_kwh

        if c.mode == CommunityMode.ON_GRID:
            spot = data.oracle_spot_price or self.oracle.get_spot_price(data.period)
            excess_revenue_eur = data.excess_kwh * spot
        else:
            spot = 0.0
            excess_revenue_eur = 0.0  # off-grid has no grid to sell to

        gross_revenue_eur = savings_eur + excess_revenue_eur

        print(f"\n  📊 ENERGY DATA")
        print(f"     Production:       {data.production_kwh:.1f} kWh")
        print(f"     Self consumed:    {data.self_consumption_kwh:.1f} kWh")
        print(f"     Excess:           {data.excess_kwh:.1f} kWh")
        print(f"\n  💶 REVENUE BREAKDOWN")
        print(f"     Savings:          €{savings_eur:.2f}")
        print(f"     Excess revenue:   €{excess_revenue_eur:.2f}")
        print(f"     Gross total:      €{gross_revenue_eur:.2f}")

        # ── 2. ALLOCATE REVENUE ─────────────────────────────────

        if not c.debt_fully_repaid:
            debt_repayment_eur = round(gross_revenue_eur * DEBT_REPAYMENT_RATIO, 2)
        else:
            debt_repayment_eur = 0.0  # debt done — all surplus goes to treasury + ops

        treasury_contribution_eur = round(gross_revenue_eur * TREASURY_RATIO, 2)
        protocol_fee_eur          = round(gross_revenue_eur * PROTOCOL_FEE_RATIO, 2)
        operations_eur            = round(gross_revenue_eur * OPERATIONS_RATIO - protocol_fee_eur, 2)

        print(f"\n  🏦 ALLOCATION")
        print(f"     Debt repayment:   €{debt_repayment_eur:.2f} ({DEBT_REPAYMENT_RATIO*100:.0f}%)")
        print(f"     Treasury:         €{treasury_contribution_eur:.2f} ({TREASURY_RATIO*100:.0f}%)")
        print(f"     Operations:       €{operations_eur:.2f}")
        print(f"     Protocol fee:     €{protocol_fee_eur:.2f}")

        # ── 3. UPDATE DEBT ──────────────────────────────────────

        c.total_debt_eur = max(0, c.total_debt_eur - debt_repayment_eur)

        # ── 4. UPDATE TREASURY + REFI YIELD ────────────────────

        c.treasury_eur += treasury_contribution_eur
        monthly_refi_yield = round(c.treasury_eur * (REFI_YIELD_RATE / 12), 2)
        c.treasury_eur += monthly_refi_yield

        print(f"\n  🌱 TREASURY")
        print(f"     Contribution:     €{treasury_contribution_eur:.2f}")
        print(f"     ReFi yield:       €{monthly_refi_yield:.2f} ({REFI_YIELD_RATE*100:.0f}% APY)")
        print(f"     Treasury balance: €{c.treasury_eur:.2f}")
        print(f"\n  📉 DEBT STATUS")
        print(f"     Remaining debt:   €{c.total_debt_eur:.2f}")
        print(f"     Debt repaid:      {'✅ COMPLETE' if c.debt_fully_repaid else f'~{c.total_debt_eur/max(debt_repayment_eur,1):.0f} months remaining'}")

        # ── 5. MEMBER BREAKDOWN ─────────────────────────────────

        member_breakdown = []
        for m in c.members:
            member_debt_repaid = round(debt_repayment_eur * (m.share_pct / 100), 2)
            member_treasury    = round(treasury_contribution_eur * (m.share_pct / 100), 2)
            member_yield       = round(monthly_refi_yield * (m.share_pct / 100), 2)
            member_savings     = round(savings_eur * (m.share_pct / 100), 2)

            m.debt_repaid_eur += member_debt_repaid
            m.yield_earned_eur += member_yield

            member_breakdown.append({
                "name":             m.name,
                "wallet":           m.wallet,
                "share_pct":        m.share_pct,
                "savings_eur":      member_savings,
                "debt_repaid_eur":  member_debt_repaid,
                "treasury_eur":     member_treasury,
                "yield_eur":        member_yield,
                "debt_remaining":   round(m.debt_remaining(c.total_investment_eur), 2),
            })

        print(f"\n  👥 MEMBER BREAKDOWN")
        for mb in member_breakdown:
            print(f"     {mb['name']:<20} share: {mb['share_pct']:.1f}% | "
                  f"savings: €{mb['savings_eur']:.2f} | "
                  f"debt repaid: €{mb['debt_repaid_eur']:.2f} | "
                  f"yield: €{mb['yield_eur']:.2f}")

        return SettlementResult(
            period=data.period,
            mode=c.mode,
            gross_revenue_eur=round(gross_revenue_eur, 2),
            savings_eur=round(savings_eur, 2),
            excess_revenue_eur=round(excess_revenue_eur, 2),
            debt_repayment_eur=debt_repayment_eur,
            treasury_contribution_eur=treasury_contribution_eur,
            operations_eur=operations_eur,
            protocol_fee_eur=protocol_fee_eur,
            total_debt_remaining=round(c.total_debt_eur, 2),
            treasury_balance=round(c.treasury_eur, 2),
            monthly_refi_yield=monthly_refi_yield,
            member_breakdown=member_breakdown,
            debt_fully_repaid=c.debt_fully_repaid,
        )

    def simulate_months(self, months: int, input_template: SettlementInput) -> List[SettlementResult]:
        """Run multi-month simulation to project debt payoff and yield."""
        results = []
        for i in range(months):
            year  = 2025 + (i // 12)
            month = (i % 12) + 1
            period = f"{year}-{month:02d}"
            data = SettlementInput(
                period=period,
                production_kwh=input_template.production_kwh,
                self_consumption_kwh=input_template.self_consumption_kwh,
                excess_kwh=input_template.excess_kwh,
                oracle_spot_price=input_template.oracle_spot_price,
            )
            result = self.settle(data)
            results.append(result)
            if self.community.debt_fully_repaid and i > 0:
                print(f"\n  🎉 DEBT FULLY REPAID after {i+1} months!")
                break
        return results


# ─────────────────────────────────────────────
# DEMO — RUN BOTH FLOWS
# ─────────────────────────────────────────────

def demo_on_grid():
    print("\n" + "🔌 "*20)
    print("ON-GRID DEMO — Barcelona Gràcia Solar Community")
    print("🔌 "*20)

    members = [
        Member("Ana García",     "wallet_ana",     3000),
        Member("Marc Puig",      "wallet_marc",    3000),
        Member("Laia Ferrer",    "wallet_laia",    3000),
        Member("Jordi Mas",      "wallet_jordi",   3000),
        Member("Núria Vila",     "wallet_nuria",   3000),
        Member("Pere Soler",     "wallet_pere",    3000),
        Member("Rosa Camps",     "wallet_rosa",    3000),
        Member("Pau Ribas",      "wallet_pau",     3000),
        Member("Marta Costa",    "wallet_marta",   3000),
        Member("Tomàs Vidal",    "wallet_tomas",   3000),
    ]

    community = Community(
        name="Barcelona Gràcia Solar",
        mode=CommunityMode.ON_GRID,
        members=members,
        total_investment_eur=30000,
        reference_price_eur_kwh=0.22,
        spot_price_eur_kwh=0.15,
        excess_kwh=800,
    )

    engine = SettlementEngine(community)

    # Single month settlement
    result = engine.settle(SettlementInput(
        period="2025-06",
        production_kwh=2400,
        self_consumption_kwh=1600,
        excess_kwh=800,
        oracle_spot_price=0.152,
    ))

    return result


def demo_off_grid():
    print("\n" + "🌿 "*20)
    print("OFF-GRID DEMO — Extremadura Valle Verde Community")
    print("🌿 "*20)

    members = [
        Member("Carmen López",   "wallet_carmen",  5000),
        Member("Antonio Ruiz",   "wallet_antonio", 5000),
        Member("María Sánchez",  "wallet_maria",   5000),
        Member("José Martínez",  "wallet_jose",    5000),
        Member("Isabel Jiménez", "wallet_isabel",  5000),
        Member("Francisco Díaz", "wallet_paco",    5000),
        Member("Pilar González", "wallet_pilar",   5000),
        Member("Manuel Moreno",  "wallet_manuel",  5000),
    ]

    community = Community(
        name="Extremadura Valle Verde",
        mode=CommunityMode.OFF_GRID,
        members=members,
        total_investment_eur=40000,
        reference_price_eur_kwh=0.20,
    )

    engine = SettlementEngine(community)

    result = engine.settle(SettlementInput(
        period="2025-06",
        production_kwh=3000,
        self_consumption_kwh=3000,
        excess_kwh=0,
        oracle_spot_price=None,
    ))

    return result


def demo_projection():
    print("\n" + "📈 "*20)
    print("12-MONTH PROJECTION — Barcelona Gràcia Solar")
    print("📈 "*20)

    members = [Member(f"Member {i}", f"wallet_{i}", 3000) for i in range(10)]
    community = Community(
        name="Barcelona Gràcia Solar",
        mode=CommunityMode.ON_GRID,
        members=members,
        total_investment_eur=30000,
        reference_price_eur_kwh=0.22,
    )

    engine = SettlementEngine(community)
    template = SettlementInput(
        period="template",
        production_kwh=2400,
        self_consumption_kwh=1600,
        excess_kwh=800,
        oracle_spot_price=0.15,
    )

    results = engine.simulate_months(12, template)

    print(f"\n  📊 12-MONTH SUMMARY")
    print(f"  {'Period':<10} {'Revenue':>10} {'Debt Left':>12} {'Treasury':>10} {'ReFi Yield':>12}")
    print(f"  {'-'*56}")
    for r in results:
        print(f"  {r.period:<10} €{r.gross_revenue_eur:>8.2f} "
              f"  €{r.total_debt_remaining:>9.2f} "
              f"  €{r.treasury_balance:>8.2f} "
              f"  €{r.monthly_refi_yield:>10.2f}")


if __name__ == "__main__":
    demo_on_grid()
    demo_off_grid()
    demo_projection()