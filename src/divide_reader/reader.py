"""The reader: locks figures, then lets five listeners judge every partition."""
from __future__ import annotations

import random
import re
import threading
import time
import unicodedata
from collections import Counter
from typing import Callable

from . import partitions as P
from . import prompts
from .providers.base import BudgetExceeded, LLMError, Provider
from .store import Store, dumps

ENUMERATE_MAX_F = 5
FIGURE_ATTEMPTS = 3
FIGURE_MIN_VOTES = 2


class Budget:
    """Cost cap for one job. cap=None means no cap."""

    def __init__(self, store: Store, job: str, cap_usd: float | None):
        self.store = store
        self.job = job
        self.cap = cap_usd
        self.unknown_cost_calls = 0

    @property
    def spent(self) -> float:
        return self.store.total_spend(self.job)

    def check(self) -> None:
        if self.cap is not None and self.spent >= self.cap:
            raise BudgetExceeded(f"cost cap ${self.cap:.2f} reached (spent ${self.spent:.2f})")

    def add(self, model: str, cost: float | None) -> None:
        if cost is None:
            self.unknown_cost_calls += 1
            return
        self.store.insert("spend", job=self.job, model=model, cost_usd=cost, created=time.time())
        self.store.commit()


def _stem_key(s: str) -> str:
    return " ".join(w[:5] for w in _norm(s).split())


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).casefold().strip()
    return re.sub(r"[\W_]+", " ", s).strip()


