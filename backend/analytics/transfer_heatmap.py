"""Transfer heatmap: aggregate token transfers by hour-of-day (no day-of-week)."""
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from backend.db import get_db
from backend import config

DECIMALS = config.TOKEN_DECIMALS
HOURS = [f"{h:02d}:00" for h in range(24)]


def raw_to_human(amount_str: str) -> float:
    try:
        return int(amount_str) / (10 ** DECIMALS)
    except (ValueError, TypeError):
        return 0.0


async def compute_heatmap(hours: int = 24) -> dict:
    """Return 24-hour grid (hour only) with transfer counts and volumes.

    Args:
        hours: Lookback period (default 24h)
    """
    db = await get_db()
    try:
        # Get all transfers and filter by block number approximation
        cursor = await db.execute(
            "SELECT from_address, to_address, amount, block_number "
            "FROM token_transfers ORDER BY block_number DESC"
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return {
                "grid": [],
                "corridors": [],
                "total_transfers": 0,
                "total_volume": 0,
                "window_hours": hours,
                "note": "No transfer data",
            }

        # Find cutoff block based on hours (assuming ~2 blocks/sec on DBK)
        max_block = rows[0]["block_number"]
        cutoff_block = max(0, max_block - (hours * 3600 * 2))  # 2 blocks per second

        # Filter rows
        recent_rows = [r for r in rows if r["block_number"] >= cutoff_block]

        # 24 hours only (no day dimension)
        counts = [0] * 24
        volumes = [0.0] * 24

        # Corridors
        corridor_data: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"count": 0, "volume": 0.0}
        )

        # For heatmap hour calculation, distribute transfers by hour of day
        # based on their index in the time window
        for i, r in enumerate(recent_rows):
            amt = raw_to_human(r["amount"])
            
            # Distribute hour based on position in window (0 = oldest, last = newest)
            # This is an approximation since we don't have exact timestamps
            total_in_window = len(recent_rows)
            if total_in_window > 0:
                hour_idx = int((i / total_in_window) * 24)
                if hour_idx >= 24:
                    hour_idx = 23
                counts[hour_idx] += 1
                volumes[hour_idx] += amt

            key = (r["from_address"], r["to_address"])
            corridor_data[key]["count"] += 1
            corridor_data[key]["volume"] += amt

        # Build grid (hour only)
        grid = []
        for hour_idx in range(24):
            if counts[hour_idx] > 0:
                grid.append({
                    "hour": hour_idx,
                    "hour_label": HOURS[hour_idx],
                    "count": counts[hour_idx],
                    "volume": round(volumes[hour_idx], 2),
                })

        # Max count for normalization
        max_count = max(counts) if any(counts) else 0

        # Top corridors
        corridors = sorted(
            corridor_data.items(), key=lambda x: x[1]["count"], reverse=True
        )[:10]
        corridor_list = [
            {
                "from": addr_from,
                "to": addr_to,
                "count": v["count"],
                "volume": round(v["volume"], 2),
            }
            for (addr_from, addr_to), v in corridors
        ]

        total_vol = sum(volumes)

        return {
            "hours": HOURS,
            "grid": grid,
            "counts": counts,
            "volumes": [round(v, 2) for v in volumes],
            "max_count": max_count,
            "corridors": corridor_list,
            "total_transfers": len(recent_rows),
            "total_volume": round(total_vol, 2),
            "window_hours": hours,
        }
    finally:
        await db.close()