# ⚡ VOLTCORE — Community Energy Protocol

> **Colosseum Frontier Hackathon 2026**  
> On-chain infrastructure for renewable energy communities on Solana

---

## What is VOLTCORE?

VOLTCORE is a Solana smart contract protocol that enables **collective solar energy communities** to govern shared infrastructure, settle energy production on-chain, distribute yield to members, and trade verified carbon credits — all transparently and automatically.

Built for the Spanish market under **RD 244/2019** (collective self-consumption) and **EU RED II** (Renewable Energy Communities Directive).

---

## Live Demo

- **Program ID (devnet):** `FRj8srGr4EvzhFgEsQ6x5iHYM9zQYmmuUZApAAy1D2p4`
- **Dashboard:** `http://localhost:8080/dashboard_v4.html`
- **Network:** Solana Devnet

---

## Architecture

```
voltcore/
├── programs/voltcore/src/lib.rs    # Anchor smart contract
├── dashboard_v4.html               # Full-stack dashboard (single file)
├── Anchor.toml                     # Anchor config
└── keypair.json                    # Program upgrade authority
```

### Smart Contract (`lib.rs`)

Five on-chain instructions:

| Instruction | Description |
|---|---|
| `initialize_community` | Creates a community PDA with name, mode, investment, reference price |
| `add_member` | Registers a member PDA with investment share in basis points |
| `record_settlement` | Records an energy settlement period — production, self-consumption, excess, oracle price |
| `distribute_yield` | Distributes treasury yield to a registered member PDA |
| `stake_to_refi` | Stakes treasury to ReFi pool (Sunrise Stake integration stub) |

### Account Structure

```rust
Community {
    authority: Pubkey,         // Community creator
    name: String,              // Community name (used in PDA seed)
    mode: CommunityMode,       // OnGrid | OffGrid
    total_investment: u64,     // Total CAPEX in micro-EUR
    total_debt: u64,           // Remaining infrastructure debt
    total_repaid: u64,         // Cumulative debt repaid
    treasury_balance: u64,     // On-chain escrow balance
    total_yield: u64,          // Cumulative yield distributed
    reference_price: u64,      // Grid price in micro-EUR/kWh
    member_count: u8,
    settlement_count: u64,
    bump: u8,
}

MemberAccount {
    community: Pubkey,
    wallet: Pubkey,
    investment: u64,
    share_bps: u64,            // Basis points (10000 = 100%)
    debt_repaid: u64,
    yield_earned: u64,
    bump: u8,
}
```

### PDA Seeds

```
Community:  ["community", authority_pubkey, community_name_bytes]
Member:     ["member", community_pda, member_wallet_pubkey]
```

---

## Dashboard Features

### Protocol Overview
- Real-time energy production simulation (PVGIS-based solar physics)
- Live REE oracle price with peak/valley/flat periods
- Protocol KPIs: communities, energy produced, grid cost, escrow, CO₂, debt repaid
- Full EN/ES translation with persistent language toggle

### Community Management
- Deploy new communities to Solana devnet in 6 steps
- Communities persist across sessions via `localStorage`
- Expand any community to see energy flow, financials, members, debt repayment
- On-grid (grid-connected) and off-grid (battery) modes

### On-Chain Actions (per community)
1. **⚡ Record Settlement** — submits `record_settlement` with live simulation data
2. **🏦 Deposit Escrow** — raw SOL transfer to community PDA vault
3. **🌿 Mint Carbon Credits** — records credits via Solana Memo Program with JSON payload
4. **💸 Distribute Yield** — batch yield distribution to registered members
5. **👤 Add Member** — registers new member PDA on-chain

### Carbon Credits Marketplace
- On-chain registry of all minted credits (community, kWh, kg CO₂, ETS value, GO value)
- Inline marketplace modal — no popup blocker issues
- Buy flow: credit marked sold → sale value flows to community escrow fund
- EU ETS pricing (€65/tonne) + GO certificates (€2.50/MWh)

### Escrow Fund Page
- Total escrow breakdown: solar revenue (15%) + carbon sales + direct deposits
- Per-community and per-member escrow share
- Full transaction log with Solana Explorer links

### Financial Transparency
- Revenue allocation: 55% debt / 15% escrow / 20% operations / 2% insurance / 5% protocol
- 5-year escrow projection at 5.5% APY
- Member-level savings, escrow, and carbon revenue breakdown

### Regulatory Compliance
- Spain: RD 244/2019, RD 23/2020, CNMC reporting
- EU: RED II (2018/2001), EU ETS, Guarantees of Origin (GO)
- Parametric insurance model (trigger < 70% expected production)

---

## Build & Deploy

### Prerequisites
```bash
# Rust + Anchor
rustup install 1.85
cargo install --git https://github.com/coral-xyz/anchor anchor-cli --locked
solana-install init 1.18.x

# Set devnet
solana config set --url devnet
solana airdrop 2
```

### Build & Deploy Program
```bash
cd programs/voltcore

# Build
cargo build-sbf

# Deploy (first time)
solana program deploy target/deploy/voltcore.so --url devnet

# Upgrade (with keypair authority)
solana program deploy target/deploy/voltcore.so \
  --program-id FRj8srGr4EvzhFgEsQ6x5iHYM9zQYmmuUZApAAy1D2p4 \
  --upgrade-authority keypair.json \
  --url devnet
```

### Run Dashboard
```bash
# From project root
npx http-server . -p 8080

# Open
open http://localhost:8080/dashboard_v4.html
```

---

## End-to-End Demo Flow

1. Connect Phantom wallet (devnet)
2. **+ New Community** → fill 6 steps → Deploy to Solana → TX confirmed
3. Expand community → **⚡ Record Settlement** → on-chain settlement recorded
4. **🌿 Mint Carbon Credits** → Memo TX → credits appear in Carbon tab
5. **Carbon tab** → Open Marketplace → Buy credit → value flows to escrow
6. **🏦 Deposit Escrow** → SOL transfer to community PDA
7. **👤 Add Member** → member PDA created on-chain
8. **💸 Distribute Yield** → batch yield to all members
9. **Escrow tab** → full breakdown of all fund flows

---

## Technical Decisions

| Decision | Rationale |
|---|---|
| Single HTML file dashboard | Zero-dependency deployment, easy demo sharing |
| Raw `DataView` for SOL transfers | Avoids `Buffer` polyfill conflicts with Phantom's lockdown-install.js |
| Solana Memo Program for carbon credits | No custom token mint needed for hackathon demo — verifiable on-chain record |
| localStorage persistence | Communities survive page refresh without backend |
| `applyLang()` called every tick | Translations persist through DOM re-renders |
| PVGIS solar physics simulation | Realistic production curves based on real Spanish irradiance data |

---

## Known Limitations (Hackathon Scope)

- Carbon credits use Memo Program (not a full SPL token mint)
- `distribute_yield` requires member to have been registered via `add_member` with the same wallet
- Escrow APY is simulated in frontend (not enforced on-chain)
- Insurance payouts are UI-only (not triggered by oracle)
- `stake_to_refi` is a stub (Sunrise Stake CPI not implemented)

---

## Team

Built by **Andrea Amenta** ([@Amentinho](https://github.com/Amentinho))  
Barcelona · May 2026

---

## License

MIT
