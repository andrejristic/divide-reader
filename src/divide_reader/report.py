"""The writer: HTML report per source, comparison report, and measures CSV."""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
from pathlib import Path

import jinja2

from . import measures, partitions as P, prompts
from .i18n import T
from .store import Store

SHARE_MEASURES = ("locked_two", "open_two", "honest_two")
NUM_MEASURES = ("range", "readings_per_unit")

_env = jinja2.Environment(loader=jinja2.PackageLoader("divide_reader", "templates"),
                          autoescape=jinja2.select_autoescape(["html", "j2"]))


def _slug(s: str) -> str:
    return re.sub(r"[^\w.-]+", "-", s).strip("-")[:60] or "source"


def _fmt(v, pct=False) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.1f}%" if pct else f"{v:.2f}"


def source_info(store: Store, source_id: int, unit_ids: list[int]) -> dict:
    src = store.one("SELECT * FROM source WHERE id=?", (source_id,))
    pages = store.q("SELECT url, fetched_at, snapshot, status, title FROM page WHERE source_id=? ORDER BY id",
                    (source_id,))
    marks = ",".join("?" for _ in unit_ids) or "NULL"
    models = [r["model"] for r in store.q(
        f"SELECT DISTINCT model FROM round WHERE unit_id IN ({marks}) AND model != 'rule'", tuple(unit_ids))]
    rules = [r["rules_version"] for r in store.q(
        f"SELECT DISTINCT rules_version FROM round WHERE unit_id IN ({marks})", tuple(unit_ids))]
    kind = store.one(f"SELECT kind FROM unit WHERE id IN ({marks}) LIMIT 1", tuple(unit_ids))
    return {
        "label": src["label"], "origin": src["origin"], "walk_mode": src["walk_mode"],
        "ok_pages": [dict(p) | {"date": dt.datetime.fromtimestamp(p["fetched_at"]).strftime("%Y-%m-%d %H:%M")}
                     for p in pages if p["status"] == "ok"],
        "skipped": [dict(p) for p in pages if p["status"] != "ok"],
        "models": models, "rules": rules or [prompts.RULES_VERSION],
        "unit_kind": kind["kind"] if kind else "sentence",
    }


def measure_rows(m: dict, stab: dict, t: T) -> list[dict]:
    rows = []
    for k in SHARE_MEASURES:
        if k in m:
            rows.append({"key": k, "name": t(k), "simple": _fmt(m[k]["simple"], True),
                         "weighted": _fmt(m[k]["weighted"], True), "n": m[k]["n"], "units": m[k]["units"]})
    if "range" in m:
        rows.append({"key": "range", "name": t("range"), "simple": _fmt(m["range"]["simple"]),
                     "weighted": _fmt(m["range"]["weighted"]), "n": m["range"]["n"], "units": []})
        r = m["readings_per_unit"]
        rows.append({"key": "readings_per_unit", "name": t("readings_per_unit"),
                     "simple": f"{_fmt(r['simple'])} / {r['max']}", "weighted": _fmt(r["weighted"]),
                     "n": r["n"], "units": []})
        rows.append({"key": "max_s", "name": t("max_s"), "simple": str(m["max_s"]["simple"]),
                     "weighted": str(m["max_s"]["majority"]), "n": m["units"], "units": []})
    return rows


def unit_view(r: measures.UnitResult, t: T) -> dict:
    names = list(r.figures)

    def view(rd: measures.Reading) -> dict:
        all_names = names + rd.assumed
        return {"s": rd.s, "desc": P.describe(P.parse_key(rd.key), all_names) if rd.key else "∅",
                "heard": t("heard", k=len(rd.heard_by), n=r.n_passes),
                "listeners": ", ".join(sorted({h.split("#")[0] for h in rd.heard_by})),
                "assumptions": rd.assumptions[:3], "anchors": rd.anchors[:3], "assumed": rd.assumed}

    shown, rest = r.shown()
    groups: dict[int, list[dict]] = {}
    for rd in rest:
        groups.setdefault(rd.s, []).append(view(rd))
    found = (t("readings_found", n=len(r.readings), b=P.bell(r.F)) if r.complete
             else t("readings_found_open", n=len(r.readings)))
    rejected = [{"s": s, "desc": P.describe(P.parse_key(k), names) if k else "∅", "reason": why}
                for k, s, why in sorted(r.rejected, key=lambda x: x[1])]
    return {"id": r.unit_id, "text": r.text, "F": r.F, "figures": names, "found": found,
            "shown": [view(x) for x in shown], "rest": groups, "n_rest": len(rest), "rejected": rejected}


