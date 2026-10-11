import pytest

from divide_reader import partitions as P


@pytest.mark.parametrize("n,expected", [(0, 1), (1, 1), (2, 2), (3, 5), (4, 15), (5, 52), (6, 203)])
def test_bell_matches_enumeration(n, expected):
    assert P.bell(n) == expected
    all_rgs = list(P.enumerate_rgs(n))
    assert len(all_rgs) == expected
    assert len(set(all_rgs)) == expected


def test_enumeration_is_canonical():
    for rgs in P.enumerate_rgs(5):
        assert P.normalize(rgs) == rgs


def test_from_groups_and_back():
    rgs = P.from_groups([[3], [0, 1, 2]], 4)
    assert P.key(rgs) == "0,0,0,1"
    assert P.sides(rgs) == 2
    assert P.to_groups(rgs) == [[0, 1, 2], [3]]
    assert P.describe(rgs, ["a", "b", "c", "d"]) == "{a, b, c} | {d}"


@pytest.mark.parametrize("groups", [[[0, 1], [1, 2]], [[0], [1]], [[0, 1, 2, 5]]])
def test_from_groups_rejects_bad(groups):
    with pytest.raises(ValueError):
        P.from_groups(groups, 3)


def test_jaccard():
    assert P.jaccard({"0,1"}, {"0,1"}) == 1.0
    assert P.jaccard({"0,1"}, {"0,0"}) == 0.0
    assert P.jaccard(set(), set()) == 1.0
    assert P.jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)
