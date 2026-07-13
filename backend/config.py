"""Configuration: loads env vars from /home/tone/.env.crypto-dashboard."""
import os
from dotenv import load_dotenv

ENV_PATH = os.environ.get("ENV_PATH", "/home/tone/.env.crypto-dashboard")
load_dotenv(ENV_PATH)

ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")
BRIDGE_ADDRESS = os.getenv("BRIDGE_ADDRESS", "0x28f1b9f457cb51e0af56dff1d11cd6cedffd1977")
NOXA_TOKEN = os.getenv("NOXA_TOKEN", "0x6778980c66bcd9A8F74D73BD1b608483c40E8DdE")
DBK_EXPLORER = os.getenv("DBK_EXPLORER", "https://scan.dbkchain.io")
DBK_GRAPHQL = os.getenv("DBK_GRAPHQL", "https://scan.dbkchain.io/graphiql")
TOKEN_DECIMALS = 18
TOTAL_SUPPLY = 1_000_000  # 1M NOXA

# HTTP client defaults
HTTP_TIMEOUT = 30.0
HTTP_RETRIES = 3
