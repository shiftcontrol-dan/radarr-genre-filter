from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS ratings_cache (
    tmdb_id     INTEGER PRIMARY KEY,
    imdb_id     TEXT,
    imdb        REAL,
    rt          INTEGER,
    metacritic  INTEGER,
    tmdb        REAL,
    popularity  REAL,
    fetched_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS keep_list (
    tmdb_id   INTEGER PRIMARY KEY,
    title     TEXT NOT NULL,
    reason    TEXT,
    source    TEXT NOT NULL DEFAULT 'user',
    added_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    mode    TEXT NOT NULL,
    params  TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    run_id      INTEGER NOT NULL,
    tmdb_id     INTEGER NOT NULL,
    radarr_id   INTEGER,
    title       TEXT,
    year        INTEGER,
    genres      TEXT,
    imdb        REAL,
    rt          INTEGER,
    metacritic  INTEGER,
    tmdb        REAL,
    size_bytes  INTEGER,
    seasonal    INTEGER NOT NULL DEFAULT 0,
    verdict     TEXT,
    reason      TEXT,
    PRIMARY KEY (run_id, tmdb_id)
);

CREATE TABLE IF NOT EXISTS deletions (
    tmdb_id     INTEGER,
    radarr_id   INTEGER,
    title       TEXT,
    size_bytes  INTEGER,
    exclusion   INTEGER,
    seasonal    INTEGER,
    deleted_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Db:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- ratings cache -------------------------------------------------
    def get_rating(self, tmdb_id: int, ttl_days: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM ratings_cache WHERE tmdb_id = ?", (tmdb_id,)
        ).fetchone()
        if not row:
            return None
        age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(row["fetched_at"])).days
        if age_days > ttl_days:
            return None
        return dict(row)

    def put_rating(
        self,
        tmdb_id: int,
        imdb_id: str | None,
        imdb: float | None,
        rt: int | None,
        metacritic: int | None,
        tmdb: float | None,
        popularity: float | None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO ratings_cache (tmdb_id, imdb_id, imdb, rt, metacritic, tmdb, popularity, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(tmdb_id) DO UPDATE SET
                imdb_id=excluded.imdb_id, imdb=excluded.imdb, rt=excluded.rt,
                metacritic=excluded.metacritic, tmdb=excluded.tmdb,
                popularity=excluded.popularity, fetched_at=excluded.fetched_at
            """,
            (tmdb_id, imdb_id, imdb, rt, metacritic, tmdb, popularity, _now()),
        )
        self.conn.commit()

    # --- keep list -----------------------------------------------------
    def is_kept(self, tmdb_id: int | None) -> bool:
        if tmdb_id is None:
            return False
        return (
            self.conn.execute("SELECT 1 FROM keep_list WHERE tmdb_id = ?", (tmdb_id,)).fetchone()
            is not None
        )

    def add_keep(self, tmdb_id: int, title: str, reason: str, source: str = "user") -> None:
        self.conn.execute(
            """
            INSERT INTO keep_list (tmdb_id, title, reason, source, added_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(tmdb_id) DO UPDATE SET
                title=excluded.title, reason=excluded.reason, source=excluded.source
            """,
            (tmdb_id, title, reason, source, _now()),
        )
        self.conn.commit()

    def remove_keep(self, tmdb_id: int) -> None:
        self.conn.execute("DELETE FROM keep_list WHERE tmdb_id = ?", (tmdb_id,))
        self.conn.commit()

    def list_keep(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM keep_list ORDER BY title")]

    # --- runs & candidates --------------------------------------------
    def new_run(self, mode: str, params: dict[str, Any]) -> int:
        cur = self.conn.execute(
            "INSERT INTO runs (ts, mode, params) VALUES (?, ?, ?)",
            (_now(), mode, json.dumps(params, default=str)),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def add_candidate(self, run_id: int, c: dict[str, Any]) -> None:
        payload = dict(c)
        payload["genres"] = ",".join(c.get("genres", []))
        payload["run_id"] = run_id
        self.conn.execute(
            """
            INSERT OR REPLACE INTO candidates
                (run_id, tmdb_id, radarr_id, title, year, genres, imdb, rt, metacritic,
                 tmdb, size_bytes, seasonal, verdict, reason)
            VALUES
                (:run_id, :tmdb_id, :radarr_id, :title, :year, :genres, :imdb, :rt, :metacritic,
                 :tmdb, :size_bytes, :seasonal, :verdict, :reason)
            """,
            payload,
        )
        self.conn.commit()

    def candidates(self, run_id: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM candidates WHERE run_id = ? ORDER BY size_bytes DESC", (run_id,)
        )
        return [dict(r) for r in rows]

    def latest_run(self, mode: str = "report") -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM runs WHERE mode = ? ORDER BY id DESC LIMIT 1", (mode,)
        ).fetchone()
        return dict(row) if row else None

    # --- deletion audit ------------------------------------------------
    def log_deletion(
        self,
        tmdb_id: int | None,
        radarr_id: int | None,
        title: str,
        size_bytes: int,
        exclusion: bool,
        seasonal: bool,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO deletions (tmdb_id, radarr_id, title, size_bytes, exclusion, seasonal, deleted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (tmdb_id, radarr_id, title, size_bytes, int(exclusion), int(seasonal), _now()),
        )
        self.conn.commit()
