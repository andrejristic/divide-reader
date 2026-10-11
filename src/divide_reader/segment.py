"""Split clean text into paragraphs, sentences, articles or chapters, with context."""
from __future__ import annotations

import re
from dataclasses import dataclass

import py3langid

CTX_CHARS = 1500

ABBREV = {
    # Serbian / Croatian / Bosnian
    "dr", "mr", "prof", "npr", "tj", "itd", "itsl", "sl", "god", "br", "str", "tzv", "gđa", "gđica", "g",
    "ul", "sv", "st", "op", "prim", "red", "prev", "v", "vs", "min", "maks", "mil", "mlrd", "tel", "čl",
    "ing", "dipl", "doc", "akad", "gosp",
    # English
    "mrs", "ms", "jr", "sr", "inc", "ltd", "co", "corp", "no", "vol", "fig", "e.g", "i.e", "etc", "approx",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "gen", "gov", "sen",
    "rep", "lt", "col", "capt", "mt", "ft",
}

_END = re.compile(r"([.!?…]+[\"'”“»«)\]]*)(\s+)")
_CHAPTER = re.compile(r"^\s*(chapter|poglavlje|glava|deo|dio|part|knjiga|book)\b.*$|^\s*[IVXLC]{1,6}\.?\s*$",
                      re.IGNORECASE)


@dataclass
class Unit:
    kind: str
    idx: int
    text: str
    ctx_before: str
    ctx_after: str
    lang: str | None = None


def paragraphs(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", text) if re.search(r"\n\s*\n", text) else text.split("\n")
    out = []
    for b in blocks:
        b = re.sub(r"\s*\n\s*", " ", b).strip()
        if b:
            out.append(b)
    return out


def sentences(par: str) -> list[str]:
    out, start = [], 0
    for m in _END.finditer(par):
        end = m.end(1)
        before = par[start:end]
        word = re.search(r"(\S+)$", before[: -len(m.group(1))] if m.group(1) else before)
        token = (word.group(1) if word else "").lower().rstrip(".")
        nxt = par[m.end():m.end() + 1]
        if m.group(1).startswith(".") and len(m.group(1)) == 1:
            if token in ABBREV or (len(token) == 1 and token.isalpha()):
                continue
            if token.isdigit() and (not nxt or not nxt.isupper()):
                continue  # Serbian ordinals and dates: "11. oktobar"
        if nxt and not (nxt.isupper() or nxt.isdigit() or nxt in "\"'„“”«»(—–-"):
            continue
        s = par[start:end].strip()
        if s:
            out.append(s)
        start = m.end()
    tail = par[start:].strip()
    if tail:
        out.append(tail)
    return out


def detect_lang(text: str) -> str | None:
    if len(text) < 20:
        return None
    lang, _ = py3langid.classify(text)
    return lang


def _clip_end(s: str) -> str:
    return s if len(s) <= CTX_CHARS else "…" + s[-CTX_CHARS:]


def _clip_start(s: str) -> str:
    return s if len(s) <= CTX_CHARS else s[:CTX_CHARS] + "…"


def split_units(text: str, kind: str = "sentence", page_lang: str | None = None) -> list[Unit]:
    pars = paragraphs(text)
    page_lang = page_lang or detect_lang(text[:5000])
    units: list[Unit] = []
    if kind == "sentence":
        for pi, par in enumerate(pars):
            sents = sentences(par)
            prev_par = pars[pi - 1] if pi > 0 else ""
            next_par = pars[pi + 1] if pi + 1 < len(pars) else ""
            for si, s in enumerate(sents):
                before = " ".join(filter(None, [prev_par, " ".join(sents[:si])]))
                after = " ".join(filter(None, [" ".join(sents[si + 1:]), next_par]))
                lang = detect_lang(s) if len(s) >= 80 else page_lang
                units.append(Unit("sentence", len(units), s, _clip_end(before), _clip_start(after), lang))
    elif kind == "paragraph":
        for pi, par in enumerate(pars):
            units.append(Unit("paragraph", pi, par, _clip_end(pars[pi - 1]) if pi else "",
                              _clip_start(pars[pi + 1]) if pi + 1 < len(pars) else "", page_lang))
    elif kind == "article":
        units.append(Unit("article", 0, "\n\n".join(pars), "", "", page_lang))
    elif kind == "chapter":
        chapters: list[list[str]] = [[]]
        for par in pars:
            if _CHAPTER.match(par) and chapters[-1]:
                chapters.append([])
            chapters[-1].append(par)
        for ci, ch in enumerate(chapters):
            units.append(Unit("chapter", ci, "\n\n".join(ch), "", "", page_lang))
    else:
        raise ValueError(f"unknown unit kind {kind}")
    return units
