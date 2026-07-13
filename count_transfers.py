import httpx
import json
import asyncio
import time

async def count_transfers():
    url = "https://scan.dbkchain.io/graphiql"
    cursor = None
    total = 0
    oldest_block = 999999999
    newest_block = 0
    
    for i in range(1000):
        after_clause = f', after: "{cursor}"' if cursor else ''
        query = """
        {
          tokenTransfers(
            first: 20,
            tokenContractAddressHash: "0x6778980c66bcd9a8f74d73bd1b608483c40e8dde"
            %s
          ) {
            edges { node { blockNumber } }
            pageInfo { hasNextPage endCursor }
          }
        }
        """ % after_clause
        
        for attempt in range(3):
            try:
                resp = httpx.post(url, json={"query": query}, timeout=15)
                data = resp.json()
                break
            except Exception:
                if attempt < 2:
                    await asyncio.sleep(2)
                    continue
                else:
                    print(f"Failed at page {i} after 3 retries, stopping")
                    print(f"Total so far: {total}")
                    return
        
        if "errors" in data:
            print(f"GraphQL error at page {i}: {data['errors']}")
            break
            
        edges = data["data"]["tokenTransfers"]["edges"]
        page_info = data["data"]["tokenTransfers"]["pageInfo"]
        
        for e in edges:
            b = e["node"]["blockNumber"]
            oldest_block = min(oldest_block, b)
            newest_block = max(newest_block, b)
        
        total += len(edges)
        cursor = page_info["endCursor"]
        
        if not page_info["hasNextPage"]:
            print(f"Reached END at page {i+1}!")
            break
        
        if i % 50 == 0:
            print(f"Page {i+1}: {total} transfers so far, blocks {oldest_block}-{newest_block}")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(0.1)
    
    print(f"\nTotal transfers on chain: {total}")
    print(f"Block range: {oldest_block} - {newest_block}")
    print(f"Block span: {newest_block - oldest_block}")

asyncio.run(count_transfers())
