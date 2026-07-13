# NOXA Analytics Dashboard

Crypto analytics dashboard for the **NOXA** token on **DBK Chain** + a **Bridge Velocity Tracker** for ETH deposits to `0x28f1b9f457cb51e0af56dff1d11cd6cedffd1977` on Ethereum.

## Features

### Token Analytics
- 📊 Supply overview (total supply, holders count, price, market cap)
- 🍩 Cost-basis analysis (supply above/below current price)
- 👥 Top 100 holders with balances, % of supply, avg buy price, PnL
- 📈 Supply distribution (Gini coefficient, top-10 vs top-100 vs rest)
- ⚙️ Manual price override for cost-basis & PnL calculations

### Bridge Velocity Tracker
- 🌉 Total ETH bridged (all-time)
- ⚡ Bridge velocity (24h / 7d / 30d volume, per-day rate)
- 👤 Unique depositors & average deposit size
- 📅 Daily volume bar chart
- 🏆 Top depositors leaderboard
- 📋 Recent bridge transactions list

## Tech Stack
- **Backend**: Python FastAPI + httpx (async) + aiosqlite
- **Frontend**: Single-page HTML + vanilla JS + Tailwind CSS (CDN) + Chart.js
- **Database**: SQLite (zero external dependencies)
- **Data Sources**: DBK Chain Blockscout GraphQL + Etherscan V2 API

## Project Structure
```
crypto-dashboard/
├── backend/
│   ├── main.py                 # FastAPI server entry point
│   ├── config.py               # Env-based configuration
│   ├── db.py                   # SQLite schema & helpers
│   ├── collectors/
│   │   ├── blockscout_collector.py  # NOXA token transfers (GraphQL pagination)
│   │   └── etherscan_collector.py   # Bridge transactions (Etherscan V2)
│   ├── analytics/
│   │   ├── token_analytics.py       # Holders, distribution, cost-basis
│   │   └── bridge_analytics.py      # Velocity, depositors, timeseries
│   └── api/
│       └── routes.py                # All API endpoints
├── frontend/
│   └── index.html                   # SPA dashboard
├── requirements.txt
└── README.md
```

## Setup

### Prerequisites
- Python 3.11+
- Internet access to DBK Chain explorer and Etherscan

### Installation

```bash
cd crypto-dashboard
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Configuration

Create an env file (default path: `~/.env.crypto-dashboard`):

```bash
ETHERSCAN_API_KEY=your_etherscan_api_key
BRIDGE_ADDRESS=0x28f1b9f457cb51e0af56dff1d11cd6cedffd1977
NOXA_TOKEN=0x6778980c66bcd9A8F74D73BD1b608483c40E8DdE
DBK_EXPLORER=https://scan.dbkchain.io
DBK_GRAPHQL=https://scan.dbkchain.io/graphiql
```

Set a custom env path if needed:
```bash
export ENV_PATH=/path/to/your/.env
```

### Running

```bash
# From the project root
source venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Or directly:
```bash
python -m backend.main
```

Open http://localhost:8000 in your browser.

On startup, the server automatically fetches token transfers and bridge transactions in the background.

## API Endpoints

### Token
| Endpoint | Method | Description |
|---|---|---|
| `/api/token/info` | GET | Token name, symbol, supply, price, market cap |
| `/api/token/holders` | GET | Top N holders (default 100) with balances & PnL |
| `/api/token/distribution` | GET | Supply distribution stats + Gini coefficient |
| `/api/token/cost-basis` | GET | % supply above/below current price |
| `/api/token/price` | POST | Set manual price override `{"price": 0.05}` |

### Bridge
| Endpoint | Method | Description |
|---|---|---|
| `/api/bridge/stats` | GET | Total ETH, velocity, depositors, averages |
| `/api/bridge/timeseries` | GET | Daily bridge volume time series |
| `/api/bridge/top-depositors` | GET | Top depositors leaderboard |
| `/api/bridge/recent` | GET | Recent bridge transactions |

### Data Collection
| Endpoint | Method | Description |
|---|---|---|
| `/api/collect/token` | POST | Trigger token transfer collection |
| `/api/collect/bridge` | POST | Trigger bridge tx collection |
| `/api/health` | GET | Health check |

## How It Works

### Token Holders Computation
Since DBK Chain's Blockscout GraphQL has no direct "token holders" query, holders are computed by aggregating all `tokenTransfers` records:
- For each transfer: `from_address` balance decreases, `to_address` balance increases
- Minting (from `0x0`) and burning (to `0x0`) are handled
- The result is a real-time balance snapshot from on-chain transfer data

### Incremental Collection
Data collection is incremental — the Blockscout collector stores the last pagination cursor so subsequent runs only fetch new transfers.

### Price Oracle
There's no public price feed for NOXA yet. The dashboard supports a manual price override via the API or UI. This price flows into cost-basis and PnL calculations. A DEX price oracle can be added later by implementing RPC calls to the liquidity pair contract.

## Tech Notes
- All HTTP calls use `httpx.AsyncClient` (fully async)
- Database access uses `aiosqlite` (async SQLite)
- The frontend auto-refreshes every 2 minutes
- CORS is enabled for all origins

## License
MIT
