"""Physician review: sample, packet and check of the record (PR-A02, PR-A06, PR-F05, A-23, A-71)."""

from __future__ import annotations

import datetime as dt
from collections import Counter
from pathlib import Path

import pytest
from typer.testing import CliRunner

from proof.cases import review
from proof.cli import app
from proof.core import yamlio
from proof.core.i18n import LANGUAGES
from proof.render import templating

FEVER_100 = Path(__file__).resolve().parents[2] / "data" / "collections" / "fever-100"
REVIEW_DIR = Path(__file__).resolve().parents[2] / "review"
runner = CliRunner()


@pytest.fixture(scope="module")
def manifest():
    return review.read_manifest(FEVER_100)


def _filled(lang: str, manifest, **changes) -> dict:
    """The record template of ``lang`` with every placeholder filled in."""
    data = yamlio.load_text(review.record_template(lang, manifest))
    entry = data["reviews"][0]
    entry.update(
        name="Dr. Test",
        clinical_practice="Test clinic",
        clinical_practice_country="CN" if lang == "zh" else "DE",
        date="2026-11-01",
        scope="Templates and sample of fever-100",
    )
    entry.update(changes)
    return data


def _write(tmp_path: Path, data: dict, name: str = "record.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yamlio.dump_text(data), encoding="utf-8")
    return path


def _verify(path: Path, lang: str, **options) -> list[str]:
    return review.verify(path, lang, today=dt.date(2026, 11, 9), **options).problems


# --- Sample ----------------------------------------------------------------------------------------------------------


def test_sample_size_is_at_least_ten_percent():
    assert [review.sample_size(n) for n in (1, 5, 10, 11, 100, 101, 500)] == [1, 1, 1, 2, 10, 11, 50]


def test_the_sample_is_deterministic_and_covers_every_target(manifest):
    """PR-A02: deterministic, at least 10 %; A-71: one case per target first."""
    targets = {entry.case_id: (entry.target.ddx, entry.target.red_flag) for entry in manifest.cases}
    samples = {lang: review.sample(manifest, lang) for lang in LANGUAGES}
    for lang, chosen in samples.items():
        assert len(chosen) == 10 and len(set(chosen)) == 10
        assert list(chosen) == sorted(chosen)
        assert chosen == review.sample(manifest, lang)
        assert len(Counter(targets[case_id] for case_id in chosen)) == 7
    assert len({samples[lang] for lang in LANGUAGES}) == 3, "each language checks its own sample"
    with pytest.raises(templating.TemplateError):
        review.sample(manifest, "fr")


def test_placeholders_are_found_everywhere():
    data = {"a": "<PLATZHALTER: x>", "b": [{"c": "ok"}, {"d": "y <PLATZHALTER> z"}], "e": 1}
    assert review.placeholders(data) == ["a: <PLATZHALTER: x>", "b[1].d: <PLATZHALTER>"]
    assert review.placeholders("<PLATZHALTER>") == ["<root>: <PLATZHALTER>"]


# --- Shipped records -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGUAGES)
def test_shipped_records_are_placeholders_with_current_hashes(manifest, lang):
    """Until a review is delivered the records are placeholders; their hashes and sample stay current."""
    path = REVIEW_DIR / f"{lang}.yaml"
    assert path.read_text(encoding="utf-8") == review.record_template(lang, manifest)
    problems = _verify(path, lang, collection_dir=FEVER_100)
    assert problems and all("placeholder not filled in" in problem for problem in problems)


# --- Verification ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGUAGES)
def test_a_complete_physician_review_is_accepted(tmp_path, manifest, lang):
    path = _write(tmp_path, _filled(lang, manifest))
    assert _verify(path, lang) == []
    assert _verify(path, lang, collection_dir=FEVER_100) == []
    report = review.verify(path, lang, today=dt.date(2026, 11, 9))
    assert (report.ok, report.physicians, report.pre_reviewers) == (True, 1, 0)


def test_a_missing_record_is_rejected(tmp_path):
    assert "no review record for de" in _verify(tmp_path / "de.yaml", "de")[0]


def test_a_pre_review_alone_is_rejected(tmp_path, manifest):
    data = _filled("de", manifest, role="pre_reviewer")
    problems = _verify(_write(tmp_path, data), "de")
    assert problems == [f"{tmp_path / 'record.yaml'}: only pre-reviews; a pre-review does not replace the "
                        "physician review (PR-A02)"]  # fmt: skip
    data["reviews"].append(_filled("de", manifest)["reviews"][0])
    report = review.verify(_write(tmp_path, data), "de", today=dt.date(2026, 11, 9))
    assert (report.ok, report.physicians, report.pre_reviewers) == (True, 1, 1)


def test_zh_needs_clinical_practice_in_china(tmp_path, manifest):
    path = _write(tmp_path, _filled("zh", manifest, clinical_practice_country="DE"))
    assert "zh needs a physician with clinical practice in China" in "\n".join(_verify(path, "zh"))


def test_changed_templates_invalidate_the_review(tmp_path, manifest):
    """PR-A06: a review covers exactly the reviewed templates and labels."""
    data = _filled("zh", manifest)
    templates = data["reviews"][0]["templates"]
    templates["templates/zh/case.j2"] = "0" * 64
    del templates["labels/fever/zh"]
    templates["templates/zh/old.j2"] = "1" * 64
    text = "\n".join(_verify(_write(tmp_path, data), "zh"))
    assert "templates/zh/case.j2 changed since the review" in text
    assert "labels/fever/zh is not covered" in text
    assert "templates/zh/old.j2 no longer exists" in text


def test_the_sample_must_be_reviewed_for_a_collection(tmp_path, manifest):
    data = _filled("de", manifest)
    data["reviews"][0]["cases"] = data["reviews"][0]["cases"][:-2]
    text = "\n".join(_verify(_write(tmp_path, data), "de", collection_dir=FEVER_100))
    assert "sample cases not reviewed:" in text
    data = _filled("de", manifest, collection_sha256="0" * 64)
    text = "\n".join(_verify(_write(tmp_path, data), "de", collection_dir=FEVER_100))
    assert "no physician review of collection fever-100 in its current form" in text


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"date": "2027-01-01"}, "lies in the future"),
        ({"role": "doctor"}, "Input should be 'physician' or 'pre_reviewer'"),
        ({"clinical_practice_country": "Germany"}, "String should match pattern"),
        ({"collection": None}, "collection and collection_sha256 go together"),
        ({"collection": None, "collection_sha256": None}, "reviewed cases need the collection"),
        ({"templates": {}}, "at least 1 item"),
    ],
)
def test_invalid_records_are_rejected(tmp_path, manifest, changes, message):
    path = _write(tmp_path, _filled("de", manifest, **changes))
    assert message in "\n".join(_verify(path, "de"))