def write_source_report(store: Store, source_id: int, out_dir: Path, lang: str = "en",
                        kind: str = "sentence", unit_ids: list[int] | None = None) -> Path:
    t = T(lang)
    unit_ids = unit_ids or measures.source_units(store, source_id, kind)
    results = [r for r in (measures.load_unit(store, u) for u in unit_ids) if r is not None]
    read_ids = [r.unit_id for r in results]
    m = measures.compute(results)
    stab = measures.stability(store, read_ids)
    hyps = [{"text": h["text"], "support": json.loads(h["support"] or "[]"),
             "against": json.loads(h["against"] or "[]")}
            for h in store.q("SELECT * FROM hypothesis WHERE source_id=? ORDER BY id", (source_id,))]
    info = source_info(store, source_id, read_ids or unit_ids)
    out_dir.mkdir(parents=True, exist_ok=True)
    html = _env.get_template("report.html.j2").render(
        t=t, lang=lang, info=info, m=m, rows=measure_rows(m, stab, t), stab=stab, hyps=hyps,
        units=[unit_view(r, t) for r in results], other=measures.other_counts(store, read_ids),
        texts={r.unit_id: r.text for r in results},
        generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    path = out_dir / "report.html"
    path.write_text(html, encoding="utf-8")
    write_csv(out_dir / "measures.csv", [(info["label"], m, stab)])
    return path


def write_csv(path: Path, items: list[tuple[str, dict, dict]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "measure", "simple", "weighted", "n", "stability", "stability_n"])
        for label, m, stab in items:
            for k in SHARE_MEASURES:
                if k in m:
                    w.writerow([label, k, m[k]["simple"], m[k]["weighted"], m[k]["n"], stab["mean"], stab["n"]])
            if "range" in m:
                w.writerow([label, "range", m["range"]["simple"], m["range"]["weighted"], m["units"],
                            stab["mean"], stab["n"]])
                r = m["readings_per_unit"]
                w.writerow([label, "readings_per_unit", r["simple"], r["weighted"], m["units"], stab["mean"], stab["n"]])
                w.writerow([label, "max_s", m["max_s"]["simple"], m["max_s"]["majority"], m["units"],
                            stab["mean"], stab["n"]])
                for b, v in sorted(m["s_distribution"]["simple"].items()):
                    w.writerow([label, f"s_count_{b}", v, m["s_distribution"]["weighted"].get(b), m["units"],
                                stab["mean"], stab["n"]])


def noise(store: Store, unit_ids: list[int]) -> dict[str, float | None]:
    """Per-measure difference between round 1 and round 2 of the same units."""
    twice = [u for u in unit_ids
             if store.one("SELECT 1 FROM round WHERE unit_id=? AND round_no=2 AND complete=1", (u,))]
    a = [r for r in (measures.load_unit(store, u, rounds=[1]) for u in twice) if r]
    b = [r for r in (measures.load_unit(store, u, rounds=[2]) for u in twice) if r]
    if not a or not b:
        return {}
    ma, mb = measures.compute(a), measures.compute(b)
    out = {}
    for k in SHARE_MEASURES + NUM_MEASURES:
        va, vb = ma[k]["simple"], mb[k]["simple"]
        out[k] = abs(va - vb) if va is not None and vb is not None else None
    return out


def write_comparison(store: Store, sources: list[tuple[int, str]], out_dir: Path, lang: str = "en",
                     kind: str = "sentence") -> Path:
    """Two (or more) sources side by side. A difference counts as a finding only when it is larger than the noise."""
    t = T(lang)
    cols, csv_items, noises = [], [], []
    for sid, label in sources:
        ids = measures.source_units(store, sid, kind)
        results = [r for r in (measures.load_unit(store, u) for u in ids) if r is not None]
        m = measures.compute(results)
        stab = measures.stability(store, [r.unit_id for r in results])
        cols.append({"label": label, "m": m, "stab": stab})
        csv_items.append((label, m, stab))
        noises.append(noise(store, [r.unit_id for r in results]))
    rows = []
    for k in SHARE_MEASURES + NUM_MEASURES:
        vals = [c["m"].get(k, {}).get("simple") for c in cols]
        pct = k in SHARE_MEASURES
        nz = [n.get(k) for n in noises if n.get(k) is not None]
        threshold = max(nz) if nz else None
        diff = (vals[1] - vals[0]) if len(vals) >= 2 and None not in vals[:2] else None
        verdict = ""
        if diff is not None and threshold is not None:
            verdict = t("finding") if abs(diff) > threshold else t("within_noise")
        rows.append({"name": t(k), "vals": [_fmt(v, pct) for v in vals], "diff": _fmt(diff, pct),
                     "noise": _fmt(threshold, pct), "verdict": verdict})
    out_dir.mkdir(parents=True, exist_ok=True)
    html = _env.get_template("compare.html.j2").render(t=t, lang=lang, cols=cols, rows=rows,
                                                        generated=dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    path = out_dir / "compare.html"
    path.write_text(html, encoding="utf-8")
    write_csv(out_dir / "measures.csv", csv_items)
    return path


def default_out_dir(project: Path, label: str) -> Path:
    return project / "reports" / f"{_slug(label)}-{dt.datetime.now():%Y%m%d-%H%M}"
