"""One job from start to finish: input -> units -> reading -> second round -> hypotheses -> report.

Used by both the GUI and the command line.
"""
from __future__ import annotations

import json
import random
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import ingest, measures, paths, report, summer, walker
from .providers.base import BudgetExceeded, LLMError, Provider, RateLimited
from .reader import Budget, Reader
from .store import Store

SECOND_ROUND_SHARE = 0.10


@dataclass
class JobSpec:
    input: str                      # file path or URL
    input_kind: str = "auto"        # auto | file | page | list | wander | wayback
    unit_kind: str = "sentence"     # sentence | paragraph | article | chapter
    sample: int | None = 200        # units per source; None = all
    max_pages: int = 30
    max_hops: int = 3
    wayback_year: int | None = None
    cost_cap: float | None = None
    second_round_share: float = SECOND_ROUND_SHARE
    hypotheses: bool = True
    report_lang: str = "en"
    label: str | None = None
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


@dataclass
class JobResult:
    source_id: int | None = None
    report: Path | None = None
    units_read: int = 0
    stopped_reason: str = ""
    resume_at: float | None = None


def project_dir(name: str = "default") -> Path:
    d = paths.projects_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def open_store(project: Path) -> Store:
    return Store(project / "store.sqlite")


def resolve_kind(spec: JobSpec) -> str:
    if spec.input_kind != "auto":
        return spec.input_kind
    if spec.input.startswith(("http://", "https://")):
        return "wayback" if spec.wayback_year else "list"
    return "file"


def collect(store: Store, spec: JobSpec, log: Callable[[str], None], stop: threading.Event) -> tuple[int, list[int]]:
    """Get the input into the store; return (source id, unit ids to read)."""
    kind = resolve_kind(spec)
    if kind == "file":
        sid, units = ingest.ingest_file(store, spec.input, spec.unit_kind)
        if spec.label:
            store.db.execute("UPDATE source SET label=? WHERE id=?", (spec.label, sid))
            store.commit()
    elif kind == "page":
        sid = store.add_source(spec.label or spec.input, "page", spec.input, "page")
        pages, _ = walker.fetch_one(store, walker.Fetcher(), sid, spec.input)
        units = ingest.make_units(store, pages, spec.unit_kind)
    elif kind in ("list", "wander"):
        sid = walker.walk(store, spec.input, kind, spec.max_pages, spec.max_hops, log=log, stop=stop,
                          label=spec.label)
        pages = [r["id"] for r in store.q("SELECT id FROM page WHERE source_id=? AND status='ok'", (sid,))]
        units = ingest.make_units(store, pages, spec.unit_kind)
    elif kind == "wayback":
        if not spec.wayback_year:
            raise ValueError("wayback needs a year")
        sid, pages = walker.fetch_wayback(store, spec.input, spec.wayback_year, spec.label)
        units = ingest.make_units(store, pages, spec.unit_kind)
    else:
        raise ValueError(f"unknown input kind {kind}")
    return sid, measures.sample_units(units, spec.sample)


def run(spec: JobSpec, provider: Provider, project: Path | None = None,
        log: Callable[[str], None] = print, progress: Callable[[str, int, int], None] | None = None,
        stop: threading.Event | None = None, source_id: int | None = None) -> JobResult:
    stop = stop or threading.Event()
    project = project or project_dir()
    store = open_store(project)
    res = JobResult()
    try:
        if source_id is None:
            log(f"collecting {spec.input}")
            sid, units = collect(store, spec, log, stop)
            _save_job(store, spec, sid, units)
        else:
            sid, units = source_id, _load_job_units(store, spec.job_id, source_id, spec)
        res.source_id = sid
        log(f"{len(units)} units to read")
        budget = Budget(store, spec.job_id, spec.cost_cap)
        reader = Reader(store, provider, budget, spec.report_lang, log=log, stop=stop)
        try:
            reader.read_units(units, progress=(lambda i, n: progress("read", i, n)) if progress else None)
            twice = random.Random(spec.job_id).sample(units, max(1, round(len(units) * spec.second_round_share))) \
                if units and spec.second_round_share > 0 else []
            for i, uid in enumerate(twice):
                if stop.is_set():
                    break
                if store.one("SELECT 1 FROM round WHERE unit_id=? AND round_no=2 AND complete=1", (uid,)):
                    continue
                if store.one("SELECT mode FROM round WHERE unit_id=? AND round_no=1", (uid,))["mode"] == "trivial":
                    continue
                try:
                    reader.read_unit(uid, new_round=True)
                except LLMError as e:
                    log(f"second round, unit {uid}: {e}")
                if progress:
                    progress("second", i + 1, len(twice))
            if spec.hypotheses and not stop.is_set():
                log("writing hypotheses")
                try:
                    summer.write_hypotheses(store, provider, budget, sid, units, spec.report_lang)
                except LLMError as e:
                    log(f"hypotheses: {e}")
        except BudgetExceeded as e:
            res.stopped_reason = str(e)
            log(f"stopped: {e}")
        except RateLimited as e:
            res.stopped_reason = str(e)
            res.resume_at = e.retry_at
            log(f"paused: {e}. Resume later; finished work is saved.")
        except InterruptedError:
            res.stopped_reason = "stopped by user"
        if budget.unknown_cost_calls:
            log(f"{budget.unknown_cost_calls} calls had unknown cost (no price set for this model)")
        res.units_read = sum(1 for u in units if store.one(
            "SELECT 1 FROM round WHERE unit_id=? AND complete=1", (u,)))
        label = store.one("SELECT label FROM source WHERE id=?", (sid,))["label"]
        res.report = report.write_source_report(store, sid, report.default_out_dir(project, label),
                                                spec.report_lang, spec.unit_kind, units)
        log(f"report: {res.report}")
        return res
    finally:
        store.close()


def _save_job(store: Store, spec: JobSpec, sid: int, units: list[int]) -> None:
    store.db.execute("INSERT OR REPLACE INTO job VALUES (?, ?, ?, ?, ?)",
                     (spec.job_id, sid, json.dumps(spec.__dict__), json.dumps(units), time.time()))
    store.commit()


def _load_job_units(store: Store, job_id: str, sid: int, spec: JobSpec) -> list[int]:
    row = store.one("SELECT units FROM job WHERE id=?", (job_id,))
    if row:
        return json.loads(row["units"])
    return measures.sample_units(measures.source_units(store, sid, spec.unit_kind), spec.sample)


def list_jobs(store: Store) -> list[dict]:
    out = []
    for r in store.q("SELECT j.*, s.label FROM job j JOIN source s ON s.id = j.source_id ORDER BY j.created DESC"):
        out.append({"id": r["id"], "source_id": r["source_id"], "label": r["label"],
                    "spec": json.loads(r["spec"]), "units": len(json.loads(r["units"])), "created": r["created"]})
    return out


def estimate(n_units: int, avg_partitions: float = 15, price_in: float | None = None,
             price_out: float | None = None, second_share: float = SECOND_ROUND_SHARE) -> dict:
    """Rough calls/tokens/cost for a job, before it runs."""
    calls_per_unit = 3 + 5 * (1 + second_share)
    in_tok = n_units * (3 * 900 + 5 * (1 + second_share) * (1400 + 40 * avg_partitions))
    out_tok = n_units * (3 * 80 + 5 * (1 + second_share) * (90 * avg_partitions))
    cost = None
    if price_in is not None and price_out is not None:
        cost = (in_tok * price_in + out_tok * price_out) / 1e6
    return {"calls": round(n_units * calls_per_unit), "in_tokens": int(in_tok), "out_tokens": int(out_tok),
            "cost_usd": cost}
