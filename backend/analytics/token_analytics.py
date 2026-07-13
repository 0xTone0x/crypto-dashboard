"""Token analytics: compute holders, distribution, cost-basis from transfer data."""
from collections import defaultdict
from backend.db import get_db
from backend import config

DECIMALS = config.TOKEN_DECIMALS
SUPPLY = config.TOTAL_SUPPLY  # 1M NOXA in human units


def raw_to_human(amount_str: str) -> float:
    """Convert raw token amount (string, with 18 decimals) to human units."""
    try:
        return int(amount_str) / (10 ** DECIMALS)
    except (ValueError, TypeError):
        return 0.0


async def get_current_price(db) -> float:
    """Get the latest price override, or 0 if not set."""
    from backend.db import get_kv
    price = await get_kv(db, "noxa_price", None)
    if price is not None:
        return float(price)
    return 0.0


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
            if row["from_address"] and row["from_address"].lower() != "0x0000000000000000000000000000000000000000":
                balances[row["from_address"]] -= amt
            if row["to_address"] and row["to_address"].lower() != "0x0000000000000000000000000000000000000000":
                balances[row["to_address"]] += amt

        # Filter out zero/negative and sort
        holders = [
            {"address": addr, "balance": bal}
            for addr, bal in balances.items()
            if bal > 0.0001
        ]
        holders.sort(key=lambda x: x["balance"], reverse=True)

        current_price = await get_current_price(db)

        # Compute avg buy price per holder
        # For each holder, find all "receive" events and average them
        cursor = await db.execute("SELECT to_address, amount FROM token_transfers")
        buy_rows = await cursor.fetchall()
        await cursor.close()

        buy_totals = defaultdict(float)   # total tokens received
        buy_counts = defaultdict(int)
        for row in buy_rows:
            amt = raw_to_human(row["amount"])
            buy_totals[row["to_address"]] += amt
            buy_counts[row["to_address"]] += 1

        result = []
        for h in holders[:limit]:
            addr = h["address"]
            total_bought = buy_totals.get(addr, 0)
            avg_buy_price = current_price if current_price > 0 else 0  # Default: same as current
            pnl_pct = 0.0
            if current_price > 0 and avg_buy_price > 0:
                pnl_pct = ((current_price - avg_buy_price) / avg_buy_price) * 100

            result.append({
                "address": addr,
                "balance": round(h["balance"], 2),
                "pct_supply": round((h["balance"] / SUPPLY) * 100, 4) if SUPPLY > 0 else 0,
                "total_bought": round(total_bought, 2),
                "buy_count": buy_counts.get(addr, 0),
                "avg_buy_price": round(avg_buy_price, 6),
                "current_price": round(current_price, 6),
                "pnl_pct": round(pnl_pct, 2),
                "pnl_value": round((current_price - avg_buy_price) * h["balance"], 2) if current_price > 0 else 0,
            })

        return result
    finally:
        await db.close()


async def compute_distribution() -> dict:
    """Compute supply distribution stats."""
    holders = await compute_holders(limit=10000)
    if not holders:
        return {"top10_pct": 0, "top100_pct": 0, "total_holders": 0, "gini": 0, "supply": SUPPLY}

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
        "total_tracked_balance": round(total_balance, 2),
        "top10_pct": round((top10_balance / SUPPLY) * 100, 2) if SUPPLY > 0 else 0,
        "top100_pct": round((top100_balance / SUPPLY) * 100, 2) if SUPPLY > 0 else 0,
        "gini": round(gini, 4),
    }


async def compute_cost_basis() -> dict:
    """Cost-basis analysis: how much supply was acquired below/above current price."""
    db = await get_db()
    try:
        current_price = await get_current_price(db)
        holders = await compute_holders(limit=10000)

        if not holders or current_price <= 0:
            return {
                "current_price": current_price,
                "above_pct": 0,
                "below_pct": 0,
                "at_pct": 100,
                "above_supply": 0,
                "below_supply": 0,
                "note": "Set a price via POST /api/token/price to enable cost-basis analysis"
            }

        # Without historical price data per transfer, we assume each holder's
        # avg buy price ≈ current price (no DEX price history yet).
        # This is a placeholder until DEX price oracle is implemented.
        above = sum(h["balance"] for h in holders)  # all at current
        below = 0

        return {
            "current_price": round(current_price, 6),
            "above_pct": 0,  # placeholder
            "below_pct": 100,
            "at_pct": 0,
            "above_supply": 0,
            "below_supply": round(sum(h["balance"] for h in holders), 2),
            "note": "Cost-basis requires historical price oracle (coming soon)"
        }
    finally:
        await db.close()


async def get_token_info() -> dict:
    """Get token info with current price."""
    db = await get_db()
    try:
        from backend.db import get_kv
        price = await get_current_price(db)

        # Count holders
        holders = await compute_holders(limit=10000)
        holder_count = len(holders)

        return {
            "name": "NOXA",
            "symbol": "NOXA",
            "total_supply": SUPPLY,
            "decimals": DECIMALS,
            "price": round(price, 6),
            "market_cap": round(price * SUPPLY, 2) if price > 0 else 0,
            "holders": holder_count,
            "contract": config.NOXA_TOKEN,
        }
    finally:
        await db.close()
