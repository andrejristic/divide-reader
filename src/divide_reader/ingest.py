"""Turn files and fetched documents into pages and units in the store."""
from __future__ import annotations

import hashlib
import io
import posixpath
import re
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

import trafilatura

from . import segment
from .store import Store

MIN_CHARS = 200


@dataclass
class Doc:
    title: str
    text: str
    html: bytes | None = None
    url: str | None = None


def sha(text: str) -> str:
    norm = re.sub(r"\s+", " ", text).strip().casefold()
    return hashlib.sha256(norm.encode()).hexdigest()


def html_to_doc(html: bytes | str, url: str | None = None) -> Doc | None:
    raw = html if isinstance(html, str) else html.decode("utf-8", "replace")
    text = trafilatura.extract(raw, url=url, include_comments=False, include_tables=False,
                               favor_precision=True)
    if not text:
        return None
    meta = trafilatura.extract_metadata(raw)
    title = (meta.title if meta and meta.title else "") or ""
    return Doc(title=title, text=text, html=html if isinstance(html, bytes) else html.encode(), url=url)


def pdf_docs(data: bytes, name: str) -> list[Doc]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = [(p.extract_text() or "") for p in reader.pages]
    text = "\n".join(pages)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)          # join hyphenated line breaks
    text = re.sub(r"(?<![.!?:])\n(?!\n)", " ", text)       # unwrap lines inside paragraphs
    title = (reader.metadata.title if reader.metadata and reader.metadata.title else name)
    return [Doc(title=title, text=text)]


def epub_docs(data: bytes, name: str) -> list[Doc]:
    """One Doc per spine item (usually one per chapter)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    container = ET.fromstring(z.read("META-INF/container.xml"))
    opf_path = container.find(".//{*}rootfile").get("full-path")
    opf = ET.fromstring(z.read(opf_path))
    base = posixpath.dirname(opf_path)
    manifest = {i.get("id"): i.get("href") for i in opf.find("{*}manifest")}
    title_el = opf.find(".//{http://purl.org/dc/elements/1.1/}title")
    book_title = title_el.text if title_el is not None and title_el.text else name
    docs = []
    for ref in opf.find("{*}spine"):
        href = manifest.get(ref.get("idref"))
        if not href:
            continue
        path = posixpath.normpath(posixpath.join(base, href))
        try:
            html = z.read(path)
        except KeyError:
            continue
        d = html_to_doc(html)
        if d and len(d.text) >= 50:
            d.title = d.title or book_title
            docs.append(d)
    return docs


def docs_from_bytes(data: bytes, name: str, content_type: str = "") -> tuple[str, list[Doc]]:
    """Return (source kind, docs) for a file's bytes."""
    low = name.lower()
    if low.endswith(".pdf") or "pdf" in content_type:
        return "book", pdf_docs(data, name)
    if low.endswith(".epub") or "epub" in content_type:
        return "book", epub_docs(data, name)
    if low.endswith((".html", ".htm", ".xhtml")) or "html" in content_type:
        d = html_to_doc(data)
        return "page", [d] if d else []
    text = data.decode("utf-8", "replace")
    return "file", [Doc(title=Path(name).stem, text=text)]


def add_docs(store: Store, source_id: int, docs: list[Doc], snapshot: str = "file") -> list[int]:
    page_ids = []
    for d in docs:
        h = sha(d.text)
        if len(d.text) < MIN_CHARS:
            status = "skipped:too little text"
        elif store.has_page_hash(source_id, h):
            status = "skipped:duplicate"
        else:
            status = "ok"
        pid = store.insert("page", source_id=source_id, url=d.url, fetched_at=time.time(), snapshot=snapshot,
                           status=status, html=d.html, sha256=h, title=d.title,
                           text=d.text if status == "ok" else None,
                           lang=segment.detect_lang(d.text[:5000]) if status == "ok" else None)
        if status == "ok":
            page_ids.append(pid)
    store.commit()
    return page_ids


def make_units(store: Store, page_ids: list[int], kind: str = "sentence") -> list[int]:
    ids = []
    for pid in page_ids:
        page = store.one("SELECT text, lang FROM page WHERE id=?", (pid,))
        existing = store.q("SELECT id FROM unit WHERE page_id=? AND kind=? ORDER BY idx", (pid, kind))
        if existing:
            ids += [r["id"] for r in existing]
            continue
        for u in segment.split_units(page["text"], kind, page["lang"]):
            ids.append(store.insert("unit", page_id=pid, kind=u.kind, idx=u.idx, text=u.text,
                                    ctx_before=u.ctx_before, ctx_after=u.ctx_after, lang=u.lang))
    store.commit()
    return ids


def ingest_file(store: Store, path: str | Path, kind: str = "sentence") -> tuple[int, list[int]]:
    """Add a local file as one source (one speaker). Returns (source id, unit ids)."""
    path = Path(path)
    skind, docs = docs_from_bytes(path.read_bytes(), path.name)
    sid = store.add_source(path.name, skind, str(path), "file")
    pages = add_docs(store, sid, docs)
    return sid, make_units(store, pages, kind)
