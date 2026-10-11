"""The shared store: one SQLite file holding every intermediate result.

Every part (walker, cleaner, reader, summer, writer) reads from and writes to
this file, so each part can be rerun without the ones before it.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

-- One source is one speaker: a site, a book, a file.
CREATE TABLE IF NOT EXISTS source (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    kind TEXT NOT NULL,              -- site | file | book | page
    origin TEXT,                     -- start URL or file path
    walk_mode TEXT,                  -- list | wander | file
    created REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS page (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES source(id),
    url TEXT,
    fetched_at REAL NOT NULL,
    snapshot TEXT,                   -- live | wayback:<timestamp> | file
    status TEXT NOT NULL,            -- ok | skipped:<reason>
    html BLOB,
    sha256 TEXT,
    title TEXT,
    text TEXT,
    lang TEXT
);
CREATE INDEX IF NOT EXISTS page_source ON page(source_id);
CREATE INDEX IF NOT EXISTS page_sha ON page(sha256);

CREATE TABLE IF NOT EXISTS unit (
    id INTEGER PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES page(id),
    kind TEXT NOT NULL,              -- sentence | paragraph | article | chapter
    idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    ctx_before TEXT,
    ctx_after TEXT,
    lang TEXT,
    UNIQUE(page_id, kind, idx)
);

-- Raw figure extractions (three per unit) and the locked list.
CREATE TABLE IF NOT EXISTS figure_attempt (
    id INTEGER PRIMARY KEY,
    unit_id INTEGER NOT NULL REFERENCES unit(id),
    attempt INTEGER NOT NULL,
    model TEXT NOT NULL,
    figures TEXT NOT NULL,           -- JSON list of strings
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS figure (
    unit_id INTEGER NOT NULL REFERENCES unit(id),
    idx INTEGER NOT NULL,            -- f0, f1, ...
    text TEXT NOT NULL,
    votes INTEGER NOT NULL,
    PRIMARY KEY(unit_id, idx)
);
CREATE TABLE IF NOT EXISTS figure_lock (
    unit_id INTEGER PRIMARY KEY REFERENCES unit(id),
    n INTEGER NOT NULL,
    model TEXT NOT NULL,
    created REAL NOT NULL
);

-- A round is one pass of all five listeners over a unit.
CREATE TABLE IF NOT EXISTS round (
    id INTEGER PRIMARY KEY,
    unit_id INTEGER NOT NULL REFERENCES unit(id),
    round_no INTEGER NOT NULL,
    model TEXT NOT NULL,
    rules_version TEXT NOT NULL,
    mode TEXT NOT NULL,              -- enumerate (F<=5) | propose (F>=6) | trivial
    created REAL NOT NULL,
    complete INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS round_unit ON round(unit_id);

CREATE TABLE IF NOT EXISTS pass (
    id INTEGER PRIMARY KEY,
    round_id INTEGER NOT NULL REFERENCES round(id),
    listener TEXT NOT NULL,
    model TEXT NOT NULL,
    raw TEXT,
    in_tokens INTEGER,
    out_tokens INTEGER,
    cost_usd REAL,
    created REAL NOT NULL
);

-- Every judged partition. Rejected ones stay, with the reason.
CREATE TABLE IF NOT EXISTS reading (
    id INTEGER PRIMARY KEY,
    pass_id INTEGER NOT NULL REFERENCES pass(id),
    rkey TEXT NOT NULL,              -- canonical RGS over explicit + assumed figures
    s INTEGER NOT NULL,
    supported INTEGER NOT NULL,
    assumed TEXT,                    -- JSON list of assumed figure names, appended after explicit ones
    assumption TEXT,
    anchor TEXT,
    reject_reason TEXT
);
CREATE INDEX IF NOT EXISTS reading_pass ON reading(pass_id);

CREATE TABLE IF NOT EXISTS other_count (
    id INTEGER PRIMARY KEY,
    unit_id INTEGER NOT NULL REFERENCES unit(id),
    pass_id INTEGER REFERENCES pass(id),
    what TEXT NOT NULL,
    amount REAL,
    anchor TEXT
);

-- Manual counts: the set of S values (and optionally partitions) a person sees.
CREATE TABLE IF NOT EXISTS manual (
    id INTEGER PRIMARY KEY,
    unit_id INTEGER NOT NULL REFERENCES unit(id),
    annotator TEXT NOT NULL,
    role TEXT NOT NULL,              -- example | check
    s_values TEXT NOT NULL,          -- JSON list of ints
    rkeys TEXT,                      -- JSON list of keys, optional
    note TEXT,
    created REAL NOT NULL,
    UNIQUE(unit_id, annotator)
);

-- Hypotheses about a whole text, written by the summer.
CREATE TABLE IF NOT EXISTS hypothesis (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES source(id),
    text TEXT NOT NULL,
    support TEXT,                    -- JSON list of unit ids
    against TEXT,                    -- JSON list of unit ids
    model TEXT,
    created REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS job (
    id TEXT PRIMARY KEY,
    source_id INTEGER REFERENCES source(id),
    spec TEXT NOT NULL,              -- JSON of the job settings
    units TEXT NOT NULL,             -- JSON list of unit ids (the sample)
    created REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS spend (
    id INTEGER PRIMARY KEY,
    job TEXT NOT NULL,
    model TEXT NOT NULL,
    cost_usd REAL NOT NULL,
    created REAL NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        self.db.executescript(SCHEMA)
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # --- generic helpers -------------------------------------------------
    def q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        return self.db.execute(sql, args).fetchall()

    def one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        return self.db.execute(sql, args).fetchone()

    def insert(self, table: str, **cols) -> int:
        names = ", ".join(cols)
        marks = ", ".join("?" for _ in cols)
        cur = self.db.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})", tuple(cols.values()))
        return cur.lastrowid

    def commit(self) -> None:
        self.db.commit()

    # --- sources and pages ----------------------------------------------
    def add_source(self, label: str, kind: str, origin: str | None = None, walk_mode: str | None = None) -> int:
        sid = self.insert("source", label=label, kind=kind, origin=origin, walk_mode=walk_mode, created=time.time())
        self.commit()
        return sid

    def has_page_hash(self, source_id: int, sha: str) -> bool:
        return self.one("SELECT 1 FROM page WHERE source_id=? AND sha256=? AND status='ok'", (source_id, sha)) is not None

    # --- figures ---------------------------------------------------------
    def locked_figures(self, unit_id: int) -> list[str] | None:
        if not self.one("SELECT 1 FROM figure_lock WHERE unit_id=?", (unit_id,)):
            return None
        return [r["text"] for r in self.q("SELECT text FROM figure WHERE unit_id=? ORDER BY idx", (unit_id,))]

    def lock_figures(self, unit_id: int, figures: list[tuple[str, int]], model: str) -> None:
        self.db.execute("DELETE FROM figure WHERE unit_id=?", (unit_id,))
        for i, (text, votes) in enumerate(figures):
            self.insert("figure", unit_id=unit_id, idx=i, text=text, votes=votes)
        self.db.execute("INSERT OR REPLACE INTO figure_lock VALUES (?, ?, ?, ?)",
                        (unit_id, len(figures), model, time.time()))
        self.commit()

    # --- readings --------------------------------------------------------
    def unit_readings(self, unit_id: int, rounds: list[int] | None = None) -> list[sqlite3.Row]:
        """All supported readings for a unit, one row per (pass, key)."""
        sql = """SELECT r.*, p.listener, p.round_id, rd.round_no FROM reading r
                 JOIN pass p ON p.id = r.pass_id JOIN round rd ON rd.id = p.round_id
                 WHERE rd.unit_id = ? AND rd.complete = 1 AND r.supported = 1"""
        args: tuple = (unit_id,)
        if rounds:
            sql += f" AND rd.round_no IN ({','.join('?' for _ in rounds)})"
            args += tuple(rounds)
        return self.q(sql, args)

    def total_spend(self, job: str) -> float:
        row = self.one("SELECT COALESCE(SUM(cost_usd), 0) AS s FROM spend WHERE job=?", (job,))
        return float(row["s"])


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)
