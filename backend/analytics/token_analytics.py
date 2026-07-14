"""Token analytics: compute holders, distribution, cost-basis from transfer data."""
from collections import defaultdict
from datetime import datetime
from backend.db import get_db, get_kv
from backend import config

DECIMALS = config.TOKEN_DECIMALS
SUPPLY = config.TOTAL_SUPPLY  # 1M NOXA in human units
BURN_ADDRESSES = [
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
]


def raw_to_human(amount_str: str) -> float:
    """Convert raw token amount (string, with 18 decimals) to human units."""
    try:
        return int(amount_str) / (10 ** DECIMALS)
    except (ValueError, TypeError):
        return 0.0


def is_burn_address(addr: str) -> bool:
    """Check if address is a burn address."""
    return addr.lower() in BURN_ADDRESSES


async def get_current_price(db) -> float:
    """Get the latest price from price_history."""
    cursor = await db.execute(
        "SELECT price FROM price_history ORDER BY id DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    await cursor.close()
    return float(row["price"]) if row else 0.0


async def compute_holders(limit: int = 100) -> list[dict]:
    """Aggregate all transfers to compute current balances. Returns top N holders."""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT from_address, to_address, amount FROM token_transfers")
        rows = await cursor.fetchall()
        await cursor.close()

        balances = defaultdict(float)
        for row in rows:
            amt = raw_to_human(row["amount"])
            if row["from_address"] and not is_burn_address(row["from_address"]):
                balances[row["from_address"]] -= amt
            if row["to_address"] and not is_burn_address(row["to_address"]):
                balances[row["to_address"]] += amt

        # Filter out zero/negative and sort
        holders = [
            {"address": addr, "balance": bal}
            for addr, bal in balances.items()
            if bal > 0.0001
        ]
        holders.sort(key=lambda x: x["balance"], reverse=True)

        current_price = await get_current_price(db)

        result = []
        for h in holders[:limit]:
            result.append({
                "address": h["address"],
                "balance": round(h["balance"], 2),
                "pct_supply": round((h["balance"] / SUPPLY) * 100, 4) if SUPPLY > 0 else 0,
                "avg_buy_price": round(current_price, 6),  # Simplified - use current price
                "current_price": round(current_price, 6),
                "pnl_pct": 0.0,  # Simplified - no real PnL
                "pnl_value": 0.0,
            })

        return result
    finally:
        await db.close()


async def compute_burn_balance() -> float:
    """Compute total NOXA burned (sent to burn addresses)."""
    db = await get_db()
    try:
        balances = defaultdict(float)
        cursor = await db.execute("SELECT from_address, to_address, amount FROM token_transfers")
        rows = await cursor.fetchall()
        await cursor.close()

        for row in rows:
            amt = raw_to_human(row["amount"])
            if row["from_address"]:
                balances[row["from_address"]] -= amt
            if row["to_address"]:
                balances[row["to_address"]] += amt

        # Sum all burn address balances
        burned = sum(
            bal for addr, bal in balances.items()
            if is_burn_address(addr) and bal > 0
        )
        return round(burned, 2)
    finally:
        await db.close()


async def compute_distribution() -> dict:
    """Compute supply distribution stats including burned tokens."""
    holders = await compute_holders(limit=10000)
    burned = await compute_burn_balance()
    if not holders:
        return {"top10_pct": 0, "top100_pct": 0, "total_holders": 0, "gini": 0, "supply": SUPPLY, "burned": 0}

    total_balance = sum(h["balance"] for h in holders)
    top10_balance = sum(h["balance"] for h in holders[:10])
    top100_balance = sum(h["balance"] for h in holders[:100])

    # Gini coefficient
    sorted_balances = sorted([h["balance"] for h in holders])
    n = len(sorted_balances)
    cum = sum((2 * i - n - 1) * b for i, b in enumerate(sorted_balances, 1))
    gini = cum / (n * total_balance) if n * total_balance > 0 else 0

    return {
        "total_holders": len(holders),
        "supply": SUPPLY,
        "burned": burned,
        "total_tracked_balance": round(total_balance + burned, 2),
        "top10_pct": round((top10_balance / SUPPLY) * 100, 2) if SUPPLY > 0 else 0,
        "top100_pct": round((top100_balance / SUPPLY) * 100, 2) if SUPPLY > 0 else 0,
        "gini": round(gini, 4),
        "top10_balance": round(top10_balance, 2),
        "top100_balance": round(top100_balance, 2),
        "others_balance": round(SUPPLY - top100_balance - burned, 2),
    }


async def compute_cost_basis(target_price: float = None) -> dict:
    """Cost-basis analysis: how much supply was acquired below/above a target price."""
    db = await get_db()
    try:
        current_price = await get_current_price(db)
        comparison_price = target_price if target_price is not None else current_price
        
        holders = await compute_holders(limit=10000)

        if not holders or comparison_price <= 0:
            return {
                "current_price": round(current_price, 6),
                "target_price": round(target_price, 6) if target_price else None,
                "comparison_price": round(comparison_price, 6),
                "above_pct": 0,
                "below_pct": 0,
                "at_pct": 100,
                "above_supply": 0,
                "below_supply": 0,
                "burned": await compute_burn_balance(),
                "note": "No price data available"
            }

        # Simplified: since all holders have avg_buy_price = current_price, 
        # we show 100% "at" price for now. Real implementation needs historical pricing.
        above_supply = 0.0
        below_supply = 0.0
        at_supply = 0.0

        for h in holders:
            # For now, all holders are "at" current price (simplified)
            at_supply += h["balance"]

        total_tracked = sum(h["balance"] for h in holders)
        above_pct = (above_supply / total_tracked * 100) if total_tracked > 0 else 0
        below_pct = (below_supply / total_tracked * 100) if total_tracked > 0 else 0
        at_pct = (at_supply / total_tracked * 100) if total_tracked > 0 else 0

        return {
            "current_price": round(current_price, 6),
            "target_price": round(target_price, 6) if target_price else None,
            "comparison_price": round(comparison_price, 6),
            "above_pct": round(above_pct, 2),
            "below_pct": round(below_pct, 2),
            "at_pct": round(at_pct, 2),
            "above_supply": round(above_supply, 2),
            "below_supply": round(below_supply, 2),
            "at_supply": round(at_supply, 2),
            "burned": await compute_burn_balance(),
        }
    finally:
        await db.close()


async def get_last_refresh() -> dict:
    """Get the timestamp of the last data refresh."""
    db = await get_db()
    try:
        # Check token transfers
        cursor = await db.execute(
            "SELECT block_number FROM token_transfers ORDER BY block_number DESC LIMIT 1"
        )
        token_row = await cursor.fetchone()
        await cursor.close()

        # Check bridge txs
        cursor = await db.execute(
            "SELECT block_number FROM bridge_txs ORDER BY block_number DESC LIMIT 1"
        )
        bridge_row = await cursor.fetchone()
        await cursor.close()

        # Check price history
        cursor = await db.execute(
            "SELECT ts FROM price_history ORDER BY id DESC LIMIT 1"
        )
        price_row = await cursor.fetchone()
        await cursor.close()

        return {
            "token_last_block": token_row["block_number"] if token_row else None,
            "bridge_last_block": bridge_row["block_number"] if bridge_row else None,
            "price_last_update": price_row["ts"] if price_row else None,
        }
    finally:
        await db.close()