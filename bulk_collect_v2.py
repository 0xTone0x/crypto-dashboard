"""Resume bulk transfer collection — handles 403 rate limits with longer backoff."""
import httpx
import sqlite3
import asyncio
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

async def resume_collect():
    conn = sqlite3.connect(DB_PATH)
    
    # Check what we already have
    existing = conn.execute("SELECT COUNT(*) FROM token_transfers").fetchone()[0]
    existing_blocks = conn.execute("SELECT MIN(block_number), MAX(block_number) FROM token_transfers").fetchone()
    print(f"Starting with {existing} transfers (blocks {existing_blocks[0]}-{existing_blocks[1]})", flush=True)
    
    # We need to page from the beginning. Since we're using INSERT OR IGNORE,
    # re-fetching already-stored transfers is harmless.
    # But to avoid the 403, let's use a SLOWER rate and more retries.
    
    cursor = None
    total_new = 0
    total_skipped = 0
    page = 0
    oldest_block = 999999999
    newest_block = 0
    consecutive_403 = 0

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            page += 1
            after_clause = f', after: "{cursor}"' if cursor else ''
            query = QUERY_TEMPLATE % (TOKEN_ADDR, after_clause)

            data = None
            for attempt in range(8):
                try:
                    resp = await client.post(GRAPHQL_URL, json={"query": query})
                    if resp.status_code == 403:
                        consecutive_403 += 1
                        wait = min(10 * (attempt + 1), 60)
                        print(f"  Page {page}: 403 (attempt {attempt+1}/8), waiting {wait}s...", flush=True)
                        await asyncio.sleep(wait)
                        continue
                    if resp.status_code != 200:
                        raise Exception(f"HTTP {resp.status_code}")
                    data = resp.json()
                    if "errors" in data:
                        raise Exception(f"GraphQL errors: {data['errors']}")
                    consecutive_403 = 0
                    break
                except Exception as e:
                    if attempt < 7:
                        wait = min(2 ** attempt, 30)
                        print(f"  Page {page}: error (attempt {attempt+1}/8): {e}, retry in {wait}s", flush=True)
                        await asyncio.sleep(wait)
                    else:
                        print(f"  Page {page}: FAILED after 8 retries: {e}", flush=True)
                        data = None
                        # If we've hit 403s multiple times, wait longer before next page
                        if consecutive_403 > 3:
                            print(f"  Too many 403s, pausing 60s...", flush=True)
                            await asyncio.sleep(60)
                            consecutive_403 = 0

            if data is None or not data.get("data", {}).get("tokenTransfers"):
                print(f"  Page {page}: no data, stopping", flush=True)
                break

            transfers = data["data"]["tokenTransfers"]
            edges = transfers["edges"]
            page_info = transfers["pageInfo"]

            rows = []
            for edge in edges:
                node = edge["node"]
                rows.append((
                    node["transactionHash"],
                    node["fromAddressHash"],
                    node["toAddressHash"],
                    node["amount"],
                    node["blockNumber"],
                    0,
                ))
                oldest_block = min(oldest_block, node["blockNumber"])
                newest_block = max(newest_block, node["blockNumber"])

            # Batch insert
            before = conn.execute("SELECT COUNT(*) FROM token_transfers").fetchone()[0]
            conn.executemany(
                "INSERT OR IGNORE INTO token_transfers (tx_hash, from_address, to_address, amount, block_number, log_index) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            conn.commit()
            after_count = conn.execute("SELECT COUNT(*) FROM token_transfers").fetchone()[0]
            added = after_count - before
            total_new += added
            total_skipped += len(rows) - added

            if page % 20 == 0:
                total = conn.execute("SELECT COUNT(*) FROM token_transfers").fetchone()[0]
                print(f"  Page {page}: +{added} new (total in DB: {total}), blocks {oldest_block}-{newest_block}", flush=True)

            if not page_info["hasNextPage"]:
                print(f"  Reached END at page {page}!", flush=True)
                break

            cursor = page_info["endCursor"]
            if not cursor:
                print(f"  No endCursor at page {page}, stopping", flush=True)
                break

            if page > 5000:
                print(f"  Safety limit reached", flush=True)
                break

            # Gentle rate: 0.3s between pages
            await asyncio.sleep(0.3)

    # Final stats
    total = conn.execute("SELECT COUNT(*) FROM token_transfers").fetchone()[0]
    blocks = conn.execute("SELECT MIN(block_number), MAX(block_number) FROM token_transfers").fetchone()
    
    holders = {}
    for row in conn.execute("SELECT from_address, to_address, amount FROM token_transfers"):
        amt = int(row[2])
        holders[row[0]] = holders.get(row[0], 0) - amt
        holders[row[1]] = holders.get(row[1], 0) + amt
    non_zero = sum(1 for v in holders.values() if v > 0)
    total_tracked = sum(v for v in holders.values() if v > 0) / 1e18

    print(f"\n{'='*60}", flush=True)
    print(f"COLLECTION SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"Pages fetched: {page}", flush=True)
    print(f"Total in DB: {total}", flush=True)
    print(f"New this run: {total_new}", flush=True)
    print(f"Already had: {total_skipped}", flush=True)
    print(f"Block range: {blocks[0]} - {blocks[1]} (span: {blocks[1]-blocks[0]})", flush=True)
    print(f"Holders (balance > 0): {non_zero}", flush=True)
    print(f"Tracked supply: {total_tracked:,.2f} NOXA ({total_tracked/1000000*100:.1f}%)", flush=True)
    
    conn.close()

if __name__ == "__main__":
    asyncio.run(resume_collect())
