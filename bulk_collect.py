"""Bulk transfer collector — directly fetch ALL transfers without the async DB layer complexity."""
import httpx
import sqlite3
import asyncio
import time
import sys

GRAPHQL_URL = "https://scan.dbkchain.io/graphiql"
TOKEN_ADDR = "0x6778980c66bcd9a8f74d73bd1b608483c40e8dde"
DB_PATH = "/home/tone/crypto-dashboard/backend/data.db"

QUERY_TEMPLATE = """
{
  tokenTransfers(
    first: 20,
    tokenContractAddressHash: "%s"
    %s
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
"""

async def bulk_collect():
    # Clear existing
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM token_transfers")
    conn.commit()
    print("Cleared existing transfers", flush=True)

    cursor = None
    total = 0
    page = 0
    oldest_block = 999999999
    newest_block = 0
    all_addresses = set()

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            page += 1
            after_clause = f', after: "{cursor}"' if cursor else ''
            query = QUERY_TEMPLATE % (TOKEN_ADDR, after_clause)

            # Retry with backoff
            data = None
            for attempt in range(5):
                try:
                    resp = await client.post(GRAPHQL_URL, json={"query": query})
                    if resp.status_code != 200:
                        raise Exception(f"HTTP {resp.status_code}")
                    data = resp.json()
                    if "errors" in data:
                        raise Exception(f"GraphQL errors: {data['errors']}")
                    break
                except Exception as e:
                    if attempt < 4:
                        wait = min(2 ** attempt, 8)
                        print(f"  Page {page}: retry {attempt+1}/5 after {wait}s ({e})", flush=True)
                        await asyncio.sleep(wait)
                    else:
                        print(f"  Page {page}: FAILED after 5 retries: {e}", flush=True)
                        # Continue from where we are rather than crashing
                        data = None

            if data is None or not data.get("data", {}).get("tokenTransfers"):
                print(f"  Page {page}: no data, skipping", flush=True)
                break

            transfers = data["data"]["tokenTransfers"]
            edges = transfers["edges"]
            page_info = transfers["pageInfo"]

            # Batch insert
            rows = []
            for edge in edges:
                node = edge["node"]
                rows.append((
                    node["transactionHash"],
                    node["fromAddressHash"],
                    node["toAddressHash"],
                    node["amount"],
                    node["blockNumber"],
                    0,  # log_index
                ))
                oldest_block = min(oldest_block, node["blockNumber"])
                newest_block = max(newest_block, node["blockNumber"])
                all_addresses.add(node["fromAddressHash"])
                all_addresses.add(node["toAddressHash"])

            conn.executemany(
                "INSERT OR IGNORE INTO token_transfers (tx_hash, from_address, to_address, amount, block_number, log_index) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            total += len(rows)

            if page % 20 == 0:
                print(f"  Page {page}: {total} transfers, blocks {oldest_block}-{newest_block}, {len(all_addresses)} unique addresses", flush=True)

            if not page_info["hasNextPage"]:
                print(f"  Reached END at page {page}!", flush=True)
                break

            cursor = page_info["endCursor"]
            if not cursor:
                print(f"  No endCursor at page {page}, stopping", flush=True)
                break

            if page > 5000:
                print(f"  Safety limit (5000 pages)", flush=True)
                break

            await asyncio.sleep(0.15)

    # Compute holders
    holders = {}
    for row in conn.execute("SELECT from_address, to_address, amount FROM token_transfers"):
        holders[row[0]] = holders.get(row[0], 0) - int(row[1+1-1])  # from
        holders[row[1]] = holders.get(row[1], 0) + int(row[2])

    # Fix: recalculate properly
    holders = {}
    for row in conn.execute("SELECT from_address, to_address, amount FROM token_transfers"):
        from_addr, to_addr, amount = row
        amt = int(amount)
        holders[from_addr] = holders.get(from_addr, 0) - amt
        holders[to_addr] = holders.get(to_addr, 0) + amt

    non_zero = {k: v for k, v in holders.items() if v > 0}
    total_tracked = sum(v for v in non_zero.values()) / 1e18

    print(f"\n{'='*60}", flush=True)
    print(f"COLLECTION COMPLETE", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Total transfers: {total}", flush=True)
    print(f"Block range: {oldest_block} - {newest_block} (span: {newest_block - oldest_block})", flush=True)
    print(f"Unique addresses: {len(all_addresses)}", flush=True)
    print(f"Holders (balance > 0): {len(non_zero)}", flush=True)
    print(f"Tracked supply: {total_tracked:,.2f} NOXA ({total_tracked/1000000*100:.1f}% of 1M)", flush=True)
    print(f"Top 5:", flush=True)
    for addr, bal in sorted(non_zero.items(), key=lambda x: -x[1])[:5]:
        print(f"  {addr}: {bal/1e18:,.2f} NOXA", flush=True)

    conn.close()

if __name__ == "__main__":
    asyncio.run(bulk_collect())
