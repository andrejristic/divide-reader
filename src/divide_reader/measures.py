"""The summer: measures over sets of readings.

Two versions of every measure:
- simple: a unit's reading set is the union of what all listeners heard;
  every found reading counts once.
- weighted: computed per (unit, listener) pair and averaged, so a reading
  heard by 4 of 5 listeners weighs four times as much as one heard by one.
"""
from __future__ import annotations

import json
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import partitions as P
from .store import Store

MAJORITY = 0.6  # "heard by at least three of five"


@dataclass
class Reading:
    key: str
    s: int
    heard_by: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    assumed: list[str] = field(default_factory=list)

    def weight(self, n_passes: int) -> float:
        return len(self.heard_by) / n_passes if n_passes else 0.0


@dataclass
class UnitResult:
    unit_id: int
    text: str
    lang: str | None
    F: int
    figures: list[str]
    mode: str
    n_passes: int
    readings: dict[str, Reading]
    per_listener: dict[str, set[str]]   # pass label -> keys heard
    rejected: list[tuple[str, int, str]]  # key, S, reason

    @property
    def s_values(self) -> set[int]:
        return {r.s for r in self.readings.values()}

    @property
    def complete(self) -> bool:
        return self.mode in ("enumerate", "trivial")

    def shown(self, limit: int = 5) -> tuple[list[Reading], list[Reading]]:
        """Up to `limit` readings: the most heard per S first, then the rest by count; display order S, count."""
        rs = sorted(self.readings.values(), key=lambda r: (-len(r.heard_by), len(r.assumed), r.s))
        best: dict[int, Reading] = {}
        for r in rs:
            best.setdefault(r.s, r)
        picked = list(best.values())[:limit]
        for r in rs:
            if len(picked) >= limit:
                break
            if r not in picked:
                picked.append(r)
        picked.sort(key=lambda r: (r.s, -len(r.heard_by)))
        rest = [r for r in rs if r not in picked]
        rest.sort(key=lambda r: (r.s, -len(r.heard_by)))
        return picked, rest


def load_unit(store: Store, unit_id: int, rounds: list[int] | None = None) -> UnitResult | None:
    u = store.one("SELECT id, text, lang FROM unit WHERE id=?", (unit_id,))
    lock = store.one("SELECT n FROM figure_lock WHERE unit_id=?", (unit_id,))
    if u is None or lock is None:
        return None
    rnds = store.q("SELECT id, round_no, mode FROM round WHERE unit_id=? AND complete=1 ORDER BY round_no",
                   (unit_id,))
    if rounds:
        rnds = [r for r in rnds if r["round_no"] in rounds]
    if not rnds:
        return None
    figures = store.locked_figures(unit_id) or []
    readings: dict[str, Reading] = {}
    per_listener: dict[str, set[str]] = defaultdict(set)
    rejected: dict[str, tuple[str, int, str]] = {}
    n_passes = 0
    for rnd in rnds:
        passes = store.q("SELECT id, listener FROM pass WHERE round_id=?", (rnd["id"],))
        n_passes += len(passes)
        for p in passes:
            label = f"{p['listener']}#{rnd['round_no']}"
            per_listener[label]  # noqa: B018  (a pass that heard nothing still counts)
            for r in store.q("SELECT * FROM reading WHERE pass_id=?", (p["id"],)):
                if r["rkey"] == "invalid":
                    continue
                if not r["supported"]:
                    rejected.setdefault(r["rkey"], (r["rkey"], r["s"], r["reject_reason"] or ""))
                    continue
                rd = readings.get(r["rkey"])
                if rd is None:
                    rd = readings[r["rkey"]] = Reading(r["rkey"], r["s"], assumed=json.loads(r["assumed"] or "[]"))
                if label not in rd.heard_by:
                    rd.heard_by.append(label)
                if r["assumption"] and r["assumption"] not in rd.assumptions:
                    rd.assumptions.append(r["assumption"])
                if r["anchor"] and r["anchor"] not in rd.anchors:
                    rd.anchors.append(r["anchor"])
                per_listener[label].add(r["rkey"])
    for k in readings:
        rejected.pop(k, None)
    return UnitResult(u["id"], u["text"], u["lang"], lock["n"], figures, rnds[0]["mode"], n_passes,
                      readings, dict(per_listener), list(rejected.values()))


def source_units(store: Store, source_id: int, kind: str = "sentence") -> list[int]:
    return [r["id"] for r in store.q("""SELECT u.id FROM unit u JOIN page p ON p.id = u.page_id
                                         WHERE p.source_id=? AND u.kind=? ORDER BY p.id, u.idx""",
                                      (source_id, kind))]


def sample_units(unit_ids: list[int], n: int | None, seed: int = 7) -> list[int]:
    """Equal-size sample per source, spread over the whole text (fixed seed, so it is repeatable)."""
    if n is None or n >= len(unit_ids):
        return list(unit_ids)
    picked = random.Random(seed).sample(range(len(unit_ids)), n)
    return [unit_ids[i] for i in sorted(picked)]


def _keys_s(keys: set[str], results: UnitResult) -> set[int]:
    return {results.readings[k].s for k in keys if k in results.readings}