def test_language_and_yaml_errors(tmp_path, manifest):
    path = _write(tmp_path, _filled("de", manifest))
    assert "the record is for de, not en" in "\n".join(_verify(path, "en"))
    path.write_text("language: [", encoding="utf-8")
    assert _verify(path, "de")


# --- Packet ----------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGUAGES)
def test_the_packet_holds_prompt_sample_templates_and_record(tmp_path, manifest, lang):
    written = review.packet(lang, FEVER_100, tmp_path)
    names = sorted(path.relative_to(tmp_path).as_posix() for path in written)
    assert names == sorted(
        [
            f"packet_{lang}.md",
            f"review_{lang}.yaml",
            f"labels_fever_{lang}.json",
            *(f"templates/{lang}/{name}" for name in templating.TEMPLATE_FILES),
        ]
    )
    document = (tmp_path / f"packet_{lang}.md").read_text(encoding="utf-8")
    for case_id in review.sample(manifest, lang):
        assert f"### {case_id}" in document
    assert "ddx.sepsis" in document and "rf.qsofa_ge2" in document
    for digest in review.current_hashes(lang).values():
        assert digest in document
    record = (tmp_path / f"review_{lang}.yaml").read_text(encoding="utf-8")
    assert record == review.record_template(lang, manifest)
    for name in templating.TEMPLATE_FILES:
        assert (tmp_path / "templates" / lang / name).read_bytes() == templating.template_bytes(lang, name)


def test_packets_need_a_collection(tmp_path):
    with pytest.raises(review.ReviewError, match=r"collection\.json: file is missing"):
        review.packet("de", tmp_path, tmp_path / "out")
    (tmp_path / "collection.json").write_text("{}", encoding="utf-8")
    with pytest.raises(review.ReviewError, match="Field required"):
        review.read_manifest(tmp_path)


# --- Command line ----------------------------------------------------------------------------------------------------


def test_review_commands(tmp_path, manifest, monkeypatch):
    result = runner.invoke(app, ["review", "sample", "--lang", "zh", "--collection", str(FEVER_100)])
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[0] == "fever-100, zh: 10 of 100 cases"
    assert result.output.splitlines()[1:] == list(review.sample(manifest, "zh"))
    out = tmp_path / "packet"
    result = runner.invoke(app, ["review", "packet", "--lang", "en", "--collection", str(FEVER_100), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert (out / "packet_en.md").is_file()
    monkeypatch.setenv("PROOF_HOME", str(tmp_path / "home"))
    result = runner.invoke(app, ["review", "packet", "--lang", "de", "--collection", str(FEVER_100)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "home/review/fever-100/de/packet_de.md").is_file()
    valid = _write(tmp_path, _filled("de", manifest))
    result = runner.invoke(app, ["review", "verify", "--lang", "de", "--record", str(valid)])
    assert result.exit_code == 0, result.output
    assert "valid; 1 physician review(s), 0 pre-review(s)" in result.output
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["review", "verify", "--lang", "de", "--collection", str(FEVER_100)])
    assert result.exit_code == 1
    assert "no review record for de" in result.output
    result = runner.invoke(app, ["review", "sample", "--lang", "fr", "--collection", str(FEVER_100)])
    assert result.exit_code == 1 and "--lang: expected one of zh, en, de" in result.output
    result = runner.invoke(app, ["review", "sample", "--lang", "de", "--collection", str(tmp_path)])
    assert result.exit_code == 1 and "collection.json: file is missing" in result.output
    result = runner.invoke(app, ["review", "packet", "--lang", "de", "--collection", str(tmp_path)])
    assert result.exit_code == 1


def test_dump_text_round_trips_with_a_comment():
    data = {"language": "zh", "list": ["a", "是"], "flag": "yes", "nested": {"n": 1}}
    text = yamlio.dump_text(data, comment="line one\n\nline three")
    assert text.startswith("# line one\n#\n# line three\n")
    assert yamlio.load_text(text) == data
    assert yamlio.dump_text({"a": 1}) == "a: 1\n"
