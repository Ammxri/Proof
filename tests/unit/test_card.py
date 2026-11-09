"""Dataset card (PR-F10, PR-A01, PR-A02, PR-C01, PR-D03, A-24, A-27)."""

from __future__ import annotations

from pathlib import Path

import pytest

from proof.cases import release
from proof.core import disclaimer, i18n, yamlio
from proof.report import card

ROOT = Path(__file__).resolve().parents[2]
FEVER_100 = ROOT / "data" / "collections" / "fever-100"


@pytest.fixture(scope="module")
def fever_card() -> str:
    """The draft card of the committed Fever-100 with the shipped records and card inputs."""
    return release.card_text(release.prepare(FEVER_100, repo=ROOT, draft=True))


def test_the_card_states_the_reference_sentence_in_every_language(fever_card):
    """PR-A01: the sentence stands in every card, in zh, en and de; A-24: with the category notice."""
    for lang in i18n.LANGUAGES:
        assert i18n.text("disclaimer.reference", lang) in fever_card
        assert i18n.text("disclaimer.category", lang) in fever_card


def test_the_card_has_every_required_part(fever_card):
    """PR-F10: provenance, rules, physician review, limitations, licence; Hugging Face metadata (A-27)."""
    assert card.missing_parts(fever_card, draft=True) == []
    headings = [line[3:] for line in fever_card.splitlines() if line.startswith("## ")]
    assert headings == list(card.SECTIONS)
    metadata = card.front_matter(fever_card)
    assert metadata is not None
    assert metadata["license"] == "cc-by-4.0"
    assert metadata["language"] == ["zh", "en", "de"]
    assert metadata["size_categories"] == ["n<1K"]
    assert [config["config_name"] for config in metadata["configs"]] == [
        "cases",
        "variants",
        "renderings_zh",
        "renderings_en",
        "renderings_de",
    ]


def test_the_card_tells_what_the_files_and_rules_say(fever_card):
    """Provenance (D-03 discarded rows, A-35), rule status (D-04), licences (PR-C01), qSOFA limit (D-04)."""
    assert "seeds 1–100" in fever_card
    assert "| `lab.crp_mg_l` | mg/L | 2199 | 879 | 296 | 331 | 0 | 693 | 808 |" in fever_card
    assert "generation parameters" in fever_card
    assert "28 active rules" in fever_card
    assert "has not been reviewed by a physician" in fever_card
    assert "CC BY 4.0" in fever_card and "Apache License 2.0" in fever_card
    assert "states no licence for the generated data" in fever_card
    assert "Surviving Sepsis Campaign 2021" in fever_card
    assert "| `vital.sbp` | 70–180 | ≥ 101 |" in fever_card
    assert "| `hx.onset_days` | 0–20 | ≤ 4 |" in fever_card


def test_the_draft_card_shows_missing_reviews_and_placeholders(fever_card):
    """Unfilled review records and card inputs stay visible as such (A-41)."""
    assert "# Proof fever-100 (DRAFT)" in fever_card
    for lang in i18n.LANGUAGES:
        assert i18n.text("release.draft", lang) in fever_card
        assert f"- Not reviewed yet: `{lang}.yaml` still has 5 placeholders." in fever_card
    assert "<PLATZHALTER: Datenlizenz der SynthEHR-Ausgabe" in fever_card
    assert "Ammar Ahad, Hochschule Trier (Germany)" in fever_card


def test_missing_parts_finds_every_gap(fever_card):
    assert card.missing_parts(fever_card, draft=False) == ["a release card must not carry the draft notice"]
    without_front = fever_card[fever_card.index("# Proof") :]
    assert "the card has no Hugging Face front matter" in card.missing_parts(without_front, draft=True)
    listed_front = "---\n- a\n---\n" + without_front
    assert "the card has no Hugging Face front matter" in card.missing_parts(listed_front, draft=True)
    unclosed = "---\nlicense: x\n" + without_front
    assert "the card has no Hugging Face front matter" in card.missing_parts(unclosed, draft=True)
    broken_front = "---\nlicense: [\n---\n" + without_front
    assert any(problem.startswith("front matter:") for problem in card.missing_parts(broken_front, draft=True))
    reduced = fever_card.replace("\nlicense: cc-by-4.0", "")
    assert "front matter lacks license" in card.missing_parts(reduced, draft=True)
    for lang in i18n.LANGUAGES:
        sentence = disclaimer.lines(lang)[1]
        problems = card.missing_parts(fever_card.replace(sentence, ""), draft=True)
        assert f"the card lacks the notice in {lang}: {sentence}" in problems
    for section in card.SECTIONS:
        problems = card.missing_parts(fever_card.replace(f"## {section}\n", "## Other\n"), draft=True)
        assert f"the card lacks the section {section!r}" in problems
    unmarked = fever_card.replace(i18n.text("release.draft", "zh"), "")
    assert "a draft card must be marked as draft in zh, en and de" in card.missing_parts(unmarked, draft=True)


def test_size_categories():
    assert [card.size_category(n) for n in (1, 999, 1_000, 9_999, 10_000, 500_000, 2_000_000)] == [
        "n<1K",
        "n<1K",
        "1K<n<10K",
        "1K<n<10K",
        "10K<n<100K",
        "100K<n<1M",
        "n>1M",
    ]


def test_card_inputs_are_checked(tmp_path):
    path = tmp_path / "card.yaml"
    with pytest.raises(card.CardError, match="file is missing"):
        card.read_inputs(path)
    path.write_text("contact: x\n", encoding="utf-8")
    with pytest.raises(card.CardError, match="synthehr_data_licence"):
        card.read_inputs(path)
    path.write_text("contact: x\nsynthehr_data_licence: y\nextra: z\n", encoding="utf-8")
    with pytest.raises(card.CardError, match="extra"):
        card.read_inputs(path)
    path.write_text("contact: [\n", encoding="utf-8")
    with pytest.raises(card.CardError):
        card.read_inputs(path)
    path.write_text(yamlio.dump_text({"contact": "x", "synthehr_data_licence": "<PLATZHALTER: offen>"}), "utf-8")
    inputs, found = card.read_inputs(path)
    assert inputs.contact == "x"
    assert found == [f"{path}: synthehr_data_licence: <PLATZHALTER: offen>"]


def test_the_shipped_card_inputs_hold_only_the_open_licence_question():
    """The contact is filled in; the SynthEHR data licence stays open until it is clarified (D-03, RK-03)."""
    inputs, found = card.read_inputs(ROOT / "data" / "card.yaml")
    assert inputs.contact == "Ammar Ahad, Hochschule Trier (Germany), Ammar_ahad@outlook.com"
    assert len(found) == 1 and "synthehr_data_licence" in found[0]
