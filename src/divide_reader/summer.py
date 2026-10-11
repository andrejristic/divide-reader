"""Hypotheses about a whole text, each with units that support and contradict it."""
from __future__ import annotations

import time

from . import measures, prompts
from .reader import Budget
from .providers.base import Provider
from .store import Store, dumps

MAX_UNITS = 300

TASK = """Below are units from ONE source (one speaker), each with its explicit figures and the numbers of sides (S) that listeners heard.
Write up to 6 hypotheses about how this text sorts figures into sides (for example: "when the topic is X, figures are sorted into two camps").
For each hypothesis list unit ids that SUPPORT it and unit ids that CONTRADICT it. Use only ids that appear below. A hypothesis without contradicting units must still be checked: search for them.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array", "maxItems": 6,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "maxLength": 400},
                    "support": {"type": "array", "maxItems": 30, "items": {"type": "integer"}},
                    "against": {"type": "array", "maxItems": 30, "items": {"type": "integer"}},
                },
                "required": ["text", "support", "against"],
            },
        },
    },
    "required": ["hypotheses"],
}


def write_hypotheses(store: Store, provider: Provider, budget: Budget, source_id: int, unit_ids: list[int],
                     report_lang: str = "en") -> int:
    lines = []
    valid = set()
    for uid in unit_ids[:MAX_UNITS]:
        r = measures.load_unit(store, uid)
        if r is None or r.F < 2:
            continue
        valid.add(uid)
        lines.append(f"[{uid}] {r.text}\n    figures: {', '.join(r.figures)}; S heard: {sorted(r.s_values)}")
    if not lines:
        return 0
    budget.check()
    system = prompts.CORE + "\n" + TASK + "\n" + prompts.lang_line(report_lang)
    res = provider.chat_json(system, "\n".join(lines), SCHEMA, "hypotheses", max_tokens=4000)
    budget.add(res.model, res.usage.cost_usd)
    store.db.execute("DELETE FROM hypothesis WHERE source_id=?", (source_id,))
    for h in res.data["hypotheses"]:
        store.insert("hypothesis", source_id=source_id, text=h["text"],
                     support=dumps([u for u in h["support"] if u in valid]),
                     against=dumps([u for u in h["against"] if u in valid]),
                     model=res.model, created=time.time())
    store.commit()
    return len(res.data["hypotheses"])
