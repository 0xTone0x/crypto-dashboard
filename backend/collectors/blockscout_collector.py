"""Blockscout GraphQL collector — fetches all NOXA token transfers with pagination."""
import asyncio
import logging
import httpx
from backend.db import get_db, get_kv, set_kv
from backend import config

logger = logging.getLogger(__name__)

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


async def fetch_transfers(
    client: httpx.AsyncClient,
    first: int = 20,
    after: str | None = None,
    max_retries: int = 5,
) -> dict:
    """Fetch a single page of token transfers from GraphQL with retry/backoff.

    Note: DBK Chain Blockscout has a max GraphQL complexity of 200.
    With 5 fields per node, `first=20` gives complexity 100 (safe).
    """
    variables = {"first": first, "after": after}
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.post(
                GRAPHQL_URL,
                json={"query": TRANSFER_QUERY, "variables": variables},
                timeout=config.HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            # GraphQL can return 200 with errors
            if "errors" in data:
                last_error = RuntimeError(f"GraphQL errors: {data['errors']}")
                logger.warning(
                    "  [blockscout] GraphQL errors (attempt %d/%d): %s",
                    attempt,
                    max_retries,
                    data["errors"],
                )
            elif not data.get("data") or not data["data"].get("tokenTransfers"):
                last_error = RuntimeError("Empty response from GraphQL")
                logger.warning(
                    "  [blockscout] empty response (attempt %d/%d)",
                    attempt,
                    max_retries,
                )
            else:
                return data["data"]["tokenTransfers"]

        except httpx.HTTPError as exc:
            last_error = exc
            logger.warning(
                "  [blockscout] HTTP error (attempt %d/%d): %s",
                attempt,
                max_retries,
                exc,
            )

        if attempt < max_retries:
            backoff = min(2**attempt, 10)  # 1s, 2s, 4s, 8s, 10s
            logger.info(
                "  [blockscout] retrying in %ds (attempt %d/%d)",
                backoff,
                attempt,
                max_retries,
            )
            await asyncio.sleep(backoff)

    raise RuntimeError(
        f"Failed to fetch transfers after {max_retries} retries: {last_error}"
    )


async def collect_all_transfers(reset: bool = False) -> dict:
    """Paginate through ALL token transfers and store in DB. Returns summary stats.

    Args:
        reset: If True, delete all existing rows and start fresh.
    """
    db = await get_db()
    try:
        if reset:
            logger.info("  [blockscout] RESET: deleting all existing token_transfers")
            await db.execute("DELETE FROM token_transfers")
            await db.execute("DELETE FROM kv_store WHERE key='last_transfer_cursor'")
            await db.commit()

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

                stored_this_page = 0
                for edge in edges:
                    node = edge["node"]
                    try:
                        cursor = await db.execute(
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
                        stored_this_page += cursor.rowcount
                        await cursor.close()
                    except Exception as exc:
                        logger.debug("  [blockscout] insert error for tx %s: %s",
                                     node.get("transactionHash", "?"), exc)

                await db.commit()
                rows_this_page = len(edges)
                total_fetched += rows_this_page
                total_stored += stored_this_page

                if page % 10 == 0 or rows_this_page < 20:
                    logger.info(
                        "  [blockscout] page %d: +%d rows (total fetched: %d, stored: %d)",
                        page,
                        rows_this_page,
                        total_fetched,
                        total_stored,
                    )

                if not page_info["hasNextPage"]:
                    logger.info(
                        "  [blockscout] reached end of pagination at page %d", page
                    )
                    break
                after = page_info["endCursor"]
                if not after:
                    logger.info("  [blockscout] no endCursor — stopping at page %d", page)
                    break
                # Safety valve: avoid infinite loops
                if page > 3000:
                    logger.warning("  [blockscout] safety limit reached (3000 pages)")
                    break
                await asyncio.sleep(0.1)

            if after:
                await set_kv(db, "last_transfer_cursor", after)

        # Count actual stored rows
        cursor = await db.execute("SELECT COUNT(*) as c FROM token_transfers")
        row = await cursor.fetchone()
        total_in_db = row["c"]
        await cursor.close()

        logger.info(
            "  [blockscout] DONE: %d pages, %d fetched, %d in DB",
            page,
            total_fetched,
            total_in_db,
        )

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
