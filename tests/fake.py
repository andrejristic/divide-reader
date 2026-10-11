"""A deterministic stand-in for a model, for tests."""
import json
import re

from divide_reader.providers.base import ModelSpec, Provider, ProviderSpec, Result, Usage

VOCAB = ["sindikat", "vlada", "poslodavci", "radnika", "ja", "website", "the union", "the government",
         "employers", "workers", "ana", "marko", "petar", "jovan", "milan", "nikola", "zoran"]


class FakeProvider(Provider):
    def __init__(self, supported_s=(2,), price=None, fail_figures_once=False):
        self.spec = ProviderSpec("fake", "Fake", "free", "openai", "", "none")
        self.model = ModelSpec("fake-1", "Fake", *(price or (None, None)), free=price is None)
        self.supported_s = set(supported_s)
        self.calls = []

    def _call(self, system, user, schema, name, max_tokens):
        self.calls.append(name)
        unit = user.split("UNIT:\n", 1)[-1].split("\n\n", 1)[0].lower()
        if name == "figures":
            figs = [w for w in VOCAB if re.search(rf"\b{re.escape(w)}\b", unit)]
            data = {"figures": figs}
        elif name == "judgements":
            parts = re.findall(r"^(\d+): (.+)$", user.split("Partitions:\n", 1)[1], re.M)
            figs = re.findall(r"^f\d+: ", user, re.M)
            data = {"judgements": [], "assumed_readings": [], "other_counts": []}
            for pid, desc in parts:
                s = desc.count("|") + 1
                ok = s in self.supported_s or ("no surrounding text" in system and s == len(figs))
                data["judgements"].append({"id": int(pid), "supported": ok, "assumption": "a" if ok else "",
                                           "anchor": "x" if ok else "", "reason": "" if ok else "no"})
            if "opet" in unit and "neutral observer" in system:
                data["other_counts"].append({"what": "time", "amount": 1, "anchor": "opet"})
        elif name == "readings":
            figs = re.findall(r"^(f\d+): ", user, re.M)
            data = {"readings": [{"sides": [figs[:-1], figs[-1:]], "assumed_figures": [], "assumption": "a",
                                  "anchor": "x"}], "other_counts": []}
        elif name == "hypotheses":
            ids = [int(i) for i in re.findall(r"^\[(\d+)\]", user, re.M)]
            data = {"hypotheses": [{"text": "two camps", "support": ids[:2], "against": ids[2:3] + [99999]}]}
        else:
            raise AssertionError(name)
        usage = Usage(100, 50)
        if self.model.price_in is not None:
            usage.cost_usd = 0.01
        return Result(data=data, usage=usage, model="fake:fake-1", raw=json.dumps(data))
