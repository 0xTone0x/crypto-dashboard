"""Etherscan V2 collector — fetches all inbound transactions to the bridge address."""
import asyncio
import httpx
from backend.db import get_db, get_kv, set_kv
from backend import config


ETHERSCAN_BASE = "https://api.etherscan.io/v2/api"
BRIDGE = config.BRIDGE_ADDRESS.lower()


async def fetch_page(client: httpx.AsyncClient, page: int = 1, offset: int = 100):
    """Fetch one page of transactions to the bridge address."""
    params = {
        "chainid": 1,
        "module": "account",
        "action": "txlist",
        "address": config.BRIDGE_ADDRESS,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "desc",
        "page": page,
        "offset": offset,
        "apikey": config.ETHERSCAN_API_KEY,
    }
    resp = await client.get(ETHERSCAN_BASE, params=params, timeout=config.HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") == "0" and data.get("message") == "No transactions found":
        return []
    if data.get("status") == "0":
        raise RuntimeError(f"Etherscan error: {data.get('result')}")
    return data["result"]


async def collect_all_bridge_txs() -> dict:
    """Paginate through all inbound bridge transactions. Returns summary stats."""
    db = await get_db()
    try:
        total_fetched = 0
        total_stored = 0
        page = 0
        has_more = True

        async with httpx.AsyncClient() as client:
            while has_more:
                page += 1
                txs = await fetch_page(client, page=page, offset=100)
                if not txs:
                    break

                for tx in txs:
                    # Only inbound txs with value > 0
                    if tx["to"].lower() != BRIDGE:
                        continue
                    value = int(tx.get("value", "0"))
                    if value <= 0:
                        continue

                    cur = await db.execute(
                        """INSERT OR IGNORE INTO bridge_txs
                           (hash, from_address, to_address, value, block_number, timestamp, input_data, is_error)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            tx["hash"],
                            tx["from"],
                            tx["to"],
                            tx["value"],
                            int(tx["blockNumber"]),
                            int(tx["timeStamp"]),
                            tx.get("input", ""),
                            int(tx.get("isError", "0")),
                        ),
                    )
                    inserted = cur.rowcount
                    await cur.close()

                    total_stored += inserted
                    total_fetched += 1

                await db.commit()
                print(f"  [etherscan] page {page}: {len(txs)} txs (stored: {total_stored})")

                if len(txs) < 100:
                    has_more = False
                # Safety valve
                if page > 100:
                    print("  [etherscan] safety limit (100 pages)")
                    break
                await asyncio.sleep(0.2)  # Etherscan rate limit

        cursor = await db.execute("SELECT COUNT(*) as c FROM bridge_txs")
        row = await cursor.fetchone()
        total_in_db = row["c"]
        await cursor.close()

        return {
            "status": "ok",
            "pages_fetched": page,
            "txs_fetched": total_fetched,
            "txs_stored": total_stored,
            "total_in_db": total_in_db,
        }
    finally:
        await db.close()
