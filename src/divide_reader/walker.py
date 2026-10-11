"""The walker: fetches pages politely, in list mode or wander mode, live or from the Internet Archive."""
from __future__ import annotations

import random
import threading
import time
import urllib.parse
import urllib.robotparser
from collections import deque
from typing import Callable

import httpx

from . import __version__, ingest
from .store import Store

USER_AGENT = f"DivideReader/{__version__} (+https://github.com/andrejristic/divide-reader)"
DOWNLOADABLE = (".pdf", ".epub", ".txt")
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".mp4", ".mp3", ".zip", ".gz", ".css", ".js",
            ".ico", ".xml", ".json", ".woff", ".woff2")


class Fetcher:
    def __init__(self, delay: float = 3.0, timeout: float = 30.0):
        self.delay = delay
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True)
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.last: dict[str, float] = {}

    def allowed(self, url: str) -> bool:
        p = urllib.parse.urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        if host not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(host + "/robots.txt")
                if r.status_code in (401, 403):
                    rp = None  # robots.txt itself is forbidden: treat the site as closed
                elif r.status_code >= 400:
                    rp.parse([])
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp.parse([])
            self.robots[host] = rp
        rp = self.robots[host]
        return rp is not None and rp.can_fetch(USER_AGENT, url)

    def get(self, url: str, check_robots: bool = True) -> httpx.Response:
        host = urllib.parse.urlparse(url).netloc
        if check_robots and not self.allowed(url):
            raise PermissionError("blocked by robots.txt")
        wait = self.last.get(host, 0) + self.delay + random.random() - time.time()
        if wait > 0:
            time.sleep(wait)
        try:
            return self.client.get(url)
        finally:
            self.last[host] = time.time()


def _links(html: str, base: str) -> list[str]:
    from lxml import html as lh
    try:
        tree = lh.fromstring(html)
    except Exception:
        return []
    out = []
    for href in tree.xpath("//a/@href"):
        u = urllib.parse.urljoin(base, href.strip())
        u, _ = urllib.parse.urldefrag(u)
        if u.startswith(("http://", "https://")) and not u.lower().endswith(SKIP_EXT):
            out.append(u)
    return out


def _skip(store: Store, source_id: int, url: str, reason: str, snapshot: str) -> None:
    store.insert("page", source_id=source_id, url=url, fetched_at=time.time(), snapshot=snapshot,
                 status=f"skipped:{reason}")
    store.commit()


def fetch_one(store: Store, fetcher: Fetcher, source_id: int, url: str, snapshot: str = "live",
              check_robots: bool = True) -> tuple[list[int], str | None]:
    """Fetch a URL into pages. Returns (page ids, html for link extraction)."""
    try:
        r = fetcher.get(url, check_robots=check_robots)
    except PermissionError as e:
        _skip(store, source_id, url, str(e), snapshot)
        return [], None
    except httpx.HTTPError as e:
        _skip(store, source_id, url, f"network: {e}", snapshot)
        return [], None
    if r.status_code in (401, 403):
        _skip(store, source_id, url, f"login required or forbidden (HTTP {r.status_code})", snapshot)
        return [], None
    if r.status_code >= 400:
        _skip(store, source_id, url, f"HTTP {r.status_code}", snapshot)
        return [], None
    ctype = r.headers.get("content-type", "")
    path = urllib.parse.urlparse(str(r.url)).path
    if "html" in ctype:
        d = ingest.html_to_doc(r.content, str(r.url))
        docs = [d] if d else []
        html = r.text
    else:
        _, docs = ingest.docs_from_bytes(r.content, path.rsplit("/", 1)[-1] or "download", ctype)
        html = None
    for d in docs:
        d.url = d.url or url
    if not docs:
        _skip(store, source_id, url, "no main text", snapshot)
        return [], html
    return ingest.add_docs(store, source_id, docs, snapshot), html


def walk(store: Store, start: str, mode: str = "list", max_pages: int = 50, max_hops: int = 3,
         delay: float = 3.0, log: Callable[[str], None] = print, stop: threading.Event | None = None,
         label: str | None = None) -> int:
    """Walk from a start URL. list = stay on the domain (for measuring); wander = follow links out (for exploring)."""
    stop = stop or threading.Event()
    fetcher = Fetcher(delay)
    host = urllib.parse.urlparse(start).netloc
    lower = start.lower().split("?")[0]
    kind = "book" if lower.endswith((".pdf", ".epub")) else "site"
    sid = store.add_source(label or host, kind, start, mode)
    queue: deque[tuple[str, int]] = deque([(start, 0)])
    seen = {start}
    ok_pages = 0
    while queue and ok_pages < max_pages and not stop.is_set():
        url, hops = queue.popleft()
        pages, html = fetch_one(store, fetcher, sid, url)
        ok_pages += len(pages)
        log(f"[{ok_pages}/{max_pages}] {url} -> {len(pages)} page(s)")
        if html is None or hops >= max_hops:
            continue
        for link in _links(html, url):
            same = urllib.parse.urlparse(link).netloc == host
            if link in seen or (mode == "list" and not same):
                continue
            seen.add(link)
            queue.append((link, hops + 1))
        if mode == "wander":
            rest = list(queue)
            random.shuffle(rest)
            queue = deque(rest)
    return sid


# --- Internet Archive --------------------------------------------------------

CDX = "https://web.archive.org/cdx/search/cdx"


def wayback_snapshot(url: str, year: int, fetcher: Fetcher | None = None) -> str | None:
    """Timestamp of the capture closest to the middle of the given year, or None."""
    fetcher = fetcher or Fetcher(delay=1.0)
    r = fetcher.client.get(CDX, params={"url": url, "from": str(year), "to": str(year), "output": "json",
                                        "filter": "statuscode:200", "limit": "50", "fl": "timestamp"})
    if r.status_code != 200:
        return None
    rows = r.json()[1:] if r.text.strip() else []
    if not rows:
        return None
    target = f"{year}0701000000"
    return min((row[0] for row in rows), key=lambda ts: abs(int(ts) - int(target)))


def fetch_wayback(store: Store, url: str, year: int, label: str | None = None) -> tuple[int, list[int]]:
    """Fetch one archived page from a given year as its own source (one speaker, one period)."""
    fetcher = Fetcher(delay=2.0)
    ts = wayback_snapshot(url, year, fetcher)
    sid = store.add_source(label or f"{urllib.parse.urlparse(url).netloc} ({year})", "site", url, "wayback")
    if ts is None:
        _skip(store, sid, url, f"no archive capture in {year}", f"wayback:{year}")
        return sid, []
    # id_ returns the original HTML without the archive toolbar.
    archived = f"https://web.archive.org/web/{ts}id_/{url}"
    pages, _ = fetch_one(store, fetcher, sid, archived, snapshot=f"wayback:{ts}", check_robots=False)
    return sid, pages