def compute(results: list[UnitResult]) -> dict:
    """All measures for one set of units (one source, one unit kind)."""
    n = len(results)
    out: dict = {"units": n}
    if not n:
        return out
    f3 = [r for r in results if r.F >= 3]

    def simple_frac(pool, pred):
        return (sum(1 for r in pool if pred(r.s_values, r)) / len(pool)) if pool else None

    def weighted_frac(pool, pred):
        num = den = 0
        for r in pool:
            for keys in r.per_listener.values():
                den += 1
                num += 1 if pred(_keys_s(keys, r), r) else 0
        return num / den if den else None

    locked = lambda s, r: s == {2}                       # noqa: E731
    open_ = lambda s, r: 2 in s and len(s) > 1           # noqa: E731
    honest = lambda s, r: r.F == 2 and 2 in s            # noqa: E731

    out["locked_two"] = {"simple": simple_frac(f3, locked), "weighted": weighted_frac(f3, locked), "n": len(f3),
                         "units": [r.unit_id for r in f3 if locked(r.s_values, r)]}
    out["open_two"] = {"simple": simple_frac(f3, open_), "weighted": weighted_frac(f3, open_), "n": len(f3),
                       "units": [r.unit_id for r in f3 if open_(r.s_values, r)]}
    out["honest_two"] = {"simple": simple_frac(results, honest), "weighted": weighted_frac(results, honest),
                         "n": n, "units": [r.unit_id for r in results if honest(r.s_values, r)]}

    dist_s: Counter[str] = Counter()
    dist_w: Counter[str] = Counter()
    for r in results:
        for rd in r.readings.values():
            b = str(rd.s) if rd.s < 5 else "5+"
            dist_s[b] += 1
            dist_w[b] += rd.weight(r.n_passes)
    out["s_distribution"] = {"simple": dict(dist_s), "weighted": {k: round(v, 3) for k, v in dist_w.items()}}

    def spread(svals):
        return (max(svals) - min(svals)) if svals else 0

    out["range"] = {
        "simple": statistics.mean(spread(r.s_values) for r in results),
        "weighted": _mean([spread(_keys_s(k, r)) for r in results for k in r.per_listener.values()]),
        "n": n,
    }
    counts = [len(r.readings) for r in results]
    out["readings_per_unit"] = {
        "simple": statistics.mean(counts), "max": max(counts),
        "weighted": _mean([len(k) for r in results for k in r.per_listener.values()]), "n": n,
    }
    majority = [rd.s for r in results for rd in r.readings.values() if rd.weight(r.n_passes) >= MAJORITY]
    out["max_s"] = {"simple": max((rd.s for r in results for rd in r.readings.values()), default=0),
                    "majority": max(majority, default=0)}
    out["incomplete_units"] = [r.unit_id for r in results if not r.complete]
    out["no_reading_units"] = [r.unit_id for r in results if not r.readings]
    return out


def _mean(xs: list[float]) -> float | None:
    return statistics.mean(xs) if xs else None


def stability(store: Store, unit_ids: list[int]) -> dict:
    """Jaccard between round 1 and round 2 reading sets, overall and per language."""
    scores: list[float] = []
    by_lang: dict[str, list[float]] = defaultdict(list)
    for uid in unit_ids:
        a = load_unit(store, uid, rounds=[1])
        b = load_unit(store, uid, rounds=[2])
        if a is None or b is None:
            continue
        j = P.jaccard(set(a.readings), set(b.readings))
        scores.append(j)
        by_lang[a.lang or "?"].append(j)
    return {"mean": _mean(scores), "n": len(scores),
            "by_lang": {k: {"mean": _mean(v), "n": len(v)} for k, v in by_lang.items()}}


def manual_check(store: Store, annotator: str | None = None, role: str = "check") -> dict:
    """Coverage: share of the human's S values the program also found. Excess: share of the program's S values the human did not see."""
    sql = "SELECT unit_id, s_values FROM manual WHERE role=?"
    args: tuple = (role,)
    if annotator:
        sql += " AND annotator=?"
        args += (annotator,)
    covered = total_h = extra = total_p = 0
    misses = []
    for row in store.q(sql, args):
        res = load_unit(store, row["unit_id"])
        if res is None:
            continue
        human = set(json.loads(row["s_values"]))
        prog = res.s_values
        total_h += len(human)
        covered += len(human & prog)
        total_p += len(prog)
        extra += len(prog - human)
        if human - prog:
            misses.append(row["unit_id"])
    return {"coverage": covered / total_h if total_h else None,
            "excess": extra / total_p if total_p else None,
            "n_units": len(store.q(sql, args)), "missed_units": misses}


def compare_models(store: Store, unit_ids: list[int], model_a: str, model_b: str) -> list[int]:
    """Units where two models' S sets differ (they go to manual review)."""
    diff = []
    for uid in unit_ids:
        sets = {}
        for m in (model_a, model_b):
            rnos = [r["round_no"] for r in store.q(
                "SELECT round_no FROM round WHERE unit_id=? AND model=? AND complete=1", (uid, m))]
            res = load_unit(store, uid, rounds=rnos) if rnos else None
            sets[m] = res.s_values if res else None
        if sets[model_a] is not None and sets[model_b] is not None and sets[model_a] != sets[model_b]:
            diff.append(uid)
    return diff


def other_counts(store: Store, unit_ids: list[int]) -> dict[str, list[dict]]:
    """Other countables grouped by what is counted."""
    groups: dict[str, list[dict]] = defaultdict(list)
    if not unit_ids:
        return {}
    marks = ",".join("?" for _ in unit_ids)
    seen = set()
    for r in store.q(f"SELECT unit_id, what, amount, anchor FROM other_count WHERE unit_id IN ({marks})",
                     tuple(unit_ids)):
        what = r["what"].strip().lower()
        k = (r["unit_id"], what, r["anchor"])
        if k in seen:
            continue
        seen.add(k)
        groups[what].append({"unit_id": r["unit_id"], "amount": r["amount"], "anchor": r["anchor"]})
    return dict(sorted(groups.items(), key=lambda kv: -len(kv[1])))
