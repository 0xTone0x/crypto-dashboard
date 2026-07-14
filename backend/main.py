"""FastAPI main server — API + static frontend + startup collection."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.db import init_db
from backend.api.routes import router as api_router
from backend.collectors import blockscout_collector, etherscan_collector, price_collector

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB + trigger initial data collection on startup + start background tasks."""
    print("[startup] Initializing database...")
    await init_db()
    print("[startup] DB ready. Starting background data collection...")
    asyncio.create_task(_initial_collection())
    
    # Start price collector background task (runs every 60s)
    price_task = asyncio.create_task(price_collector._price_loop())
    
    # Start periodic data refresh (every 30 minutes)
    refresh_task = asyncio.create_task(_periodic_refresh())
    
    yield
    
    # Cleanup on shutdown
    price_task.cancel()
    refresh_task.cancel()


async def _initial_collection():
    """Fetch data on startup (non-blocking)."""
    for label, coro in [
        ("token transfers", blockscout_collector.collect_all_transfers),
        ("bridge txs", etherscan_collector.collect_all_bridge_txs),
    ]:
        try:
            print(f"[startup] Collecting {label}...")
            result = await coro()
            print(f"[startup] {label}: {result}")
        except Exception as e:
            print(f"[startup] {label} collection failed: {e}")


async def _periodic_refresh():
    """Refresh token and bridge data every 30 minutes (1800 seconds)."""
    import time
    while True:
        await asyncio.sleep(1800)  # 30 minutes
        print("[refresh] Starting 30-min data refresh...")
        try:
            # Trigger incremental collection
            await blockscout_collector.collect_all_transfers()
            await etherscan_collector.collect_all_bridge_txs()
            print("[refresh] 30-min data refresh complete")
        except Exception as e:
            print(f"[refresh] Refresh failed: {e}")


app = FastAPI(title="NOXA Analytics Dashboard", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# Serve frontend static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    """Serve the main dashboard page."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "NOXA Analytics API. Frontend not found at frontend/index.html"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
