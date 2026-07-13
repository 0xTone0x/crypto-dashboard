#!/usr/bin/env python3
"""One-shot script: collect ALL NOXA transfers from Blockscout GraphQL."""
import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

from backend.collectors.blockscout_collector import collect_all_transfers


async def main():
    result = await collect_all_transfers(reset=True)
    print("RESULT:", result, file=sys.stderr)


asyncio.run(main())
