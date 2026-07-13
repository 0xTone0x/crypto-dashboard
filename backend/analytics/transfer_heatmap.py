"""Transfer heatmap: aggregate token transfers by day-of-week x hour-of-day."""
from collections import defaultdict
from datetime import datetime, timezone
from backend.db import get_db
from backend import config

DECIMALS = config.TOKEN_DECIMALS

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def raw_to_human(amount_str: str) -> float:
    try:
        return int(amount_str) / (10 ** DECIMALS)
    except (ValueError, TypeError):
        return 0.0


async def _block_to_timestamp_map(db) -> dict[int, int]:
    """Build block_number -> timestamp mapping via bridge calibration.
    Returns a callable-like dict with interpolation/extrapolation.
    """
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

    return {"slope": slope, "b0": b0, "t0": t0, "b1": b1, "t1": t1}


def _estimate_ts(cal: dict, block: int) -> int:
    """Estimate timestamp from block using calibration dict."""
    if not cal:
        # No calibration — assume blocks are recent (now)
        return int(datetime.utcnow().timestamp())
    return int(cal["t0"] + cal["slope"] * (block - cal["b0"]))


async def compute_heatmap() -> dict:
    """Return 7x24 grid (days x hours) with transfer counts and volumes,
    plus top transfer corridors."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT from_address, to_address, amount, block_number "
            "FROM token_transfers ORDER BY block_number ASC"
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return {
                "grid": [],
                "corridors": [],
                "total_transfers": 0,
                "total_volume": 0,
                "note": "No transfer data",
            }

        cal = await _block_to_timestamp_map(db)

        # 7 days x 24 hours
        counts = [[0] * 24 for _ in range(7)]
        volumes = [[0.0] * 24 for _ in range(7)]

        # Corridors
        corridor_data: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"count": 0, "volume": 0.0}
        )

        for r in rows:
            amt = raw_to_human(r["amount"])
            ts = _estimate_ts(cal, r["block_number"])
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)

            # weekday() = Monday=0 ... Sunday=6
            day = dt.weekday()
            hour = dt.hour
            counts[day][hour] += 1
            volumes[day][hour] += amt

            key = (r["from_address"], r["to_address"])
            corridor_data[key]["count"] += 1
            corridor_data[key]["volume"] += amt

        # Build grid
        grid = []
        for day_idx in range(7):
            for hour_idx in range(24):
                if counts[day_idx][hour_idx] > 0:
                    grid.append({
                        "day": day_idx,
                        "day_name": DAYS[day_idx],
                        "hour": hour_idx,
                        "count": counts[day_idx][hour_idx],
                        "volume": round(volumes[day_idx][hour_idx], 2),
                    })

        # Peak cell
        max_count = max(max(row) for row in counts) if any(any(r) for r in counts) else 0

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

        total_vol = sum(sum(row) for row in volumes)

        return {
            "days": DAYS,
            "hours": list(range(24)),
            "grid": grid,  # sparse format: only non-zero cells
            "full_grid": {  # dense format for easy rendering
                "counts": counts,
                "volumes": [[round(v, 2) for v in row] for row in volumes],
            },
            "max_count": max_count,
            "corridors": corridor_list,
            "total_transfers": len(rows),
            "total_volume": round(total_vol, 2),
        }
    finally:
        await db.close()
