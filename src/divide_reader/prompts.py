"""Instructions and JSON schemas for the reader.

Prompts are written in English (models follow English instructions best); the
text being read can be in any language. Free-text fields come back in the
report language.
"""
from __future__ import annotations

RULES_VERSION = "2026-10-11.1"

LISTENERS: dict[str, str] = {
    "neutral": ("You are a neutral observer. Read only what the text says, with as few "
                "assumptions as possible."),
    "close": ("You are a listener close to the speaker. Hear what the speaker most likely "
              "wants you to hear."),
    "averse": ("You are a listener averse to the speaker. Read suspiciously: look for what "
               "the speaker merges together or leaves unsaid."),
    "figure": ("You listen from the place of the figure in the sentence that suffers the "
               "action or has no voice in it."),
    "bare": ("You hear only this one sentence, with no surrounding text and no title. "
             "Do not guess at context you were not given."),
}
LISTENER_ORDER = list(LISTENERS)
NO_CONTEXT_LISTENERS = {"bare"}

CORE = """You help measure how many SIDES a text sorts its figures into.

Definitions:
- A FIGURE is a person, group or thing that does something or has something done to it in the unit. A person the author quotes is a figure, not a speaker.
- The SPEAKER is the whole source (the website or book), never a quoted person.
- A SIDE is a group into which the speaker sorts one or more figures.
- S is the number of sides after sorting. A READING is one way of sorting, with S, the assumption under which it holds (from where the speaker is speaking), and the anchor in the text (a short quote) that supports it.
- The speaker expects the listener to hear a certain number of sides; the listener may or may not hear it.
"""

FIGURES_TASK = """Task: list the EXPLICIT figures in the unit below.
- Only figures that stand in the UNIT itself (nouns, names, pronouns referring to agents or patients, things acted on). The text before and after is context only: never take figures from it.
- Do not add implied figures. Do not list the same figure twice under different words.
- Write each figure as a short phrase copied or minimally lemmatized from the text, in the text's language.
- Order them by first appearance.
"""

FIGURES_SCHEMA = {
    "type": "object",
    "properties": {
        "figures": {"type": "array", "maxItems": 24, "items": {"type": "string", "maxLength": 80}},
    },
    "required": ["figures"],
}

_S = {"type": "string", "maxLength": 200}

_OTHER = {
    "type": "array",
    "maxItems": 8,
    "items": {
        "type": "object",
        "properties": {
            "what": _S,
            "amount": {"type": ["number", "null"]},
            "anchor": _S,
        },
        "required": ["what", "amount", "anchor"],
    },
}

_FREE_READING = {
    "type": "object",
    "properties": {
        "sides": {"type": "array", "maxItems": 24,
                  "items": {"type": "array", "maxItems": 24, "items": {"type": "string", "maxLength": 80}}},
        "assumed_figures": {"type": "array", "maxItems": 6, "items": {"type": "string", "maxLength": 80}},
        "assumption": _S,
        "anchor": _S,
    },
    "required": ["sides", "assumed_figures", "assumption", "anchor"],
}

ENUMERATE_SCHEMA = {
    "type": "object",
    "properties": {
        "judgements": {
            "type": "array",
            "maxItems": 60,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "supported": {"type": "boolean"},
                    "assumption": _S,
                    "anchor": _S,
                    "reason": _S,
                },
                "required": ["id", "supported", "assumption", "anchor", "reason"],
            },
        },
        "assumed_readings": {"type": "array", "maxItems": 8, "items": _FREE_READING},
        "other_counts": _OTHER,
    },
    "required": ["judgements", "assumed_readings", "other_counts"],
}

PROPOSE_SCHEMA = {
    "type": "object",
    "properties": {
        "readings": {"type": "array", "maxItems": 30, "items": _FREE_READING},
        "other_counts": _OTHER,
    },
    "required": ["readings", "other_counts"],
}

ENUMERATE_TASK = """Task: below is EVERY possible way to sort the unit's explicit figures into sides. For EACH numbered partition decide whether the text supports it as a way the speaker sorts the figures, heard from your position as a listener.
- supported=true: give the assumption (from where the speaker speaks for this to hold) and the anchor (short quote from the unit).
- supported=false: give a reason of a few words; assumption and anchor are empty strings.
- Keep every text field short: one clause, anchors of a few words.
- Judge every id exactly once.
- assumed_readings: readings that need a figure NOT in the text (e.g. an implied judge of the result). Write sides as lists of figure labels (f0, f1, ...) and the new figure names; list the new names in assumed_figures. Leave empty if none.
- other_counts: anything else in the unit that can be counted but is not a count of sides (e.g. times, occasions), with what is counted, the amount (or null) and the anchor. Leave empty if none.
"""

PROPOSE_TASK = """Task: the unit has many figures. Propose every way of sorting them into sides that the text supports, heard from your position as a listener.
- Each reading: sides as lists of figure labels (f0, f1, ...); every explicit figure must be in exactly one side. If a reading needs a figure not in the text, add its name to a side and list it in assumed_figures.
- Give the assumption and the anchor (short quote) for each reading.
- other_counts: anything else in the unit that can be counted but is not a count of sides, with what is counted, the amount (or null) and the anchor.
"""


def lang_line(report_lang: str) -> str:
    name = {"en": "English", "sr": "Serbian (Latin script)"}.get(report_lang, "English")
    return f"Write assumption, reason and 'what' fields in {name}. Anchors are quotes in the text's own language."


def unit_block(text: str, title: str | None, before: str | None, after: str | None, with_context: bool) -> str:
    parts = []
    if with_context:
        if title:
            parts.append(f"Page title: {title}")
        if before:
            parts.append(f"Text before:\n{before}")
    parts.append(f"UNIT:\n{text}")
    if with_context and after:
        parts.append(f"Text after:\n{after}")
    return "\n\n".join(parts)


def examples_block(examples: list[dict]) -> str:
    """Worked examples from the manual sample (role=example)."""
    if not examples:
        return ""
    lines = ["Worked examples from a human counter (S values they hear):"]
    for ex in examples:
        lines.append(f"- \"{ex['text']}\" -> S in {sorted(ex['s_values'])}"
                     + (f" ({ex['note']})" if ex.get("note") else ""))
    return "\n".join(lines) + "\n"


def figures_prompt(unit: str) -> tuple[str, str]:
    return CORE + "\n" + FIGURES_TASK, unit


def enumerate_prompt(listener: str, unit: str, figures: list[str], partitions: list[tuple[int, str]],
                     report_lang: str, examples: str) -> tuple[str, str]:
    system = "\n".join([CORE, examples, f"Your position: {LISTENERS[listener]}", ENUMERATE_TASK,
                        lang_line(report_lang)])
    figs = "\n".join(f"f{i}: {f}" for i, f in enumerate(figures))
    parts = "\n".join(f"{pid}: {desc}" for pid, desc in partitions)
    user = f"{unit}\n\nExplicit figures:\n{figs}\n\nPartitions:\n{parts}"
    return system, user


def propose_prompt(listener: str, unit: str, figures: list[str], report_lang: str, examples: str) -> tuple[str, str]:
    system = "\n".join([CORE, examples, f"Your position: {LISTENERS[listener]}", PROPOSE_TASK,
                        lang_line(report_lang)])
    figs = "\n".join(f"f{i}: {f}" for i, f in enumerate(figures))
    return system, f"{unit}\n\nExplicit figures:\n{figs}"
