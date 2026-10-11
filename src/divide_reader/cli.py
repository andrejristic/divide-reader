"""Command line: divide-reader <command> ...  (the GUI is divide-reader-gui)."""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from . import __version__, auth, download, jobs, measures, report
from .connect import connect
from .providers.catalog import LOCAL_MODELS, PROVIDERS, provider as get_spec, recommend_local


def cmd_models(a) -> None:
    print("Built-in local model (llama.cpp): the JSON grammar forces every answer into the schema,")
    print("so a local model cannot return a malformed answer.\n")
    ram = download.total_ram_gb()
    rec = recommend_local(ram)
    print(f"Local models (this machine: {ram:.0f} GB RAM; recommended: {rec.id}). Direct download links:")
    for m in LOCAL_MODELS:
        mark = "downloaded" if download.is_downloaded(m) else f"{m.size / 1e9:.1f} GB"
        print(f"  {m.id:12} {m.label:40} [{mark}]\n      {m.url}")
    print("\nOnline providers (login opens your web browser):")
    for p in PROVIDERS:
        if p.group in ("free", "paid"):
            ms = ", ".join(m.id for m in p.models) or "(model list loaded live)"
            print(f"  {p.id:10} {p.label:20} {p.group:5} {ms}")


def cmd_download(a) -> None:
    m = next((x for x in LOCAL_MODELS if x.id == a.model), None)
    if m is None:
        sys.exit(f"unknown model {a.model}; see `divide-reader models`")

    def prog(have, total):
        print(f"\r{have / 1e9:.2f} / {total / 1e9:.2f} GB", end="", flush=True)
    print(download.download(m, prog))


def login(session: auth.Session, pid: str) -> None:
    spec = get_spec(pid)
    if spec.login == "none":
        return
    if spec.login == "pkce":
        print(f"Opening your browser to log in to {spec.label}...")
        session.set(pid, auth.openrouter_login())
        return
    print(f"Opening your browser at {spec.key_url}\nCreate a key there and paste it here (it is kept in memory only).")
    auth.open_key_page(spec)
    session.set(pid, getpass.getpass(f"{spec.label} key: "))


def cmd_read(a) -> None:
    session = auth.Session()
    login(session, a.provider)
    model = a.model
    if a.provider == "local" and not model:
        sys.exit("give --model <file.gguf> (see `divide-reader models`)")
    conn = connect(a.provider, model, session)
    spec = jobs.JobSpec(input=a.input, input_kind=a.mode, unit_kind=a.unit, sample=None if a.sample == 0 else a.sample,
                        max_pages=a.max_pages, max_hops=a.max_hops, wayback_year=a.year, cost_cap=a.cap,
                        second_round_share=a.second, hypotheses=not a.no_hypotheses, report_lang=a.lang,
                        label=a.label)
    try:
        res = jobs.run(spec, conn.provider, project=jobs.project_dir(a.project),
                       progress=lambda st, i, n: print(f"\r{st} {i}/{n}", end="", flush=True))
    finally:
        conn.close()
    print(f"\nread {res.units_read} units. {res.stopped_reason}\n{res.report}")


def cmd_sources(a) -> None:
    store = jobs.open_store(jobs.project_dir(a.project))
    for r in store.q("""SELECT s.id, s.label, s.kind, COUNT(p.id) AS pages FROM source s
                        LEFT JOIN page p ON p.source_id = s.id AND p.status='ok' GROUP BY s.id"""):
        print(f"{r['id']:4} {r['kind']:5} {r['pages']:4} pages  {r['label']}")


def cmd_report(a) -> None:
    project = jobs.project_dir(a.project)
    store = jobs.open_store(project)
    if len(a.source) == 1:
        label = store.one("SELECT label FROM source WHERE id=?", (a.source[0],))["label"]
        print(report.write_source_report(store, a.source[0], report.default_out_dir(project, label), a.lang, a.unit))
    else:
        srcs = [(s, store.one("SELECT label FROM source WHERE id=?", (s,))["label"]) for s in a.source]
        print(report.write_comparison(store, srcs, report.default_out_dir(project, "compare"), a.lang, a.unit))


def cmd_check(a) -> None:
    store = jobs.open_store(jobs.project_dir(a.project))
    r = measures.manual_check(store, a.annotator)
    cov = "—" if r["coverage"] is None else f"{r['coverage'] * 100:.0f}%"
    exc = "—" if r["excess"] is None else f"{r['excess'] * 100:.0f}%"
    print(f"coverage {cov}  excess {exc}  units {r['n_units']}  missed: {r['missed_units']}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="divide-reader", description="Counts how many sides a text sorts its figures into.")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("--project", default="default")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("models", help="list models and direct download links").set_defaults(fn=cmd_models)
    d = sub.add_parser("download", help="download a local model")
    d.add_argument("model")
    d.set_defaults(fn=cmd_download)

    r = sub.add_parser("read", help="read a file or website and write a report")
    r.add_argument("input")
    r.add_argument("--provider", required=True, choices=[p.id for p in PROVIDERS])
    r.add_argument("--model")
    r.add_argument("--mode", default="auto", choices=["auto", "file", "page", "list", "wander", "wayback"])
    r.add_argument("--unit", default="sentence", choices=["sentence", "paragraph", "article", "chapter"])
    r.add_argument("--sample", type=int, default=200, help="units per source; 0 = all")
    r.add_argument("--max-pages", type=int, default=30)
    r.add_argument("--max-hops", type=int, default=3)
    r.add_argument("--year", type=int, help="Internet Archive year (wayback mode)")
    r.add_argument("--cap", type=float, help="cost cap in USD for this job")
    r.add_argument("--second", type=float, default=jobs.SECOND_ROUND_SHARE, help="share of units read twice")
    r.add_argument("--no-hypotheses", action="store_true")
    r.add_argument("--lang", default="en", choices=["en", "sr"])
    r.add_argument("--label")
    r.set_defaults(fn=cmd_read)

    sub.add_parser("sources", help="list sources in the project").set_defaults(fn=cmd_sources)
    rp = sub.add_parser("report", help="report for one source, or comparison of several")
    rp.add_argument("source", type=int, nargs="+")
    rp.add_argument("--lang", default="en", choices=["en", "sr"])
    rp.add_argument("--unit", default="sentence")
    rp.set_defaults(fn=cmd_report)
    c = sub.add_parser("check", help="compare with manual counts (coverage and excess)")
    c.add_argument("--annotator")
    c.set_defaults(fn=cmd_check)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
