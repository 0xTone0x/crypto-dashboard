"""DEX price collector — fetches NOXA price from Uniswap V3 pool on DBK Chain.

The NOXA/WETH pool is at 0x00b9b5096dcb4aad445e78c5a264dfe472867653 (UniV3-style).
token0 = WETH (0x4200...0006), token1 = NOXA.
Price is derived from slot0().sqrtPriceX96.
USD price = ETH_PRICE_USD / (NOXA_per_WETH).

Runs as a periodic background task every 60 seconds.
"""
import asyncio
import math
from datetime import datetime

import httpx

from backend.db import get_db, get_kv, set_kv
from backend import config

# ─── Chain / Pool constants ───
RPC_URL = "https://rpc.mainnet.dbkchain.io"
POOL_ADDRESS = "0x00b9b5096dcb4aad445e78c5a264dfe472867653"

# Token ordering in the V3 pool
TOKEN0_WETH = "0x4200000000000000000000000000000000000006"
TOKEN1_NOXA = config.NOXA_TOKEN.lower()

# Uniswap V3 function selectors
SLOT0_SELECTOR = "0x3850c7bd"
TOKEN0_SELECTOR = "0x0dfe1681"
TOKEN1_SELECTOR = "0xd21220a7"

# Coingecko simple-price endpoint for ETH/USD
COINGECKO_ETH_URL = (
    "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
)

# Background task handle
_price_task: asyncio.Task | None = None


# ─── RPC helpers ───

async def _eth_call(client: httpx.AsyncClient, to: str, data: str) -> str:
    """Perform an eth_call to the DBK RPC and return the hex result."""
    resp = await client.post(
        RPC_URL,
        json={
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": to, "data": data}, "latest"],
            "id": 1,
        },
        timeout=15,
    )
    result = resp.json().get("result", "0x")
    if result == "0x" or "error" in resp.json():
        raise RuntimeError(f"eth_call reverted for {to} {data}: {resp.json()}")
    return result


def _parse_slot0(slot0_hex: str) -> tuple[int, int]:
    """Parse slot0() return: (sqrtPriceX96, tick).

    Returns:
        sqrtPriceX96 (int), tick (signed int)
    """
    data = slot0_hex[2:]  # strip 0x
    sqrt_price = int(data[0:64], 16)
    tick_raw = int(data[64:128], 16)
    # Convert to signed int (two's complement)
    tick = tick_raw if tick_raw < 2 ** 255 else tick_raw - 2 ** 256
    return sqrt_price, tick


async def _get_eth_price_usd(client: httpx.AsyncClient) -> float:
    """Fetch ETH/USD from CoinGecko simple-price API."""
    resp = await client.get(COINGECKO_ETH_URL, timeout=10)
    data = resp.json()
    return float(data.get("ethereum", {}).get("usd", 0))


# ─── Public API ───

async def fetch_dex_price() -> dict:
    """Fetch the current NOXA price from the DEX pool.

    Returns a dict with:
        price_usd        — NOXA price in USD
        noxa_per_weth    — raw pool ratio (NOXA per 1 WETH)
        eth_price_usd    — ETH/USD used for conversion
        sqrt_price_x96   — raw pool oracle value
        tick             — V3 tick
        timestamp        — ISO timestamp
        source           — "dex_uniswap_v3"
    """
    async with httpx.AsyncClient() as client:
        slot0_hex = await _eth_call(client, POOL_ADDRESS, SLOT0_SELECTOR)
        sqrt_price, tick = _parse_slot0(slot0_hex)

        eth_usd = await _get_eth_price_usd(client)

    # Price = (sqrtPriceX96 / 2^96)^2  → token1 per token0 = NOXA per WETH
    noxa_per_weth = (sqrt_price / (2 ** 96)) ** 2

    if noxa_per_weth <= 0:
        raise RuntimeError(f"Invalid pool price ratio: {noxa_per_weth}")

    price_usd = eth_usd / noxa_per_weth if eth_usd > 0 else 0.0

    return {
        "price_usd": round(price_usd, 8),
        "noxa_per_weth": round(noxa_per_weth, 6),
        "eth_price_usd": eth_usd,
        "sqrt_price_x96": sqrt_price,
        "tick": tick,
        "timestamp": datetime.utcnow().isoformat(),
        "source": "dex_uniswap_v3",
    }


async def get_current_dex_price() -> float:
    """Convenience: return just the USD price (or 0 on error)."""
    try:
        data = await fetch_dex_price()
        return data["price_usd"]
    except Exception as e:
        print(f"[price_collector] Error fetching DEX price: {e}")
        return 0.0


async def collect_price_snapshot() -> dict:
    """Fetch current DEX price and store in price_history table.

    If a manual override exists in kv_store, that price is used instead
    (the DEX price is still recorded in the snapshot for reference).
    """
    price_data = await fetch_dex_price()

    db = await get_db()
    try:
        # Check for manual override
        override = await get_kv(db, "noxa_price_override", None)
        if override is not None:
            override_price = float(override)
            # Store override as the effective price, but mark source
            effective_price = override_price
            source = "manual_override"
        else:
            effective_price = price_data["price_usd"]
            source = price_data["source"]

        await db.execute(
            "INSERT INTO price_history (ts, price, source) VALUES (?, ?, ?)",
            (price_data["timestamp"], effective_price, source),
        )
        # Update the live DEX price in kv so other modules can read it
        await set_kv(db, "noxa_dex_price", str(price_data["price_usd"]))
        await set_kv(db, "noxa_dex_price_ts", price_data["timestamp"])
        await db.commit()

        return {
            "status": "ok",
            "price": effective_price,
            "dex_price": price_data["price_usd"],
            "source": source,
            "timestamp": price_data["timestamp"],
        }
    finally:
        await db.close()


# ─── Background task ───

COLLECT_INTERVAL = 60  # seconds


async def _price_loop():
    """Background loop: collect price snapshot every 60 seconds."""
    print("[price_collector] Background price collection started (60s interval)")
    while True:
        try:
            result = await collect_price_snapshot()
            print(
                f"[price_collector] {result['timestamp']} "
                f"price=${result['price']:.8f} "
                f"(dex=${result['dex_price']:.8f}, src={result['source']})"
            )
        except Exception as e:
            print(f"[price_collector] Collection error: {e}")
        await asyncio.sleep(COLLECT_INTERVAL)


def start_price_collector():
    """Start the background price collection task. Call from lifespan startup."""
    global _price_task
    if _price_task is None or _price_task.done():
        _price_task = asyncio.create_task(_price_loop())
    return _price_task


def stop_price_collector():
    """Stop the background price collection task."""
    global _price_task
    if _price_task and not _price_task.done():
        _price_task.cancel()
    _price_task = None
