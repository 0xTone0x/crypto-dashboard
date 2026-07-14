"""Token swap feed: returns recent transfers with wallet balances."""
from collections import defaultdict
from datetime import datetime, timedelta
from backend.db import get_db, get_kv
from backend import config

DECIMALS = config.TOKEN_DECIMALS
SUPPLY = config.TOTAL_SUPPLY
BURN_ADDRESSES = {"0x0000000000000000000000000000000000000000", "0x000000000000000000000000000000000000dead"}


def raw_to_human(amount_str: str) -> float:
    try:
        return int(amount_str) / (10 ** DECIMALS)
    except (ValueError, TypeError):
        return 0.0


def is_burn_address(addr: str) -> bool:
    return addr.lower() in BURN_ADDRESSES


async def get_swaps_feed(limit: int = 50):
    """Get recent token transfers formatted as swap feed."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT from_address, to_address, amount, block_number, tx_hash "
            "FROM token_transfers ORDER BY block_number DESC LIMIT ?",
            (limit,)
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            return []

        # Get current NOXA/USD price
        cursor = await db.execute(
            "SELECT price FROM price_history ORDER BY id DESC LIMIT 1"
        )
        price_row = await cursor.fetchone()
        await cursor.close()
        
        noxa_usd = float(price_row["price"]) if price_row else 0.0
        eth_usd = 3000.0
        noxa_eth = noxa_usd / eth_usd if eth_usd > 0 else 0.0

        # Get recent transfers for wallet balances
        cursor = await db.execute(
            "SELECT from_address, to_address, amount, block_number "
            "FROM token_transfers ORDER BY block_number DESC LIMIT 1000"
        )
        all_transfers = [dict(row) for row in await cursor.fetchall()]
        await cursor.close()

        # Compute wallet balances
        balances = defaultdict(float)
        for tx in all_transfers:
            amt = raw_to_human(tx["amount"])
            if tx["from_address"] and not is_burn_address(tx["from_address"]):
                balances[tx["from_address"].lower()] -= amt
            if tx["to_address"] and not is_burn_address(tx["to_address"]):
                balances[tx["to_address"].lower()] += amt

        swaps = []
        current_time = datetime.utcnow()
        max_block = rows[0]["block_number"] if rows else 0

        for row in rows:
            amount = raw_to_human(row["amount"])
            usd_amount = amount * noxa_usd
            mcap = SUPPLY * noxa_usd
            
            # Determine type
            from_lower = row["from_address"].lower() if row["from_address"] else ""
            to_lower = row["to_address"].lower() if row["to_address"] else ""
            
            if is_burn_address(from_lower):
                swap_type = "BUY"
            elif is_burn_address(to_lower):
                swap_type = "SELL"
            else:
                swap_type = "SWAP"
            
            tx_hash = row["tx_hash"] or f"0x{row['block_number']:064x}"
            block_diff = max_block - row["block_number"]
            tx_time = current_time.timestamp() - (block_diff * 2)
            
            # Get wallet balance
            wallet_addr = to_lower if swap_type in ["BUY", "SWAP"] else from_lower
            wallet_balance = balances.get(wallet_addr, 0.0)
            
            swaps.append({
                "type": swap_type,
                "amount": amount,
                "amount_str": f"{amount:,.2f}",
                "price_eth": noxa_eth,
                "price_eth_str": f"{noxa_eth:.8f}",
                "price_usd": noxa_usd,
                "price_usd_str": f"${noxa_usd:.6f}",
                "usd_amount": usd_amount,
                "usd_amount_str": f"${usd_amount:,.2f}",
                "market_cap": mcap,
                "market_cap_str": f"${mcap/1000000:.2f}M",
                "wallet_address": row["to_address"] if swap_type in ["BUY", "SWAP"] else row["from_address"],
                "wallet_short": f"{(row['to_address'] if swap_type in ['BUY', 'SWAP'] else row['from_address'])[:6]}…{row['to_address'][-4:] if swap_type in ['BUY', 'SWAP'] else row['from_address'][-4:]}",
                "wallet_balance": wallet_balance,
                "wallet_balance_str": f"{wallet_balance:,.2f} NOXA",
                "wallet_value": wallet_balance * noxa_usd,
                "wallet_value_str": f"${wallet_balance * noxa_usd:,.2f}",
                "activity_6h": {"buys": 0, "sells": 0, "net": 0, "is_accumulating": wallet_balance > 1000, "is_distributing": wallet_balance < -1000},
                "tx_hash": tx_hash,
                "tx_short": f"{tx_hash[:10]}…",
                "timestamp": int(tx_time),
                "time_utc": datetime.utcfromtimestamp(tx_time).strftime("%H:%M UTC"),
            })
        
        return swaps
    finally:
        await db.close()