"""English (default) and Serbian Latin strings for the GUI and the report."""
from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    # report
    "report_title": {"en": "Divide Reader report", "sr": "Divide Reader raport"},
    "sec_walked": {"en": "1. What was read", "sr": "1. Šta je obiđeno"},
    "sec_measures": {"en": "2. Measures", "sr": "2. Mjere"},
    "sec_hypotheses": {"en": "3. Hypotheses about the text", "sr": "3. Pretpostavke o tekstu"},
    "sec_units": {"en": "4. Readings by unit", "sr": "4. Čitanja po jedinicama"},
    "sec_other": {"en": "5. Other counts", "sr": "5. Druga brojanja"},
    "source": {"en": "Source (speaker)", "sr": "Izvor (govornik)"},
    "pages": {"en": "Pages", "sr": "Stranice"},
    "units": {"en": "Units", "sr": "Jedinice"},
    "unit_kind": {"en": "Unit", "sr": "Jedinica"},
    "models": {"en": "Models", "sr": "Modeli"},
    "rules": {"en": "Rules version", "sr": "Verzija pravila"},
    "skipped": {"en": "Skipped pages", "sr": "Preskočene stranice"},
    "measure": {"en": "Measure", "sr": "Mjera"},
    "simple": {"en": "Simple", "sr": "Prosta"},
    "weighted": {"en": "Weighted", "sr": "Težena"},
    "sample": {"en": "Sample", "sr": "Uzorak"},
    "stability": {"en": "Stability (Jaccard, two rounds)", "sr": "Stabilnost (Jaccard, dva kruga)"},
    "locked_two": {"en": "Locked twos", "sr": "Zaključane dvojke"},
    "open_two": {"en": "Open twos", "sr": "Otvorene dvojke"},
    "honest_two": {"en": "Honest twos", "sr": "Poštene dvojke"},
    "s_distribution": {"en": "Distribution of S", "sr": "Raspodjela S"},
    "range": {"en": "Range per unit (max S − min S)", "sr": "Raspon po jedinici (najveći S − najmanji S)"},
    "readings_per_unit": {"en": "Readings per unit (mean / max)", "sr": "Čitanja po jedinici (prosjek / najviše)"},
    "max_s": {"en": "Highest S (heard by ≥3 of 5)", "sr": "Najviši S (čuje ≥3 od 5)"},
    "figures": {"en": "Figures", "sr": "Figure"},
    "readings_found": {"en": "Readings ({n} found of {b} possible)", "sr": "Čitanja ({n} nađeno od {b} mogućih)"},
    "readings_found_open": {"en": "Readings ({n} found; completeness not guaranteed for F ≥ 6)",
                            "sr": "Čitanja ({n} nađeno; potpunost nije zajamčena za F ≥ 6)"},
    "heard": {"en": "heard by {k} of {n}", "sr": "čulo {k} od {n}"},
    "assumption": {"en": "assumption", "sr": "pretpostavka"},
    "anchor": {"en": "anchor", "sr": "oslonac"},
    "assumed_figures": {"en": "assumed figures", "sr": "pretpostavljene figure"},
    "more_readings": {"en": "Other readings ({n})", "sr": "Ostala čitanja ({n})"},
    "rejected": {"en": "Rejected partitions ({n})", "sr": "Odbačene particije ({n})"},
    "supports": {"en": "Supported by", "sr": "Podupiru"},
    "against": {"en": "Contradicted by", "sr": "Protivrječe"},
    "none": {"en": "None.", "sr": "Nema."},
    "unit": {"en": "Unit", "sr": "Jedinica"},
    "compare_title": {"en": "Comparison", "sr": "Poređenje"},
    "difference": {"en": "Difference", "sr": "Razlika"},
    "noise": {"en": "Noise (difference between two rounds of the same source)",
              "sr": "Šum (razlika između dva kruga istog izvora)"},
    "finding": {"en": "finding", "sr": "nalaz"},
    "within_noise": {"en": "within noise", "sr": "u okviru šuma"},
    "units_link": {"en": "units", "sr": "jedinice"},
    "unknown_cost": {"en": "Calls with unknown cost", "sr": "Pozivi nepoznate cijene"},
}


class T:
    def __init__(self, lang: str = "en"):
        self.lang = lang if lang in ("en", "sr") else "en"

    def __call__(self, key: str, **kw) -> str:
        entry = STRINGS.get(key)
        s = entry.get(self.lang, entry["en"]) if entry else key
        return s.format(**kw) if kw else s
