"""Holder concentration over time: reconstruct snapshots from transfer history."""
from collections import defaultdict
from backend.db import get_db
from backend import config

DECIMALS = config.TOKEN_DECIMALS
SUPPLY = config.TOTAL_SUPPLY

ZERO_ADDR = "0x" + "0" * 40


def raw_to_human(amount_str: str) -> float:
    try:
        return int(amount_str) / (10 ** DECIMALS)
    except (ValueError, TypeError):
        return 0.0


def _gini(values: list[float]) -> float:
    """Compute Gini coefficient from a list of non-negative balances."""
    if not values or sum(values) == 0:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cumulative = sum((2 * i - n - 1) * v for i, v in enumerate(sorted_vals, 1))
    return cumulative / (n * sum(sorted_vals))


async def _block_to_timestamp_map(db) -> dict:
    cursor = await db.execute(
        "SELECT MIN(block_number) as b0, MAX(block_number) as b1, "
        "MIN(timestamp) as t0, MAX(timestamp) as t1 FROM bridge_txs"
    )
    row = await cursor.fetchone()
    await cursor.close()
    if not row or row["b0"] is None:
        return {}
    b0, b1, t0, t1 = row["b0"], row["b1"], row["t0"], row["t1"]
    slope = (t1 - t0) / (b1 - b0) if b1 > b0 else 0
    return {"slope": slope, "b0": b0, "t0": t0}


def _estimate_ts(cal: dict, block: int) -> int:
    if not cal:
        import time
        return int(time.time())
    return int(cal["t0"] + cal["slope"] * (block - cal["b0"]))


async def compute_concentration_history(snapshot_count: int = 10) -> dict:
    """Reconstruct holder concentration snapshots at evenly-spaced points
    throughout the transfer history.

    Process: sort all transfers by block_number.  Divide into N checkpoints.
    At each checkpoint, replay all transfers up to that point to compute
    holder balances, then derive Gini + concentration ratios.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT from_address, to_address, amount, block_number, tx_hash "
            "FROM token_transfers ORDER BY block_number ASC, id ASC"
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return {
                "history": [],
                "trend": "stable",
                "current": None,
                "note": "No transfer data available",
            }

        cal = await _block_to_timestamp_map(db)
        total = len(rows)

        # Choose snapshot indices — evenly distributed checkpoints
        # Always include the final state (index = total - 1)
        snapshot_count = min(snapshot_count, total)
        step = total / snapshot_count
        snapshot_indices = set()
        for i in range(1, snapshot_count + 1):
            snapshot_indices.add(min(int(i * step) - 1, total - 1))
        snapshot_indices.add(total - 1)  # ensure final point

        # Replay transfers incrementally
        balances: dict[str, float] = defaultdict(float)
        history = []

        for idx, r in enumerate(rows):
            amt = raw_to_human(r["amount"])
            from_addr = r["from_address"]
            to_addr = r["to_address"]

            if from_addr and from_addr.lower() != ZERO_ADDR:
                balances[from_addr] -= amt
            if to_addr and to_addr.lower() != ZERO_ADDR:
                balances[to_addr] += amt

            if idx in snapshot_indices:
                # Snapshot: only positive balances are holders
                holder_balances = [b for b in balances.values() if b > 1e-9]
                holder_balances.sort(reverse=True)

                total_balance = sum(holder_balances)
                top10_bal = sum(holder_balances[:10])
                top100_bal = sum(holder_balances[:100])
                gini = _gini([b for b in balances.values() if b > 1e-9])

                ts = _estimate_ts(cal, r["block_number"])

                history.append({
                    "block_number": r["block_number"],
                    "timestamp": ts,
                    "transfer_index": idx + 1,
                    "total_transfers": total,
                    "holder_count": len(holder_balances),
                    "total_balance": round(total_balance, 2),
                    "gini": round(gini, 4),
                    "top10_pct": round((top10_bal / SUPPLY) * 100, 2) if SUPPLY > 0 else 0,
                    "top100_pct": round((top100_bal / SUPPLY) * 100, 2) if SUPPLY > 0 else 0,
                    "top10_share": round((top10_bal / total_balance) * 100, 2) if total_balance > 0 else 0,
                    "top100_share": round((top100_bal / total_balance) * 100, 2) if total_balance > 0 else 0,
                })

        # Determine trend
        trend = "stable"
        current = history[-1] if history else None
        if len(history) >= 2:
            first_gini = history[0]["gini"]
            last_gini = history[-1]["gini"]
            delta = last_gini - first_gini
            if delta > 0.02:
                trend = "increasing"
            elif delta < -0.02:
                trend = "decreasing"

        return {
            "history": history,
            "trend": trend,
            "current": current,
            "snapshots": len(history),
        }
    finally:
        await db.close()
