# -*- coding: utf-8 -*-
"""Lưu job + cache link đích bằng SQLite (WAL). Nhẹ, không cần Redis."""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import uuid
from typing import Any, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    provider    TEXT,
    key         TEXT,
    status      TEXT NOT NULL,            -- queued|running|success|error|timeout
    destination TEXT,
    error       TEXT,
    tries       INTEGER DEFAULT 0,
    elapsed_ms  REAL DEFAULT 0,
    cached      INTEGER DEFAULT 0,
    client      TEXT,
    created     REAL NOT NULL,
    updated     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created);

CREATE TABLE IF NOT EXISTS cache (
    provider    TEXT NOT NULL,
    key         TEXT NOT NULL,
    destination TEXT NOT NULL,
    updated     REAL NOT NULL,
    hits        INTEGER DEFAULT 0,
    PRIMARY KEY (provider, key)
);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.commit()

    # ---------------------------------------------------------------- jobs
    def create_job(self, url: str, provider: str, key: str, client: str) -> str:
        jid = uuid.uuid4().hex[:16]
        now = time.time()
        with self._lock:
            self._db.execute(
                "INSERT INTO jobs(id,url,provider,key,status,client,created,updated)"
                " VALUES(?,?,?,?, 'queued', ?,?,?)",
                (jid, url, provider, key, client, now, now))
            self._db.commit()
        return jid

    def set_status(self, jid: str, status: str, **fields: Any) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        sql = f"UPDATE jobs SET status=?, updated=?" + (f", {cols}" if cols else "") + " WHERE id=?"
        with self._lock:
            self._db.execute(sql, (status, time.time(), *fields.values(), jid))
            self._db.commit()

    def get_job(self, jid: str) -> Optional[dict]:
        with self._lock:
            row = self._db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        return dict(row) if row else None

    def incr_tries(self, jid: str) -> int:
        with self._lock:
            self._db.execute("UPDATE jobs SET tries=tries+1, updated=? WHERE id=?", (time.time(), jid))
            self._db.commit()
            row = self._db.execute("SELECT tries FROM jobs WHERE id=?", (jid,)).fetchone()
        return int(row["tries"]) if row else 0

    def requeue_running(self) -> int:
        """Job kẹt ở 'running' do restart -> đưa về 'queued'."""
        with self._lock:
            cur = self._db.execute(
                "UPDATE jobs SET status='queued', updated=? WHERE status IN ('running','queued')",
                (time.time(),))
            self._db.commit()
            return cur.rowcount

    def stats(self) -> dict:
        with self._lock:
            rows = self._db.execute(
                "SELECT status, COUNT(*) n FROM jobs GROUP BY status").fetchall()
            total = self._db.execute("SELECT COUNT(*) n FROM jobs").fetchone()["n"]
            cached = self._db.execute("SELECT COUNT(*) n FROM cache").fetchone()["n"]
        by = {r["status"]: r["n"] for r in rows}
        return {"total_jobs": total, "by_status": by, "cached_links": cached}

    def recent(self, limit: int = 20) -> list[dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id,url,provider,status,destination,elapsed_ms,cached,created"
                " FROM jobs ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------- cache
    def cache_get(self, provider: str, key: str, ttl: int) -> Optional[str]:
        with self._lock:
            row = self._db.execute(
                "SELECT destination, updated FROM cache WHERE provider=? AND key=?",
                (provider, key)).fetchone()
        if not row:
            return None
        if ttl > 0 and (time.time() - row["updated"]) > ttl:
            return None
        with self._lock:
            self._db.execute(
                "UPDATE cache SET hits=hits+1 WHERE provider=? AND key=?", (provider, key))
            self._db.commit()
        return row["destination"]

    def cache_put(self, provider: str, key: str, destination: str) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO cache(provider,key,destination,updated,hits) VALUES(?,?,?,?,0)"
                " ON CONFLICT(provider,key) DO UPDATE SET destination=excluded.destination,"
                " updated=excluded.updated",
                (provider, key, destination, time.time()))
            self._db.commit()

    def close(self) -> None:
        try:
            with self._lock:
                self._db.close()
        except Exception:
            pass
