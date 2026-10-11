"""Set partitions of a sentence's figures, with a canonical key per partition.

A partition of F figures is stored as a restricted growth string (RGS): one
side index per figure, where figure 0 is always on side 0 and every new side
takes the next free index. "0,0,0,1" means {f0, f1, f2} | {f3}. The same
grouping always gets the same key, so readings from different listeners,
rounds, models and manual counts compare directly.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Iterator, Sequence


@lru_cache(maxsize=None)
def bell(n: int) -> int:
    """Number of partitions of an n-element set."""
    if n < 0:
        raise ValueError("n must be >= 0")
    row = [1]
    for _ in range(n):
        nxt = [row[-1]]
        for v in row:
            nxt.append(nxt[-1] + v)
        row = nxt
    return row[0]


def enumerate_rgs(n: int) -> Iterator[tuple[int, ...]]:
    """Yield every partition of n figures as an RGS tuple, in lexicographic order."""
    if n == 0:
        yield ()
        return
    rgs = [0] * n

    def rec(i: int, mx: int) -> Iterator[tuple[int, ...]]:
        if i == n:
            yield tuple(rgs)
            return
        for v in range(mx + 2):
            rgs[i] = v
            yield from rec(i + 1, max(mx, v))

    rgs[0] = 0
    yield from rec(1, 0)


def key(rgs: Sequence[int]) -> str:
    return ",".join(str(v) for v in rgs)


def parse_key(k: str) -> tuple[int, ...]:
    return tuple(int(v) for v in k.split(",")) if k else ()


def sides(rgs: Sequence[int]) -> int:
    """S for this partition."""
    return max(rgs) + 1 if rgs else 0


def normalize(rgs: Sequence[int]) -> tuple[int, ...]:
    """Relabel arbitrary side labels into canonical RGS form."""
    mapping: dict[int, int] = {}
    out = []
    for v in rgs:
        if v not in mapping:
            mapping[v] = len(mapping)
        out.append(mapping[v])
    return tuple(out)


def from_groups(groups: Sequence[Sequence[int]], n: int) -> tuple[int, ...]:
    """Build an RGS from a list of figure-index groups.

    Raises ValueError unless every figure 0..n-1 appears in exactly one group.
    """
    label = [-1] * n
    for g_i, group in enumerate(groups):
        for f in group:
            if not 0 <= f < n:
                raise ValueError(f"figure index {f} out of range 0..{n - 1}")
            if label[f] != -1:
                raise ValueError(f"figure {f} is in more than one side")
            label[f] = g_i
    missing = [i for i, v in enumerate(label) if v == -1]
    if missing:
        raise ValueError(f"figures {missing} are in no side")
    return normalize(label)


def to_groups(rgs: Sequence[int]) -> list[list[int]]:
    groups: list[list[int]] = [[] for _ in range(sides(rgs))]
    for f, s in enumerate(rgs):
        groups[s].append(f)
    return groups


def describe(rgs: Sequence[int], names: Sequence[str]) -> str:
    """Human form: {a, b} | {c}."""
    return " | ".join("{" + ", ".join(names[f] for f in g) + "}" for g in to_groups(rgs))


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)