class Reader:
    def __init__(self, store: Store, provider: Provider, budget: Budget, report_lang: str = "en",
                 log: Callable[[str], None] = print, stop: threading.Event | None = None,
                 seed: int | None = None):
        self.store = store
        self.provider = provider
        self.budget = budget
        self.report_lang = report_lang
        self.log = log
        self.stop = stop or threading.Event()
        self.rng = random.Random(seed)
        self._examples: str | None = None

    # --- helpers ---------------------------------------------------------
    def _call(self, system: str, user: str, schema: dict, name: str, max_tokens: int = 4000):
        if self.stop.is_set():
            raise InterruptedError("stopped")
        self.budget.check()
        res = self.provider.chat_json(system, user, schema, name, max_tokens=max_tokens)
        self.budget.add(res.model, res.usage.cost_usd)
        return res

    def examples(self) -> str:
        if self._examples is None:
            rows = self.store.q("""SELECT u.text, m.s_values, m.note FROM manual m JOIN unit u ON u.id = m.unit_id
                                   WHERE m.role = 'example' ORDER BY m.id LIMIT 40""")
            import json
            self._examples = prompts.examples_block(
                [{"text": r["text"], "s_values": json.loads(r["s_values"]), "note": r["note"]} for r in rows])
        return self._examples

    def _unit(self, unit_id: int):
        u = self.store.one("""SELECT u.*, p.title FROM unit u JOIN page p ON p.id = u.page_id WHERE u.id = ?""",
                           (unit_id,))
        if u is None:
            raise KeyError(f"no unit {unit_id}")
        return u

    # --- step 1: figures -------------------------------------------------
    def lock_figures(self, unit_id: int) -> list[str]:
        locked = self.store.locked_figures(unit_id)
        if locked is not None:
            return locked
        u = self._unit(unit_id)
        block = prompts.unit_block(u["text"], u["title"], u["ctx_before"], u["ctx_after"], with_context=True)
        system, user = prompts.figures_prompt(block)
        done = self.store.q("SELECT attempt, figures FROM figure_attempt WHERE unit_id=? ORDER BY attempt",
                            (unit_id,))
        import json
        attempts = [json.loads(r["figures"]) for r in done]
        for i in range(len(attempts), FIGURE_ATTEMPTS):
            res = self._call(system, user, prompts.FIGURES_SCHEMA, "figures", max_tokens=1000)
            figs = [f for f in res.data["figures"] if isinstance(f, str) and f.strip()]
            self.store.insert("figure_attempt", unit_id=unit_id, attempt=i, model=res.model,
                              figures=dumps(figs), created=time.time())
            self.store.commit()
            attempts.append(figs)
        figures = vote_figures(attempts, u["text"])
        self.store.lock_figures(unit_id, figures, self.provider.label)
        return [f for f, _ in figures]

    # --- step 2: listeners -----------------------------------------------
    def read_unit(self, unit_id: int, new_round: bool = False) -> int:
        """Run (or finish) a round of five listeners over a unit. Returns the round id."""
        figures = self.lock_figures(unit_id)
        F = len(figures)
        rnd = self.store.one("SELECT * FROM round WHERE unit_id=? ORDER BY round_no DESC LIMIT 1", (unit_id,))
        if rnd is not None and rnd["complete"] and not new_round:
            return rnd["id"]
        if rnd is None or (rnd["complete"] and new_round):
            mode = "trivial" if F <= 1 else ("enumerate" if F <= ENUMERATE_MAX_F else "propose")
            round_no = (rnd["round_no"] + 1) if rnd else 1
            rid = self.store.insert("round", unit_id=unit_id, round_no=round_no, model=self.provider.label,
                                    rules_version=prompts.RULES_VERSION, mode=mode, created=time.time())
            self.store.commit()
            rnd = self.store.one("SELECT * FROM round WHERE id=?", (rid,))
        rid, mode = rnd["id"], rnd["mode"]

        if mode == "trivial":
            pid = self.store.insert("pass", round_id=rid, listener="rule", model="rule", created=time.time())
            self.store.insert("reading", pass_id=pid, rkey=P.key((0,) * F), s=F, supported=1,
                              assumption="", anchor="", assumed="[]")
            self.store.db.execute("UPDATE round SET complete=1 WHERE id=?", (rid,))
            self.store.commit()
            return rid

        have = {r["listener"] for r in self.store.q("SELECT listener FROM pass WHERE round_id=?", (rid,))}
        u = self._unit(unit_id)
        for listener in prompts.LISTENER_ORDER:
            if listener in have:
                continue
            ctx = listener not in prompts.NO_CONTEXT_LISTENERS
            block = prompts.unit_block(u["text"], u["title"], u["ctx_before"], u["ctx_after"], with_context=ctx)
            if mode == "enumerate":
                self._enumerate_pass(rid, unit_id, listener, block, figures)
            else:
                self._propose_pass(rid, unit_id, listener, block, figures)
        self.store.db.execute("UPDATE round SET complete=1 WHERE id=?", (rid,))
        self.store.commit()
        return rid

    def _enumerate_pass(self, rid: int, unit_id: int, listener: str, block: str, figures: list[str]) -> None:
        F = len(figures)
        all_rgs = list(P.enumerate_rgs(F))
        self.rng.shuffle(all_rgs)  # different order for every listener
        id_map = {i + 1: rgs for i, rgs in enumerate(all_rgs)}
        shown = [(pid, P.describe(rgs, [f"f{i}" for i in range(F)])) for pid, rgs in id_map.items()]
        system, user = prompts.enumerate_prompt(listener, block, figures, shown, self.report_lang, self.examples())
        res = self._call(system, user, prompts.ENUMERATE_SCHEMA, "judgements", max_tokens=400 + 160 * len(all_rgs))
        pid = self._save_pass(rid, listener, res)
        judged: dict[int, dict] = {}
        for j in res.data["judgements"]:
            if j["id"] in id_map and j["id"] not in judged:
                judged[j["id"]] = j
        for p_id, rgs in id_map.items():
            j = judged.get(p_id)
            if j is None:
                self.store.insert("reading", pass_id=pid, rkey=P.key(rgs), s=P.sides(rgs), supported=0,
                                  reject_reason="not judged by model", assumed="[]")
                continue
            self.store.insert("reading", pass_id=pid, rkey=P.key(rgs), s=P.sides(rgs), supported=int(j["supported"]),
                              assumption=j["assumption"], anchor=j["anchor"],
                              reject_reason=None if j["supported"] else j["reason"], assumed="[]")
        for r in res.data["assumed_readings"]:
            self._save_free(pid, r, figures, require_assumed=True)
        self._save_other(unit_id, pid, res.data["other_counts"])
        self.store.commit()

    def _propose_pass(self, rid: int, unit_id: int, listener: str, block: str, figures: list[str]) -> None:
        system, user = prompts.propose_prompt(listener, block, figures, self.report_lang, self.examples())
        res = self._call(system, user, prompts.PROPOSE_SCHEMA, "readings", max_tokens=8000)
        pid = self._save_pass(rid, listener, res)
        for r in res.data["readings"]:
            self._save_free(pid, r, figures, require_assumed=False)
        self._save_other(unit_id, pid, res.data["other_counts"])
        self.store.commit()

    def _save_pass(self, rid: int, listener: str, res) -> int:
        return self.store.insert("pass", round_id=rid, listener=listener, model=res.model, raw=res.raw,
                                 in_tokens=res.usage.in_tokens, out_tokens=res.usage.out_tokens,
                                 cost_usd=res.usage.cost_usd, created=time.time())

    def _save_free(self, pid: int, r: dict, figures: list[str], require_assumed: bool) -> None:
        try:
            rgs, assumed = free_reading_key(r["sides"], figures)
        except ValueError as e:
            self.store.insert("reading", pass_id=pid, rkey="invalid", s=0, supported=0,
                              reject_reason=f"invalid proposal: {e}", assumed=dumps(r.get("assumed_figures", [])),
                              assumption=r.get("assumption"), anchor=r.get("anchor"))
            return
        if require_assumed and not assumed:
            # A plain partition proposed outside the list: already judged in the enumeration.
            return
        self.store.insert("reading", pass_id=pid, rkey=P.key(rgs), s=P.sides(rgs), supported=1,
                          assumption=r["assumption"], anchor=r["anchor"], assumed=dumps(assumed))

    def _save_other(self, unit_id: int, pid: int, items: list[dict]) -> None:
        for o in items:
            self.store.insert("other_count", unit_id=unit_id, pass_id=pid, what=o["what"],
                              amount=o.get("amount"), anchor=o.get("anchor"))

    # --- whole sources ---------------------------------------------------
    def read_units(self, unit_ids: list[int], progress: Callable[[int, int], None] | None = None) -> None:
        for i, uid in enumerate(unit_ids):
            if self.stop.is_set():
                break
            try:
                self.read_unit(uid)
            except LLMError as e:
                self.log(f"unit {uid}: {e}")
            if progress:
                progress(i + 1, len(unit_ids))


