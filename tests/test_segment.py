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
    text = "Prvi pasus ovdje. Druga rečenica.\n\nDrugi pasus. Još jedna."
    units = segment.split_units(text, "sentence")
    assert [u.text for u in units] == ["Prvi pasus ovdje.", "Druga rečenica.", "Drugi pasus.", "Još jedna."]
    assert "Prvi pasus ovdje." in units[1].ctx_before
    assert "Drugi pasus" in units[1].ctx_after
    assert len(segment.split_units(text, "paragraph")) == 2
    assert len(segment.split_units(text, "article")) == 1


def test_chapters():
    text = "Poglavlje 1\n\nTekst jedan.\n\nPoglavlje 2\n\nTekst dva."
    assert len(segment.split_units(text, "chapter")) == 2
