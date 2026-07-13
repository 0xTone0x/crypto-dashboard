"""SQLite database layer using aiosqlite."""
import aiosqlite
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "data.db"


async def get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    """Create all tables if not exist."""
    db = await get_db()
    try:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS token_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_hash TEXT NOT NULL,
                from_address TEXT NOT NULL,
                to_address TEXT NOT NULL,
                amount TEXT NOT NULL,
                block_number INTEGER NOT NULL,
                log_index INTEGER DEFAULT 0,
                UNIQUE(tx_hash, from_address, to_address, amount, log_index)
            );

            CREATE TABLE IF NOT EXISTS bridge_txs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hash TEXT UNIQUE NOT NULL,
                from_address TEXT NOT NULL,
                to_address TEXT NOT NULL,
                value TEXT NOT NULL,
                block_number INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                input_data TEXT DEFAULT '',
                is_error INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                price REAL NOT NULL,
                source TEXT DEFAULT 'manual'
            );

            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_tt_from ON token_transfers(from_address);
            CREATE INDEX IF NOT EXISTS idx_tt_to ON token_transfers(to_address);
            CREATE INDEX IF NOT EXISTS idx_tt_block ON token_transfers(block_number);
            CREATE INDEX IF NOT EXISTS idx_bt_from ON bridge_txs(from_address);
            CREATE INDEX IF NOT EXISTS idx_bt_ts ON bridge_txs(timestamp);
        """)
        await db.commit()
    finally:
        await db.close()


async def get_kv(db, key, default=None):
    cursor = await db.execute("SELECT value FROM kv_store WHERE key=?", (key,))
    row = await cursor.fetchone()
    await cursor.close()
    return row["value"] if row else default


async def set_kv(db, key, value):
    await db.execute(
        "INSERT INTO kv_store (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )
    await db.commit()
