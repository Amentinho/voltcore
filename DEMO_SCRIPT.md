# VOLTCORE — Demo Script & Video Submission Guide

## The Story (30 seconds)

> "In Spain, 2.5 million households could form solar communities under RD 244/2019 — 
> but there's no open infrastructure to govern them transparently.
> VOLTCORE puts the entire community lifecycle on Solana."

---

## Video Structure (3 minutes max)

### 00:00–00:20 — HOOK
**Screen:** Terminal showing the deployed program  
**Say:** *"This is a live Solana devnet program. Every energy settlement, every carbon credit, every yield distribution — on-chain, transparent, immutable."*

Show:
```
Program Id: FRj8srGr4EvzhFgEsQ6x5iHYM9zQYmmuUZApAAy1D2p4
```

---

### 00:20–00:50 — THE PROBLEM
**Screen:** Switch to dashboard — ES mode, empty state  
**Say:** *"Spain has 20,000+ solar installations that could operate as community energy systems. But today there's no transparent way to track production, settle revenue, or distribute yield to members. Banks don't trust informal communities. Members can't verify their share."*

**Action:** Toggle EN → ES to show bilingual support

---

### 00:50–01:30 — CREATE A COMMUNITY
**Screen:** Click "+ Nueva Comunidad"  
**Say:** *"Let's deploy a real community. Six steps — and it hits Solana."*

**Actions (do this fast, have values pre-filled):**
1. Name: `Comunidad Solar Gracia`
2. Type: On-Grid, Barcelona
3. 10 households, €0.22 reference price
4. 48 panels × 400Wp
5. Panel cost €0.35/Wp, bank loan 4.5% / 10 years
6. Add 3 members: Ana García, Marc Puig, Laia Ferrer — show wallet generation
7. Click "⚡ Deploy to Solana" — Phantom popup appears
8. Confirm → **show the Solana Explorer with SUCCESS**

**Say:** *"That's a real on-chain account. The community's name, investment, member structure — all in a PDA on Solana devnet."*

---

### 01:30–02:00 — LIVE OPERATIONS
**Screen:** Back on dashboard, community expanded  
**Say:** *"Now the AI simulation runs. Production, self-consumption, grid exports — all live. Let's record a settlement on-chain."*

**Actions:**
1. Click **⚡ Record Settlement** — values are pre-filled from the simulation
2. Confirm in Phantom
3. **Show Explorer TX** — "Instruction 0: record_settlement — FINALIZED"
4. Click **🌿 Mint Carbon Credits** — confirm
5. **Show Carbon tab** — credit appears in the on-chain registry

**Say:** *"Every kWh produced generates a verifiable carbon credit. 0.18 kg CO₂ avoided per kWh. Recorded with a signed transaction, verifiable by anyone."*

---

### 02:00–02:30 — CARBON MARKETPLACE + ESCROW
**Screen:** Carbon tab → Open Marketplace  
**Say:** *"Those credits can now be traded. EU ETS price €65/tonne. GO certificates €2.50/MWh."*

**Actions:**
1. Open marketplace modal
2. Click **BUY CREDIT BUNDLE** on a credit
3. Switch to **Escrow tab**
4. **Show:** sale value appeared in escrow fund, with transaction log

**Say:** *"The proceeds go directly to the community escrow fund. Members see their share in real time. 5.5% APY on idle funds."*

---

### 02:30–03:00 — CLOSING
**Screen:** Regulatory tab  
**Say:** *"VOLTCORE is built for the Spanish market — RD 244/2019, EU RED II, CNMC reporting. Everything you need to run a compliant energy community, on-chain."*

**Final screen:** Program ID on Explorer, "FINALIZED" in green  
**Say:** *"Open source, single program, one dashboard. VOLTCORE — community energy, on Solana."*

---

## Pre-Recording Checklist

```
□ Phantom connected on devnet
□ Devnet SOL balance > 1 SOL  (airdrop if needed: solana airdrop 2 --url devnet)
□ http-server running on port 8080
□ localStorage cleared (fresh demo): localStorage.clear() in browser console
□ Screen recording software ready (QuickTime / OBS)
□ Microphone tested
□ Browser zoom at 100%
□ Close all notifications (macOS: Do Not Disturb ON)
□ Use Firefox (Phantom works better, no popup issues)
```

---

## Recording Tips

- **Do NOT stop recording between steps** — continuous flow is more impressive
- **Pause 1 second on each confirmed TX** — let the Explorer URL be visible
- **Keep the terminal open in a corner** — shows you're running real infra
- For the Explorer shots, **zoom in** on the "Result: Success" badge
- Talk while clicking — don't let there be silence
- If a TX fails: breathe, say "let me retry that" — it's live blockchain, judges expect it

---

## B-roll ideas (overlay on explanations)

- Spanish solar panels on rooftops (stock footage)
- Real-time chart of REE electricity prices
- Barcelona aerial shot while saying "RD 244/2019"

---

## Submission Text (copy-paste)

**Project name:** VOLTCORE  
**Tagline:** On-chain infrastructure for collective solar energy communities  
**Track:** DeFi / RWA / DePIN  
**Tech:** Solana · Anchor 0.29 · Rust 1.85 · Vanilla JS

**Description:**
VOLTCORE is a Solana Anchor program that powers the full lifecycle of a renewable energy community — from on-chain deployment and member registration, to energy settlement, carbon credit minting, yield distribution, and escrow fund management. Built for the Spanish market under RD 244/2019 and EU RED II. Includes a full-stack single-file dashboard with live solar physics simulation, PVGIS-based production estimates, REE oracle price feed, and a carbon credits marketplace. All five instructions are live and tested on Solana devnet.

**Links:**
- GitHub: https://github.com/Amentinho/voltcore
- Program: https://explorer.solana.com/address/FRj8srGr4EvzhFgEsQ6x5iHYM9zQYmmuUZApAAy1D2p4?cluster=devnet
