"""Trigger initial data collection."""
import asyncio
import sys
sys.path.insert(0, '/home/tone/crypto-dashboard')

from backend.collectors import blockscout_collector, price_collector, etherscan_collector

async def collect_all():
    print("Collecting token transfers...")
    await blockscout_collector.collect_all_transfers()
    
    print("Collecting price...")
    await price_collector.collect_price()
    
    print("Collecting bridge deposits...")
    await etherscan_collector.collect_all_deposits()
    
    print("\n✅ Data collection complete!")

asyncio.run(collect_all())