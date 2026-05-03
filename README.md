# ⚡ VOLTCORE

> **The first AI-powered settlement layer for community energy cooperatives — built on Solana.**

[![Solana](https://img.shields.io/badge/Solana-Devnet-9945FF?logo=solana)](https://solana.com)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Hackathon](https://img.shields.io/badge/Colosseum-Frontier%202025-orange)](https://colosseum.com/frontier)

---

## The Problem

Spain has **2,400+ registered energy communities** sharing solar power with zero digital infrastructure. They settle accounts manually on spreadsheets, wait quarterly for payments, and trust a cooperative manager with their money.

The EU Energy Communities Directive requires transparent, democratic governance. Nobody has built the infrastructure to make that real — until now.

---

## What VOLTCORE Does

VOLTCORE is an AI agent on Solana that:

- 📡 **Reads** official smart meter data (SIPS) and IoT inverter APIs automatically
- 🧠 **Calculates** fair energy allocation between members every 15 minutes
- ⚡ **Settles** payments on-chain in under 1 second — no manager, no disputes
- 📈 **Compounds** community surplus into ReFi yield automatically
- 🔗 **Records** every kilowatt and every euro immutably on Solana

---

## Two Flows

### 🔌 On-Grid Communities
For urban neighborhoods connected to the national grid.

```
Solar production → Self consumption (savings) + Excess sold to grid
                                                      ↓
                                          Chainlink oracle → REE spot price
                                                      ↓
                                          Combined revenue → Debt repayment
                                                           → Community treasury
                                                           → ReFi yield
```

### 🌿 Off-Grid Communities
For rural villages, islands, and remote areas.

```
Solar + Battery → 100% self consumption (savings)
                                    ↓
                          Reference price valuation
                                    ↓
                          Savings → Debt repayment
                                  → Community treasury
                                  → ReFi yield
```

---

## Revenue Flows

| Stream | On-Grid | Off-Grid |
|--------|---------|----------|
| Energy savings | ✅ Grid price avoided | ✅ Full energy cost avoided |
| Excess energy | ✅ Sold at REE spot price (oracle) | ❌ Stored in battery |
| ReFi yield | ✅ 6% APY on treasury | ✅ 6% APY on treasury |

**Allocation per settlement:**
- 60% → Infrastructure debt repayment
- 15% → Community green treasury (staked for ReFi yield)
- 20% → Operations
- 5%  → VOLTCORE protocol fee

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Blockchain | Solana (Anchor framework) |
| AI Agent | Python — settlement + anomaly detection |
| Price Oracle | Chainlink → REE PVPC spot price |
| On-Grid Data | SIPS smart meter API (Spain) |
| Off-Grid Data | SolarEdge / Shelly IoT inverter APIs |
| Solar Forecasting | PVGIS (EU Solar Atlas — free) |
| Frontend | Next.js dashboard |
| ReFi Yield | Sunrise Stake / Solana stablecoin pools |

---

## Smart Contracts (Solana / Anchor)

```
programs/voltcore/
├── CommunityRegistry     — initialize, add members, set mode (ON_GRID | OFF_GRID)
├── SettlementEngine      — record energy data, calculate allocation, trigger payments
├── TreasuryManager       — stake to ReFi, distribute yield, fund new communities
└── InvestmentNFT         — mint on join, track debt repaid, burn when debt = 0
```

---

## Project Structure

```
voltcore/
├── programs/           # Solana smart contracts (Rust/Anchor)
│   └── voltcore/
│       └── src/
│           └── lib.rs
├── app/                # Next.js frontend dashboard
│   ├── components/
│   └── pages/
├── agent/              # AI settlement agent (Python)
│   ├── settlement.py   # Core allocation algorithm ← START HERE
│   ├── oracle.py       # Chainlink price feed integration
│   ├── meter.py        # SIPS + IoT data ingestion
│   └── mock/           # Simulated data for demo
│       ├── on_grid_mock.json
│       └── off_grid_mock.json
├── scripts/            # Deploy + test scripts
└── README.md
```

---

## Quickstart

```bash
# Clone
git clone https://github.com/Amentinho/voltcore.git
cd voltcore

# Run the settlement engine (no Solana needed)
pip install -r requirements.txt
python3 agent/settlement.py

# Deploy to Solana devnet
anchor build
anchor deploy --provider.cluster devnet
```

---

## The Numbers

**On-Grid — 10 families, Barcelona (€30,000 invested)**
- Monthly revenue: ~€473 (savings + excess energy)
- Debt repaid monthly: €284
- Treasury growth: €71/month compounding at 6% APY
- Debt-free in: ~94 months → pure yield from that point

**Off-Grid — 8 families, Extremadura (€40,000 invested)**
- Monthly savings: €600
- Debt repaid monthly: €360
- Treasury growth: €90/month compounding at 6% APY
- Debt-free in: ~111 months → pure yield from that point

---

## Why Solana

- **Speed**: Settlement every 15 minutes requires sub-second finality
- **Cost**: €0.00025/transaction — viable for energy micropayments
- **Oracle**: Chainlink native on Solana for REE price feeds
- **Transparency**: Every member audits every transaction in real time
- **DAO**: On-chain governance for treasury investment decisions

---

## Why Now

- 🇪🇺 EU Energy Communities Directive (2023) — legally mandates democratic governance
- 🇪🇸 Spain: 2,400+ registered communities, zero digital infrastructure
- 🌍 EU target: 10,000 energy communities by 2030
- ☀️ Spain: 300 sunny days/year — highest solar potential in continental Europe

---

## Team

**Andrea** — Program Manager & Founder  
7+ years in AI/ML and Web3 program delivery. Renewable Energy Engineering MSc.  
Previously: VoltGrid (Mantle Hackathon), GreenStake (ETHGlobal winner), VirtusGreen.  
Based in Barcelona 🇪🇸

---

## Hackathon

Built for the **Colosseum Frontier Hackathon** — La Familia track (Spain 🇪🇸)  
Submitted on [Colosseum](https://colosseum.com/frontier) and Superteam Earn.

---

*VOLTCORE — Energy owned by the people who power it.*
