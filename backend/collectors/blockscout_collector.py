"""Blockscout GraphQL collector — fetches all NOXA token transfers with pagination."""
import asyncio
import httpx
from backend.db import get_db, get_kv, set_kv
from backend import config


GRAPHQL_URL = config.DBK_GRAPHQL
TOKEN_ADDR = config.NOXA_TOKEN.lower()

TRANSFER_QUERY = """
query GetTransfers($first: Int!, $after: String) {
  tokenTransfers(
    first: $first,
    tokenContractAddressHash: "%s",
    after: $after
  ) {
    edges {
      node {
        fromAddressHash
        toAddressHash
        amount
        transactionHash
        blockNumber
      }
    }
    pageInfo { hasNextPage endCursor }
  }
}
""" % TOKEN_ADDR


async def fetch_transfers(client: httpx.AsyncClient, first: int = 20, after: str | None = None):
    """Fetch a single page of token transfers from GraphQL.

    Note: DBK Chain Blockscout has a max GraphQL complexity of 200.
    With 5 fields per node, `first=20` gives complexity 100 (safe).
    """
    variables = {"first": first, "after": after}
    resp = await client.post(
        GRAPHQL_URL,
        json={"query": TRANSFER_QUERY, "variables": variables},
        timeout=config.HTTP_TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]["tokenTransfers"]


async def collect_all_transfers() -> dict:
    """Paginate through ALL token transfers and store in DB. Returns summary stats."""
    db = await get_db()
    try:
        last_cursor = await get_kv(db, "last_transfer_cursor", None)
        after = last_cursor
        total_fetched = 0
        total_stored = 0
        page = 0

        async with httpx.AsyncClient() as client:
            while True:
                page += 1
                result = await fetch_transfers(client, first=20, after=after)
                edges = result["edges"]
                page_info = result["pageInfo"]

                for edge in edges:
                    node = edge["node"]
                    try:
                        await db.execute(
                            """INSERT OR IGNORE INTO token_transfers
                               (tx_hash, from_address, to_address, amount, block_number, log_index)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (
                                node["transactionHash"],
                                node["fromAddressHash"],
                                node["toAddressHash"],
                                node["amount"],
                                node["blockNumber"],
                                0,
                            ),
                        )
                        total_stored += db.total_changes - total_stored if False else 0
                    except Exception:
                        pass

                await db.commit()
                rows_this_page = len(edges)
                total_fetched += rows_this_page
                print(f"  [blockscout] page {page}: {rows_this_page} transfers (total: {total_fetched})")

                if not page_info["hasNextPage"]:
                    break
                after = page_info["endCursor"]
                if not after:
                    break
                # Safety valve: avoid infinite loops
                if page > 2000:
                    print("  [blockscout] safety limit reached (2000 pages)")
                    break
                await asyncio.sleep(0.1)

            if after:
                await set_kv(db, "last_transfer_cursor", after)

        # Count actual stored rows
        cursor = await db.execute("SELECT COUNT(*) as c FROM token_transfers")
        row = await cursor.fetchone()
        total_in_db = row["c"]
        await cursor.close()

        return {
            "status": "ok",
            "pages_fetched": page,
            "transfers_fetched": total_fetched,
            "total_in_db": total_in_db,
        }
    finally:
        await db.close()


async def collect_token_info() -> dict:
    """Fetch token metadata from Blockscout V1 REST API."""
    url = (
        f"{config.DBK_EXPLORER}/api"
        f"?module=token&action=getToken&contractaddress={TOKEN_ADDR}"
    )
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    if data.get("status") == "1":
        result = data["result"]
        return {
            "name": result.get("name", "NOXA"),
            "symbol": result.get("symbol", "NOXA"),
            "decimals": int(result.get("decimals", "18")),
            "total_supply": int(result.get("totalSupply", "0")),
        }
    return {"name": "NOXA", "symbol": "NOXA", "decimals": 18, "total_supply": 10**24}
