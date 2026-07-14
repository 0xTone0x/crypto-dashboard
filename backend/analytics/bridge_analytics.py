"""Bridge analytics: total ETH bridged, velocity, depositors, time series, cross-chain."""
from collections import defaultdict
from datetime import datetime, timedelta
from backend.db import get_db, get_kv

WEI_PER_ETH = 10**18
NOXA_DECIMALS = 10**18


def wei_to_eth(wei_str: str) -> float:
    try:
        return int(wei_str) / WEI_PER_ETH
    except (ValueError, TypeError):
        return 0.0


async def compute_bridge_stats(hours: int = 72) -> dict:
    """Compute bridge velocity stats.

    Args:
        hours: Only count bridgers and volume from the last N hours (default 72h = 3 days).
    """
    db = await get_db()
    try:
        now_ts = int(datetime.utcnow().timestamp())
        cutoff = now_ts - hours * 3600
        
        cursor = await db.execute(
            "SELECT from_address, value, timestamp FROM bridge_txs WHERE timestamp >= ? ORDER BY timestamp ASC",
            (cutoff,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return {
                "window_hours": hours,
                "total_eth": 0,
                "total_deposits": 0,
                "unique_depositors": 0,
                "avg_deposit": 0,
                "eth_1h": 0,
                "eth_6h": 0,
                "eth_12h": 0,
                "eth_24h": 0,
                "eth_7d": 0,
                "eth_30d": 0,
                "txs_1h": 0,
                "txs_6h": 0,
                "txs_12h": 0,
                "txs_24h": 0,
                "txs_7d": 0,
                "velocity_1h": 0,
                "velocity_6h": 0,
                "velocity_12h": 0,
                "velocity_24h": 0,
                "velocity_7d": 0,
                "velocity_7d_per_day": 0,
            }

        total_eth = sum(wei_to_eth(r["value"]) for r in rows)
        depositors = set(r["from_address"] for r in rows)

        eth_1h = sum(wei_to_eth(r["value"]) for r in rows if r["timestamp"] >= now_ts - 3600)
        eth_6h = sum(wei_to_eth(r["value"]) for r in rows if r["timestamp"] >= now_ts - 3600 * 6)
        eth_12h = sum(wei_to_eth(r["value"]) for r in rows if r["timestamp"] >= now_ts - 3600 * 12)
        eth_24h = sum(wei_to_eth(r["value"]) for r in rows if r["timestamp"] >= now_ts - 86400)
        eth_7d = sum(wei_to_eth(r["value"]) for r in rows if r["timestamp"] >= now_ts - 86400 * 7)
        eth_30d = sum(wei_to_eth(r["value"]) for r in rows if r["timestamp"] >= now_ts - 86400 * 30)

        txs_1h = sum(1 for r in rows if r["timestamp"] >= now_ts - 3600)
        txs_6h = sum(1 for r in rows if r["timestamp"] >= now_ts - 3600 * 6)
        txs_12h = sum(1 for r in rows if r["timestamp"] >= now_ts - 3600 * 12)
        txs_24h = sum(1 for r in rows if r["timestamp"] >= now_ts - 86400)
        txs_7d = sum(1 for r in rows if r["timestamp"] >= now_ts - 86400 * 7)

        velocity_1h = eth_1h / 1
        velocity_6h = eth_6h / 6
        velocity_12h = eth_12h / 12
        velocity_24h = eth_24h / 24
        velocity_7d = eth_7d / (7 * 24)

        return {
            "window_hours": hours,
            "total_eth": round(total_eth, 4),
            "total_deposits": len(rows),
            "unique_depositors": len(depositors),
            "avg_deposit": round(total_eth / len(rows), 4) if rows else 0,
            "eth_1h": round(eth_1h, 4),
            "eth_6h": round(eth_6h, 4),
            "eth_12h": round(eth_12h, 4),
            "eth_24h": round(eth_24h, 4),
            "eth_7d": round(eth_7d, 4),
            "eth_30d": round(eth_30d, 4),
            "txs_1h": txs_1h,
            "txs_6h": txs_6h,
            "txs_12h": txs_12h,
            "txs_24h": txs_24h,
            "txs_7d": txs_7d,
            "velocity_1h": round(velocity_1h, 4),
            "velocity_6h": round(velocity_6h, 4),
            "velocity_12h": round(velocity_12h, 4),
            "velocity_24h": round(velocity_24h, 4),
            "velocity_7d": round(velocity_7d, 4),
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


async def compute_top_depositors(limit: int = 20, hours: int = 72) -> list[dict]:
    """Top depositors by total ETH sent to bridge, within time window."""
    db = await get_db()
    try:
        now_ts = int(datetime.utcnow().timestamp())
        cutoff = now_ts - hours * 3600
        
        cursor = await db.execute(
            "SELECT from_address, value FROM bridge_txs WHERE timestamp >= ? ORDER BY value DESC",
            (cutoff,),
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


async def compute_timeseries_hourly(hours: int = 168) -> list[dict]:
    """Hourly bridge volume time series for the last N hours."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT value, timestamp FROM bridge_txs ORDER BY timestamp ASC"
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return []

        now_ts = int(datetime.utcnow().timestamp())
        cutoff = now_ts - hours * 3600

        hourly = defaultdict(float)
        hourly_counts = defaultdict(int)
        for r in rows:
            if r["timestamp"] < cutoff:
                continue
            hour_bucket = (r["timestamp"] // 3600) * 3600  # truncate to hour
            hourly[hour_bucket] += wei_to_eth(r["value"])
            hourly_counts[hour_bucket] += 1

        # Fill gaps with zero entries for continuous timeline
        result = []
        start_bucket = (cutoff // 3600) * 3600
        end_bucket = (now_ts // 3600) * 3600
        current = start_bucket
        while current <= end_bucket:
            dt = datetime.utcfromtimestamp(current)
            result.append({
                "timestamp": current,
                "hour": dt.strftime("%Y-%m-%d %H:00"),
                "volume": round(hourly.get(current, 0.0), 6),
                "tx_count": hourly_counts.get(current, 0),
            })
            current += 3600

        return result
    finally:
        await db.close()


async def compute_cross_chain_summary(days: int = 3) -> dict:
    """Summary of bridgers vs NOXA buyers overlap, filtered to recent bridgers only.

    Args:
        days: Only count bridgers from the last N days (default 3).
    """
    db = await get_db()
    try:
        now_ts = int(datetime.utcnow().timestamp())
        cutoff = now_ts - days * 86400

        # Unique RECENT bridge depositor addresses (last N days)
        cursor = await db.execute(
            "SELECT DISTINCT LOWER(from_address) AS addr FROM bridge_txs WHERE timestamp >= ?",
            (cutoff,),
        )
        bridger_rows = await cursor.fetchall()
        bridgers = {r["addr"] for r in bridger_rows}
        await cursor.close()

        # Unique NOXA buyers (to_address in token_transfers) — all time
        cursor = await db.execute(
            "SELECT DISTINCT LOWER(to_address) AS addr FROM token_transfers"
        )
        buyer_rows = await cursor.fetchall()
        buyers = {r["addr"] for r in buyer_rows}
        await cursor.close()

        overlap = bridgers & buyers

        # ETH bridged per address — recent only, CAST AS REAL for overflow safety
        cursor = await db.execute(
            "SELECT LOWER(from_address) AS addr, SUM(CAST(value AS REAL)) AS total_wei "
            "FROM bridge_txs WHERE timestamp >= ? GROUP BY LOWER(from_address)",
            (cutoff,),
        )
        eth_by_addr = {}
        for r in await cursor.fetchall():
            eth_by_addr[r["addr"]] = r["total_wei"] / WEI_PER_ETH
        await cursor.close()

        buyer_eth = [eth_by_addr.get(a, 0) for a in overlap]
        non_buyer_addrs = bridgers - overlap
        non_buyer_eth = [eth_by_addr.get(a, 0) for a in non_buyer_addrs]

        return {
            "window_days": days,
            "total_bridgers": len(bridgers),
            "total_noxa_holders": len(buyers),
            "overlap_count": len(overlap),
            "conversion_rate": round(len(overlap) / len(bridgers), 4) if bridgers else 0,
            "avg_eth_bridged_by_buyers": round(sum(buyer_eth) / len(buyer_eth), 4) if buyer_eth else 0,
            "avg_eth_bridged_by_non_buyers": round(sum(non_buyer_eth) / len(non_buyer_eth), 4) if non_buyer_eth else 0,
        }
    finally:
        await db.close()


async def compute_bridgers_buyers(days: int = 3) -> dict:
    """Addresses that BOTH bridged ETH (recent) AND bought NOXA (all-time), with per-address detail.

    Args:
        days: Only count bridgers from the last N days (default 3).
    """
    db = await get_db()
    try:
        now_ts = int(datetime.utcnow().timestamp())
        cutoff = now_ts - days * 86400

        # Get NOXA price from KV
        price_str = await get_kv(db, "noxa_price")
        noxa_price = float(price_str) if price_str else 0.0

        # ETH bridged per address — recent only, CAST AS REAL for overflow safety
        cursor = await db.execute(
            "SELECT LOWER(from_address) AS addr, "
            "SUM(CAST(value AS REAL)) AS total_wei, "
            "COUNT(*) AS tx_count "
            "FROM bridge_txs WHERE timestamp >= ? GROUP BY LOWER(from_address)",
            (cutoff,),
        )
        bridge_data = {}
        for r in await cursor.fetchall():
            bridge_data[r["addr"]] = {
                "total_wei": r["total_wei"],
                "total_eth": r["total_wei"] / WEI_PER_ETH,
                "tx_count": r["tx_count"],
            }
        await cursor.close()

        # NOXA bought per address (to_address = buyer) — all time
        cursor = await db.execute(
            "SELECT LOWER(to_address) AS addr, "
            "SUM(CAST(amount AS REAL)) AS total_amount, "
            "COUNT(*) AS transfer_count "
            "FROM token_transfers GROUP BY LOWER(to_address)"
        )
        noxa_data = {}
        for r in await cursor.fetchall():
            noxa_data[r["addr"]] = {
                "total_raw": r["total_amount"],
                "total_noxa": r["total_amount"] / NOXA_DECIMALS,
                "transfer_count": r["transfer_count"],
            }
        await cursor.close()

        overlap = set(bridge_data.keys()) & set(noxa_data.keys())

        matches = []
        for addr in sorted(overlap, key=lambda a: bridge_data[a]["total_eth"], reverse=True):
            eth = bridge_data[addr]["total_eth"]
            noxa = noxa_data[addr]["total_noxa"]
            noxa_value_usd = noxa * noxa_price
            pct = round((noxa / eth * 100), 2) if eth > 0 else 0
            matches.append({
                "address": addr,
                "total_eth_bridged": round(eth, 4),
                "total_noxa_bought": round(noxa, 2),
                "bridge_tx_count": bridge_data[addr]["tx_count"],
                "noxa_transfer_count": noxa_data[addr]["transfer_count"],
                "noxa_value_usd": round(noxa_value_usd, 2),
                "pct_of_bridged_spent": pct,
            })

        total_eth_by_buyers = sum(m["total_eth_bridged"] for m in matches)
        total_noxa_bought = sum(m["total_noxa_bought"] for m in matches)

        return {
            "window_days": days,
            "matches": matches,
            "match_count": len(matches),
            "total_eth_by_buyers": round(total_eth_by_buyers, 4),
            "total_noxa_bought_by_bridgers": round(total_noxa_bought, 2),
            "noxa_price": noxa_price,
        }
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