"""API route handlers."""
from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from backend.analytics import token_analytics, bridge_analytics, whale_alerts, transfer_heatmap, concentration
from backend.collectors import blockscout_collector, etherscan_collector, price_collector
from backend.db import get_db, get_kv, set_kv
from datetime import datetime
import json

router = APIRouter(prefix="/api")


# ─── Token endpoints ───

@router.get("/token/info")
async def token_info():
    db = await get_db()
    try:
        # Get latest price from price_history (prefer DEX, fallback to manual override)
        cursor = await db.execute(
            "SELECT price, source FROM price_history ORDER BY id DESC LIMIT 1"
        )
        row = await cursor.fetchone()
        latest_price = float(row["price"]) if row else 0.05
        await cursor.close()
        
        # Get token metadata
        cursor = await db.execute(
            "SELECT value FROM kv_store WHERE key = 'token_info'"
        )
        row = await cursor.fetchone()
        token_meta = json.loads(row["value"]) if row else {}
        await cursor.close()
        
        total_supply = token_meta.get("total_supply", 10**24)
        decimals = token_meta.get("decimals", 18)
        name = token_meta.get("name", "NOXA")
        symbol = token_meta.get("symbol", "NOXA")
        
        # Compute holders count
        holders = {}
        cursor = await db.execute("SELECT from_address, to_address, amount FROM token_transfers")
        rows = await cursor.fetchall()
        await cursor.close()
        for row in rows:
            amt = int(row[2])
            holders[row[0]] = holders.get(row[0], 0) - amt
            holders[row[1]] = holders.get(row[1], 0) + amt
        holder_count = sum(1 for v in holders.values() if v > 0)
        
        # Compute current tracked supply for MC
        tracked_supply = sum(v for v in holders.values() if v > 0) / 10**18
        
        return {
            "name": name,
            "symbol": symbol,
            "total_supply": total_supply / 10**18,
            "decimals": decimals,
            "price": latest_price,
            "market_cap": round(latest_price * total_supply / 10**18, 2),
            "holders": holder_count,
            "contract": token_meta.get("address", ""),
        }
    finally:
        await db.close()


@router.get("/token/holders")
async def token_holders(limit: int = 100):
    holders = await token_analytics.compute_holders(limit=limit)
    return {"holders": holders, "count": len(holders)}


@router.get("/token/distribution")
async def token_distribution():
    return await token_analytics.compute_distribution()


@router.get("/token/cost-basis")
async def token_cost_basis():
    return await token_analytics.compute_cost_basis()


class PriceOverride(BaseModel):
    price: float
    source: Optional[str] = "manual"


@router.post("/token/price")
async def set_price(body: PriceOverride):
    db = await get_db()
    try:
        await set_kv(db, "noxa_price", str(body.price))
        # Also store in price_history
        from datetime import datetime
        await db.execute(
            "INSERT INTO price_history (ts, price, source) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(), body.price, body.source),
        )
        await db.commit()
        return {"status": "ok", "price": body.price}
    finally:
        await db.close()


@router.get("/token/price-history")
async def token_price_history(limit: int = 100):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT ts, price, source FROM price_history ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return {
            "history": [{"ts": r["ts"], "price": r["price"], "source": r["source"]} for r in reversed(rows)]
        }
    finally:
        await db.close()


# ─── Bridge endpoints ───

@router.get("/bridge/stats")
async def bridge_stats(hours: int = 72):
    return await bridge_analytics.compute_bridge_stats(hours=hours)


@router.get("/bridge/timeseries")
async def bridge_timeseries():
    return {"data": await bridge_analytics.compute_timeseries()}


@router.get("/bridge/timeseries-hourly")
async def bridge_timeseries_hourly(hours: int = 168):
    return {"data": await bridge_analytics.compute_timeseries_hourly(hours=hours)}


@router.get("/bridge/top-depositors")
async def bridge_top_depositors(limit: int = 20, hours: int = 72):
    return {"depositors": await bridge_analytics.compute_top_depositors(limit=limit, hours=hours)}


@router.get("/bridge/recent")
async def bridge_recent(limit: int = 20):
    return {"transactions": await bridge_analytics.get_recent_bridge_txs(limit=limit)}


# ─── Whale Alerts ───

@router.get("/whale-alerts")
async def whale_alerts_endpoint(limit: int = 20):
    return {"alerts": await whale_alerts.get_whale_alerts(limit=limit)}


# ─── Cross-Chain Analysis ───

@router.get("/cross-chain/summary")
async def cross_chain_summary(days: int = 3):
    return await bridge_analytics.compute_cross_chain_summary(days=days)


@router.get("/cross-chain/bridgers-buyers")
async def cross_chain_bridgers_buyers(days: int = 3):
    return await bridge_analytics.compute_bridgers_buyers(days=days)


# ─── Transfer Heatmap ───

@router.get("/token/transfer-heatmap")
async def transfer_heatmap_endpoint():
    return await transfer_heatmap.compute_heatmap()


# ─── Concentration History ───

@router.get("/token/concentration-history")
async def concentration_history_endpoint():
    return await concentration.compute_concentration_history()


# ─── Collection triggers ───

@router.post("/collect/token")
async def collect_token():
    try:
        result = await blockscout_collector.collect_all_transfers()
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/collect/bridge")
async def collect_bridge():
    try:
        result = await etherscan_collector.collect_all_bridge_txs()
        return result
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/health")
async def health():
    return {"status": "ok"}
