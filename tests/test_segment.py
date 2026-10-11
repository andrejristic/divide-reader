from divide_reader import segment


def test_sentences_serbian_abbrev_and_dates():
    par = ("Dr. Petrović je 11. oktobra 2026. godine rekao da npr. vlada laže. "
           "Sindikat se nije složio! Šta sad? „Ništa“, rekao je.")
    s = segment.sentences(par)
    assert s[0].startswith("Dr. Petrović") and s[0].endswith("vlada laže.")
    assert s[1] == "Sindikat se nije složio!"
    assert s[2] == "Šta sad?"
    assert len(s) == 4


def test_sentences_english():
    s = segment.sentences("Mr. Smith met the union. They agreed, e.g. on pay. Then they left.")
    assert s == ["Mr. Smith met the union.", "They agreed, e.g. on pay.", "Then they left."]


def test_units_with_context():
    text = "Prvi pasus je ovdje. Druga rečenica je ovo.\n\nDrugi pasus počinje ovako. Još jedna rečenica."
    units = segment.split_units(text, "sentence")
    assert [u.text for u in units] == ["Prvi pasus je ovdje.", "Druga rečenica je ovo.",
                                       "Drugi pasus počinje ovako.", "Još jedna rečenica."]
    assert "Prvi pasus je ovdje." in units[1].ctx_before
    assert "Drugi pasus" in units[1].ctx_after
    assert len(segment.split_units(text, "paragraph")) == 2
    assert len(segment.split_units(text, "article")) == 1


def test_chapters():
    text = "Poglavlje 1\n\nTekst jedan.\n\nPoglavlje 2\n\nTekst dva."
    assert len(segment.split_units(text, "chapter")) == 2


def test_footnotes_and_short_fragments_dropped():
    units = segment.split_units("Tesla je bio pronalazač[1][2]. Da.\n\n,\n\nOn je radio u Njujorku mnogo godina.", "sentence")
    assert [u.text for u in units] == ["Tesla je bio pronalazač.", "On je radio u Njujorku mnogo godina."]
