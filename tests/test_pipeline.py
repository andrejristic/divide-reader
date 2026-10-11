import json

import pytest

from divide_reader import ingest, jobs, measures, report
from divide_reader.providers.base import BudgetExceeded
from divide_reader.reader import Budget, Reader, free_reading_key, vote_figures
from divide_reader.store import Store

from fake import FakeProvider

TEXT = """Sindikat, vlada i poslodavci opet su se dogovorili preko leđa radnika. Ja sam napravio website.

Marko i Ana su otišli. Kiša pada cijeli dan bez prestanka, a niko ne zna zašto je tako ovih dana.

Petar, Jovan, Milan, Nikola, Zoran, Marko i Ana čekaju odluku koja dugo ne dolazi u ovaj mali grad."""


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "s.sqlite")
    yield s
    s.close()


def ingest_text(store, tmp_path, text=TEXT):
    p = tmp_path / "t.txt"
    p.write_text(text, encoding="utf-8")
    return ingest.ingest_file(store, p)


def test_vote_figures_majority_and_order():
    got = vote_figures([["vlada", "Sindikat"], ["sindikat", "radnici"], ["Vlada", "sindikat"]],
                       "Sindikat i vlada ...")
    assert [f for f, _ in got] == ["Sindikat", "vlada"] or [f for f, _ in got] == ["sindikat", "vlada"]
    assert all(v >= 2 for _, v in got)


def test_free_reading_key_with_assumed():
    rgs, assumed = free_reading_key([["f0"], ["website"], ["judge"]], ["ja", "website"])
    assert assumed == ["judge"]
    assert rgs == (0, 1, 2)
    with pytest.raises(ValueError):
        free_reading_key([["f0"]], ["ja", "website"])


def test_reader_end_to_end(store, tmp_path):
    sid, units = ingest_text(store, tmp_path)
    assert len(units) == 5
    fake = FakeProvider(supported_s=(2,))
    reader = Reader(store, fake, Budget(store, "j", None), seed=1)
    reader.read_units(units)
    res = {u: measures.load_unit(store, u) for u in units}
    first = res[units[0]]
    assert first.F == 4 and first.mode == "enumerate"
    assert first.n_passes == 5
    # every S=2 partition of 4 figures is supported by all five listeners (7 of them)
    assert sum(1 for r in first.readings.values() if r.s == 2) == 7
    # the "bare" listener also hears S = F
    assert 4 in first.s_values
    # rejected partitions are kept with a reason
    assert first.rejected and all(why for _, _, why in first.rejected)
    # a sentence with no vocabulary figures is trivial: S=0, no model call
    rain = res[units[3]]
    assert rain.F == 0 and rain.mode == "trivial" and rain.s_values == {0}
    # F >= 6 uses proposals
    big = res[units[4]]
    assert big.F == 7 and big.mode == "propose"
    # other counts recorded
    oc = measures.other_counts(store, units)
    assert "time" in oc
    # figure calls: 3 per unit with figures attempt (all units call figures)
    assert fake.calls.count("figures") == 3 * 5


def test_measures_and_report(store, tmp_path):
    sid, units = ingest_text(store, tmp_path)
    reader = Reader(store, FakeProvider(supported_s=(2,)), Budget(store, "j", None), seed=1)
    reader.read_units(units)
    reader.read_unit(units[0], new_round=True)
    results = [measures.load_unit(store, u) for u in units]
    m = measures.compute(results)
    assert m["units"] == 5
    assert m["open_two"]["simple"] is not None
    stab = measures.stability(store, units)
    assert stab["n"] == 1 and 0 <= stab["mean"] <= 1
    out = report.write_source_report(store, sid, tmp_path / "rep", "sr")
    html = out.read_text(encoding="utf-8")
    assert "Sindikat" in html and "Mjere" in html
    assert (tmp_path / "rep" / "measures.csv").exists()


def test_manual_check(store, tmp_path):
    sid, units = ingest_text(store, tmp_path)
    Reader(store, FakeProvider(supported_s=(2,)), Budget(store, "j", None), seed=1).read_units(units[:1])
    store.insert("manual", unit_id=units[0], annotator="andrej", role="check", s_values=json.dumps([2, 3]),
                 created=0)
    store.commit()
    r = measures.manual_check(store)
    assert r["coverage"] == 0.5


def test_budget_stops(store, tmp_path):
    sid, units = ingest_text(store, tmp_path)
    reader = Reader(store, FakeProvider(price=(1.0, 1.0)), Budget(store, "j", 0.05), seed=1)
    with pytest.raises(BudgetExceeded):
        reader.read_units(units)
    assert store.total_spend("j") >= 0.05


def test_job_run(tmp_path, monkeypatch):
    p = tmp_path / "t.txt"
    p.write_text(TEXT, encoding="utf-8")
    spec = jobs.JobSpec(input=str(p), sample=None, second_round_share=0.5, report_lang="en")
    res = jobs.run(spec, FakeProvider(), project=tmp_path / "proj", log=lambda s: None)
    assert res.units_read == 5
    assert res.report.exists()
    html = res.report.read_text(encoding="utf-8")
    assert "two camps" in html


def test_estimate():
    e = jobs.estimate(200, price_in=1, price_out=5)
    assert e["calls"] > 1000 and e["cost_usd"] > 0
