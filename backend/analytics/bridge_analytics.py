"""Bridge analytics: total ETH bridged, velocity, depositors, time series."""
from collections import defaultdict
from datetime import datetime, timedelta
from backend.db import get_db

WEI_PER_ETH = 10**18


def wei_to_eth(wei_str: str) -> float:
    try:
        return int(wei_str) / WEI_PER_ETH
    except (ValueError, TypeError):
        return 0.0


async def compute_bridge_stats() -> dict:
    """Compute bridge velocity stats."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT from_address, value, timestamp FROM bridge_txs ORDER BY timestamp ASC"
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return {
                "total_eth": 0,
                "total_deposits": 0,
                "unique_depositors": 0,
                "avg_deposit": 0,
                "eth_24h": 0,
                "eth_7d": 0,
                "eth_30d": 0,
                "velocity_7d_per_day": 0,
            }

        total_eth = sum(wei_to_eth(r["value"]) for r in rows)
        depositors = set(r["from_address"] for r in rows)

        now_ts = int(datetime.utcnow().timestamp())
        eth_24h = sum(wei_to_eth(r["value"]) for r in rows if r["timestamp"] >= now_ts - 86400)
        eth_7d = sum(wei_to_eth(r["value"]) for r in rows if r["timestamp"] >= now_ts - 86400 * 7)
        eth_30d = sum(wei_to_eth(r["value"]) for r in rows if r["timestamp"] >= now_ts - 86400 * 30)

        return {
            "total_eth": round(total_eth, 4),
            "total_deposits": len(rows),
            "unique_depositors": len(depositors),
            "avg_deposit": round(total_eth / len(rows), 4) if rows else 0,
            "eth_24h": round(eth_24h, 4),
            "eth_7d": round(eth_7d, 4),
            "eth_30d": round(eth_30d, 4),
            "velocity_7d_per_day": round(eth_7d / 7, 4),
        }
    finally:
        await db.close()


async def compute_timeseries() -> list[dict]:
    """Daily bridge volume time series."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT value, timestamp FROM bridge_txs ORDER BY timestamp ASC"
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return []

        daily = defaultdict(float)
        for r in rows:
            day = datetime.utcfromtimestamp(r["timestamp"]).strftime("%Y-%m-%d")
            daily[day] += wei_to_eth(r["value"])

        return [{"date": day, "volume": round(vol, 4)} for day, vol in sorted(daily.items())]
    finally:
        await db.close()


async def compute_top_depositors(limit: int = 20) -> list[dict]:
    """Top depositors by total ETH sent to bridge."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT from_address, value FROM bridge_txs ORDER BY value DESC"
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return []

        totals = defaultdict(float)
        counts = defaultdict(int)
        for r in rows:
            eth = wei_to_eth(r["value"])
            totals[r["from_address"]] += eth
            counts[r["from_address"]] += 1

        result = []
        for addr, eth in sorted(totals.items(), key=lambda x: x[1], reverse=True)[:limit]:
            result.append({
                "address": addr,
                "total_eth": round(eth, 4),
                "deposit_count": counts[addr],
                "avg_deposit": round(eth / counts[addr], 4),
            })
        return result
    finally:
        await db.close()


async def get_recent_bridge_txs(limit: int = 20) -> list[dict]:
    """Recent bridge transactions."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT hash, from_address, value, timestamp, block_number "
            "FROM bridge_txs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        result = []
        for r in rows:
            result.append({
                "hash": r["hash"],
                "from": r["from_address"],
                "value_eth": round(wei_to_eth(r["value"]), 4),
                "timestamp": r["timestamp"],
                "time_ago": _time_ago(r["timestamp"]),
                "block_number": r["block_number"],
            })
        return result
    finally:
        await db.close()


def _time_ago(ts: int) -> str:
    diff = int(datetime.utcnow().timestamp()) - ts
    if diff < 60:
        return f"{diff}s ago"
    elif diff < 3600:
        return f"{diff // 60}m ago"
    elif diff < 86400:
        return f"{diff // 3600}h ago"
    else:
        return f"{diff // 86400}d ago"
