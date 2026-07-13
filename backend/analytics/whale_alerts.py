"""Whale alerts: detect large token transfers and bridge deposits."""
from collections import defaultdict
from backend.db import get_db
from backend import config
from backend.analytics.bridge_analytics import wei_to_eth

DECIMALS = config.TOKEN_DECIMALS
SUPPLY = config.TOTAL_SUPPLY

# Thresholds
TOKEN_WHALE_PCT = 1.0       # > 1% of supply
TOKEN_WHALE_ABS = 500       # or > 500 NOXA absolute floor
BRIDGE_WHALE_ETH = 5.0      # > 5 ETH


def raw_to_human(amount_str: str) -> float:
    try:
        return int(amount_str) / (10 ** DECIMALS)
    except (ValueError, TypeError):
        return 0.0


async def _get_price(db) -> float:
    from backend.db import get_kv
    price = await get_kv(db, "noxa_price", None)
    return float(price) if price is not None else 0.0


async def _block_to_timestamp(block_number: int) -> int | None:
    """Estimate a unix timestamp from a block number using bridge_txs calibration.
    DBK Chain block time is ~2s.  Use known bridge (block, timestamp) pairs
    for interpolation; fall back to 2s/block if no data.
    """
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT block_number, timestamp FROM bridge_txs ORDER BY block_number ASC LIMIT 1"
        )
        first = await cursor.fetchone()
        await cursor.close()
        cursor = await db.execute(
            "SELECT block_number, timestamp FROM bridge_txs ORDER BY block_number DESC LIMIT 1"
        )
        last = await cursor.fetchone()
        await cursor.close()

        if first and last:
            b0, t0 = first["block_number"], first["timestamp"]
            b1, t1 = last["block_number"], last["timestamp"]
            if b1 > b0:
                # Interpolate / extrapolate
                slope = (t1 - t0) / (b1 - b0)
                return int(t0 + slope * (block_number - b0))
            return t0
        return None
    finally:
        await db.close()


async def get_whale_alerts(limit: int = 20) -> list[dict]:
    """Return recent whale movements: large token transfers + large bridge deposits."""
    db = await get_db()
    try:
        price = await _get_price(db)
        whale_threshold_tokens = max(SUPPLY * TOKEN_WHALE_PCT / 100, TOKEN_WHALE_ABS)

        alerts: list[dict] = []

        # --- Large token transfers ---
        cursor = await db.execute(
            "SELECT from_address, to_address, amount, tx_hash, block_number "
            "FROM token_transfers ORDER BY block_number DESC"
        )
        rows = await cursor.fetchall()
        await cursor.close()

        # Pre-compute per-address received totals for context
        addr_received = defaultdict(float)
        for r in rows:
            amt = raw_to_human(r["amount"])
            addr_received[r["to_address"]] += amt

        for r in rows:
            amt = raw_to_human(r["amount"])
            if amt >= whale_threshold_tokens:
                ts = await _block_to_timestamp(r["block_number"])
                value_usd = amt * price if price > 0 else 0
                alerts.append({
                    "type": "token_transfer",
                    "address": r["from_address"],
                    "to_address": r["to_address"],
                    "amount": round(amt, 2),
                    "pct_supply": round((amt / SUPPLY) * 100, 4) if SUPPLY > 0 else 0,
                    "value_usd": round(value_usd, 2),
                    "timestamp": ts,
                    "tx_hash": r["tx_hash"],
                    "block_number": r["block_number"],
                })

        # --- Large bridge deposits ---
        cursor = await db.execute(
            "SELECT hash, from_address, to_address, value, block_number, timestamp "
            "FROM bridge_txs WHERE is_error = 0 ORDER BY timestamp DESC"
        )
        bridge_rows = await cursor.fetchall()
        await cursor.close()

        for r in bridge_rows:
            eth = wei_to_eth(r["value"])
            if eth >= BRIDGE_WHALE_ETH:
                value_usd = eth * 3000  # rough ETH price fallback
                alerts.append({
                    "type": "bridge_deposit",
                    "address": r["from_address"],
                    "to_address": r["to_address"],
                    "amount": round(eth, 4),
                    "amount_unit": "ETH",
                    "value_usd": round(value_usd, 2),
                    "timestamp": r["timestamp"],
                    "tx_hash": r["hash"],
                    "block_number": r["block_number"],
                })

        # Sort by timestamp desc (None timestamps sort last)
        alerts.sort(key=lambda a: a.get("timestamp") or 0, reverse=True)

        return alerts[:limit]
    finally:
        await db.close()
