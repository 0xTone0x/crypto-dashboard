import sqlite3
conn = sqlite3.connect("backend/data.db")
c = conn.cursor()

total = c.execute("SELECT COUNT(*) FROM token_transfers").fetchone()[0]
print(f"Total transfers collected: {total}")

unique_all = c.execute("SELECT COUNT(DISTINCT addr) FROM (SELECT from_address as addr FROM token_transfers UNION SELECT to_address FROM token_transfers)").fetchone()[0]
print(f"Unique addresses (from+to): {unique_all}")

min_block = c.execute("SELECT MIN(block_number) FROM token_transfers").fetchone()[0]
max_block = c.execute("SELECT MAX(block_number) FROM token_transfers").fetchone()[0]
print(f"Block range: {min_block} - {max_block}")

holders = {}
for row in c.execute("SELECT from_address, to_address, amount FROM token_transfers"):
    from_addr, to_addr, amount = row
    amount = int(amount)
    holders[from_addr] = holders.get(from_addr, 0) - amount
    holders[to_addr] = holders.get(to_addr, 0) + amount

non_zero = {k: v for k, v in holders.items() if v > 0}
print(f"Computed holders (balance > 0): {len(non_zero)}")

total_tracked = sum(non_zero.values())
print(f"Total balance tracked (tokens, 18 dec): {total_tracked / 1e18:,.2f}")
print(f"Total supply: 1,000,000.00")
print(f"Coverage: {total_tracked / 1e18 / 1000000 * 100:.1f}%")

sorted_h = sorted(non_zero.items(), key=lambda x: -x[1])
print("\nTop 5 holders:")
for addr, bal in sorted_h[:5]:
    print(f"  {addr}: {bal / 1e18:,.2f} NOXA")

# Check if the token contract itself is showing up as a holder (minting)
print("\n--- Contract address check ---")
contract = "0x6778980c66bcd9a8f74d73bd1b608483c40e8dde"
if contract in holders:
    print(f"Token contract balance: {holders[contract] / 1e18:,.2f} NOXA")

# Check the zero address (0x000...0) — often the deployer/mint source
zero = "0x0000000000000000000000000000000000000000"
if zero in holders:
    print(f"Zero address balance: {holders[zero] / 1e18:,.2f} NOXA")
    
# Check how many total holders the explorer reports
# Also check: are we missing transfers? Let's see the latest blocks
latest_chain_block = 33256729  # from our earlier GraphQL test
print(f"\nLatest block in DB: {max_block}")
print(f"Latest block on chain: ~{latest_chain_block}")

# How many transfers exist on chain vs what we have?
# Check the GraphQL total count
conn.close()
