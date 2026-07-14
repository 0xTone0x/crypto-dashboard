"""Whale alerts: detect large token movements."""
from collections import defaultdict
from datetime import datetime, timedelta
from backend.db import get_db, get_kv
from backend import config

DECIMALS = config.TOKEN_DECIMALS


def raw_to_human(amount_str: str) -> float:
    """Convert raw token amount to human units."""
    try:
        return int(amount_str) / (10 ** DECIMALS)
    except (ValueError, TypeError):
        return 0.0


async def get_whale_alerts(hours: int = 24) -> list[dict]:
    """Detect large token transfers in the last N hours.

    Args:
        hours: Lookback period (default 24h)
    """
    db = await get_db()
    try:
        cutoff_timestamp = int((datetime.utcnow() - timedelta(hours=hours)).timestamp())
        threshold = 10000  # 10K NOXA as default whale threshold

        cursor = await db.execute(
            "SELECT tx_hash, from_address, to_address, amount, block_number "
            "FROM token_transfers WHERE block_number >= ? ORDER BY block_number DESC",
            (cutoff_timestamp,),  # Note: using timestamp, but we should ideally use block numbers
        )
        rows = await cursor.fetchall()
        await cursor.close()

        alerts = []
        for row in rows:
            amount = raw_to_human(row["amount"])
            if amount >= threshold:
                alerts.append({
                    "tx_hash": row["tx_hash"],
                    "from": row["from_address"],
                    "to": row["to_address"],
                    "amount": round(amount, 2),
                    "block_number": row["block_number"],
                })

        return alerts
    finally:
        await db.close()


async def get_block_number_from_timestamp(timestamp: int) -> int:
    """Approximate block number from timestamp for DBK chain."""
    # DBK chain produces ~2 blocks per second
    # Reference block and timestamp
    REF_BLOCK = 33258157
    REF_TIMESTAMP = 1720934400  # Approx timestamp of reference block
    BLOCKS_PER_SECOND = 2

    if timestamp >= REF_TIMESTAMP:
        delta_seconds = timestamp - REF_TIMESTAMP
        return REF_BLOCK + (delta_seconds * BLOCKS_PER_SECOND)
    else:
        delta_seconds = REF_TIMESTAMP - timestamp
        return REF_BLOCK - (delta_seconds * BLOCKS_PER_SECOND)


async def get_whale_alerts_by_block(hours: int = 24) -> list[dict]:
    """Detect large token transfers using block numbers instead of timestamp."""
    db = await get_db()
    try:
        cutoff_timestamp = int((datetime.utcnow() - timedelta(hours=hours)).timestamp())
        cutoff_block = await get_block_number_from_timestamp(cutoff_timestamp)
        threshold = 10000  # 10K NOXA

        cursor = await db.execute(
            "SELECT tx_hash, from_address, to_address, amount, block_number "
            "FROM token_transfers WHERE block_number >= ? ORDER BY block_number DESC",
            (cutoff_block,),
        )
        rows = await cursor.fetchall()
        await cursor.close()

        alerts = []
        for row in rows:
            amount = raw_to_human(row["amount"])
            if amount >= threshold:
                alerts.append({
                    "tx_hash": row["tx_hash"],
                    "from": row["from_address"],
                    "to": row["to_address"],
                    "amount": round(amount, 2),
                    "block_number": row["block_number"],
                })

        return alerts
    finally:
        await db.close()