def vote_figures(attempts: list[list[str]], text: str) -> list[tuple[str, int]]:
    """Keep figures named in at least FIGURE_MIN_VOTES attempts, ordered by position in the text."""
    need = min(FIGURE_MIN_VOTES, len(attempts))
    votes: Counter[str] = Counter()
    forms: dict[str, Counter[str]] = {}
    for att in attempts:
        seen = set()
        for f in att:
            n = _stem_key(f)  # inflected forms of the same figure vote together
            if not n or n in seen:
                continue
            seen.add(n)
            votes[n] += 1
            forms.setdefault(n, Counter())[f.strip()] += 1
    low = _norm(text)
    stems = {w[:4] for w in low.split()}
    # A figure must come from the unit: at least one of its words (by stem) appears in it.
    kept = [n for n, v in votes.items() if v >= need and any(w[:4] in stems for w in n.split())]

    def pos(n: str) -> int:
        i = low.find(n.split()[0])
        return i if i >= 0 else len(low) + 1

    kept.sort(key=lambda n: (pos(n), n))
    return [(forms[n].most_common(1)[0][0], votes[n]) for n in kept]


def free_reading_key(sides: list[list[str]], figures: list[str]) -> tuple[tuple[int, ...], list[str]]:
    """Turn sides written as labels/names into a canonical key over explicit + assumed figures."""
    F = len(figures)
    by_name = {_norm(f): i for i, f in enumerate(figures)}
    resolved: list[list[int | str]] = []
    assumed: set[str] = set()
    for side in sides:
        out: list[int | str] = []
        for label in side:
            m = re.fullmatch(r"\s*[fF](\d+)\s*", label)
            if m and int(m.group(1)) < F:
                out.append(int(m.group(1)))
            elif _norm(label) in by_name:
                out.append(by_name[_norm(label)])
            elif _norm(label):
                assumed.add(_norm(label))
                out.append(_norm(label))
        if out:
            resolved.append(out)
    order = sorted(assumed)
    index = {name: F + i for i, name in enumerate(order)}
    groups = [[x if isinstance(x, int) else index[x] for x in side] for side in resolved]
    return P.from_groups(groups, F + len(order)), order
