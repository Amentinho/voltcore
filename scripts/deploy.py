"""
VOLTCORE Deploy Script v0.1
============================
Deploys and initializes both communities on Solana devnet.
Run after: anchor build && anchor deploy

Usage:
  python3 scripts/deploy.py

Requirements:
  pip install solana anchorpy python-dotenv
"""

import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

DEVNET_RPC    = "https://api.devnet.solana.com"
PROGRAM_ID    = "VoLtC0reXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
WALLET_PATH   = os.path.expanduser("~/.config/solana/id.json")

COMMUNITIES = [
    {
        "id":               "barcelona-gracia-solar",
        "name":             "Barcelona Gràcia Solar",
        "mode":             "ON_GRID",
        "total_investment": 30_000,   # EUR
        "reference_price":  0.22,     # EUR/kWh
        "members": [
            {"name": "Ana García",   "investment": 3000},
            {"name": "Marc Puig",    "investment": 3000},
            {"name": "Laia Ferrer",  "investment": 3000},
            {"name": "Jordi Mas",    "investment": 3000},
            {"name": "Núria Vila",   "investment": 3000},
            {"name": "Pere Soler",   "investment": 3000},
            {"name": "Rosa Camps",   "investment": 3000},
            {"name": "Pau Ribas",    "investment": 3000},
            {"name": "Marta Costa",  "investment": 3000},
            {"name": "Tomàs Vidal",  "investment": 3000},
        ]
    },
    {
        "id":               "extremadura-valle-verde",
        "name":             "Extremadura Valle Verde",
        "mode":             "OFF_GRID",
        "total_investment": 40_000,   # EUR
        "reference_price":  0.20,     # EUR/kWh
        "members": [
            {"name": "Carmen López",   "investment": 5000},
            {"name": "Antonio Ruiz",   "investment": 5000},
            {"name": "María Sánchez",  "investment": 5000},
            {"name": "José Martínez",  "investment": 5000},
            {"name": "Isabel Jiménez", "investment": 5000},
            {"name": "Francisco Díaz", "investment": 5000},
            {"name": "Pilar González", "investment": 5000},
            {"name": "Manuel Moreno",  "investment": 5000},
        ]
    }
]

# ─────────────────────────────────────────────
# DEPLOY
# ─────────────────────────────────────────────

async def deploy():
    print("\n" + "="*60)
    print("  VOLTCORE DEPLOY SCRIPT")
    print("  Target: Solana Devnet")
    print("="*60)

    print(f"\n  📡 RPC:     {DEVNET_RPC}")
    print(f"  📋 Program: {PROGRAM_ID}")
    print(f"  👛 Wallet:  {WALLET_PATH}")

    # NOTE: Full deployment requires anchorpy + solana-py
    # Install: pip install anchorpy solana
    # This script shows the deployment flow for documentation purposes
    # On Wednesday (Mac with Anchor CLI), run: anchor deploy instead

    print("\n  ⚠️  Full deployment requires Anchor CLI (available on Mac Wednesday)")
    print("  📝 Deployment flow:")
    print()

    for i, community in enumerate(COMMUNITIES, 1):
        print(f"  [{i}] {community['name']} [{community['mode']}]")
        print(f"      Investment: €{community['total_investment']:,}")
        print(f"      Reference price: €{community['reference_price']}/kWh")
        print(f"      Members: {len(community['members'])}")
        print()
        for m in community['members']:
            share_pct = m['investment'] / community['total_investment'] * 100
            print(f"        • {m['name']:<20} €{m['investment']:,} ({share_pct:.1f}%)")
        print()

    print("  ✅ Communities ready for on-chain deployment")
    print()
    print("  Wednesday deployment commands:")
    print("  $ solana config set --url devnet")
    print("  $ solana airdrop 2")
    print("  $ anchor build")
    print("  $ anchor deploy")
    print("  $ python3 scripts/deploy.py --live")
    print()

    # Save deployment config
    config = {
        "program_id": PROGRAM_ID,
        "network": "devnet",
        "rpc": DEVNET_RPC,
        "communities": COMMUNITIES,
    }
    Path("scripts/deployment_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False)
    )
    print("  💾 Deployment config saved to scripts/deployment_config.json")


if __name__ == "__main__":
    asyncio.run(deploy())