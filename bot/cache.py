from contextlib import contextmanager
import sqlite3
import time
from typing import Optional

class LinkCache:
    """SQLite-backed cache for bypassed links.
    Eliminates redundant bypasses and provides instant sub-10ms responses.
    """
    def __init__(self, db_path: str = "cache.db", default_ttl: int = 86400):
        self.db_path = db_path
        self.default_ttl = default_ttl
        self._init_db()

    @contextmanager
    def _conn(self):
        """Deterministic connection manager ensuring handles are closed immediately."""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            conn.execute("PRAGMA busy_timeout = 5000;")
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS link_cache (
                    alias TEXT PRIMARY KEY,
                    destination_url TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    hits INTEGER DEFAULT 1
                )
            """)

    def get(self, alias: str) -> Optional[str]:
        now = time.time()
        for attempt in range(5):
            try:
                with self._conn() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT destination_url, expires_at, hits FROM link_cache WHERE alias = ?
                    """, (alias,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    dest, expires_at, hits = row
                    if now > expires_at:
                        cur.execute("DELETE FROM link_cache WHERE alias = ?", (alias,))
                        return None
                    cur.execute("UPDATE link_cache SET hits = hits + 1 WHERE alias = ?", (alias,))
                    return dest
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc) and attempt < 4:
                    time.sleep(0.05 * (attempt + 1))
                else:
                    raise

    def set(self, alias: str, destination_url: str, ttl: Optional[int] = None):
        now = time.time()
        ttl = ttl or self.default_ttl
        expires_at = now + ttl
        for attempt in range(10):
            try:
                with self._conn() as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO link_cache (alias, destination_url, created_at, expires_at, hits)
                        VALUES (?, ?, ?, ?, 1)
                    """, (alias, destination_url, now, expires_at))
                return
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc) and attempt < 9:
                    time.sleep(0.05 * (attempt + 1))
                else:
                    raise

    def get_entry(self, alias: str) -> Optional[dict]:
        """Fetch raw cache entry metadata (for tests and inspection)."""
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT alias, destination_url, created_at, expires_at, hits FROM link_cache WHERE alias = ?
            """, (alias,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "alias": row[0],
                "destination_url": row[1],
                "created_at": row[2],
                "expires_at": row[3],
                "hits": row[4],
            }
