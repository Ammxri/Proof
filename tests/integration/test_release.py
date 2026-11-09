"""Release package (PR-F10, PR-A02, PR-A06, PR-C01, PR-D04, UF-04, A-27, A-41).

Every test works on a copy of a small repository: a demo collection with a variant set, the licence files, the rule
documentation, card inputs and review records, committed with git.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from proof.cases import collection, release, review
from proof.cli import app
from proof.core import canonical, i18n, yamlio
from proof.report import card
from proof.variants import sets

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PACKS = ROOT / "tests" / "fixtures" / "packs"
TODAY = dt.date(2026, 11, 9)
COLLECTION = Path("data") / "collections" / "demo-10"
CONTACT = "Test Person, Test University (Germany), test@example.org"
runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    git = shutil.which("git")
    assert git is not None
    subprocess.run(  # noqa: S603 - fixed executable and arguments, no shell
        [git, "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.org", *args],
        check=True,
        capture_output=True,
    )


def _filled(lang: str, manifest: collection.CollectionManifest, packs: Path, **changes) -> dict:
    data = yamlio.load_text(review.record_template(lang, manifest, packs))
    entry = data["reviews"][0]
    entry.update(
        name=f"Dr. Test {lang}",
        clinical_practice="Test clinic",
        clinical_practice_country="CN" if lang == "zh" else "DE",
        date="2026-11-01",
        scope="Templates, labels and the sample of demo-10",
    )
    entry.update(changes)
    return data


@pytest.fixture(scope="module")
def base(tmp_path_factory) -> tuple[Path, Path]:
    """A committed repository with the demo collection, valid reviews and filled card inputs; and its packs."""
    top = tmp_path_factory.mktemp("release")
    packs = top / "packs"
    shutil.copytree(FIXTURE_PACKS, packs)
    repo = top / "repo"
    directory = repo / COLLECTION
    collection.write(collection.build("demo", 10, 1, name="demo-10", root=packs), directory)
    sets.write(sets.build(directory, 3, root=packs), sets.default_directory(directory, 3))
    for name in ("LICENSE", "LICENSE-DATA", "NOTICE"):
        shutil.copy(ROOT / name, repo / name)
    (repo / "docs").mkdir()
    shutil.copy(ROOT / "docs" / "regeln.md", repo / "docs" / "regeln.md")
    (repo / "data" / "card.yaml").write_text(
        yamlio.dump_text({"contact": CONTACT, "synthehr_data_licence": "Clarified for the test."}), encoding="utf-8"
    )
    manifest = review.read_manifest(directory)
    (repo / "review").mkdir()
    for lang in i18n.LANGUAGES:
        (repo / "review" / f"{lang}.yaml").write_text(
            yamlio.dump_text(_filled(lang, manifest, packs)), encoding="utf-8"
        )
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "test repository")
    return repo, packs


@pytest.fixture
def repo(base, tmp_path) -> Path:
    target = tmp_path / "repo"
    shutil.copytree(base[0], target)
    return target


@pytest.fixture
def packs(base) -> Path:
    return base[1]


def _prepare(repo: Path, packs: Path, **options) -> release.Prepared:
    return release.prepare(repo / COLLECTION, repo=repo, root=packs, today=TODAY, **options)


def _problems(repo: Path, packs: Path, **options) -> str:
    with pytest.raises(release.ReleaseError) as caught:
        _prepare(repo, packs, **options)
    return "\n".join(caught.value.problems)


def _commit(repo: Path) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")


def _record(repo: Path, lang: str, packs: Path, **changes) -> None:
    manifest = review.read_manifest(repo / COLLECTION)
    (repo / "review" / f"{lang}.yaml").write_text(
        yamlio.dump_text(_filled(lang, manifest, packs, **changes)), encoding="utf-8"
    )
    _commit(repo)


# --- A release -------------------------------------------------------------------------------------------------------


def test_a_release_with_valid_reviews_is_complete(repo, packs, tmp_path):
    """UF-04: cases, variants, renderings, rules, card and review records with complete SHA256SUMS."""
    prepared = _prepare(repo, packs, version="0.1.0")
    assert prepared.problems == ()
    target = release.write(prepared, tmp_path / "out")
    assert target.name == "proof-demo-10-0.1.0"
    files = sorted(path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file())
    for expected in (
        "README.md",
        "LICENSE",
        "LICENSE-CODE",
        "NOTICE",
        "SHA256SUMS",
        "release.json",
        "data/cases.jsonl",
        "data/collection.json",
        "data/variants/3/variants.jsonl",
        "data/variants/3/variants.json",
        "data/prompts/system_zh.txt",
        "schema/case.schema.json",
        "schema/variant.schema.json",
        "schema/response.schema.json",
        "rules/RULES.md",
        "rules/demo/pack.yaml",
        "rules/labx/pack.yaml",
        *(f"data/renderings/{lang}.jsonl" for lang in i18n.LANGUAGES),
        *(f"review/{lang}.yaml" for lang in i18n.LANGUAGES),
    ):
        assert expected in files
    listed = [line.split("  ", 1)[1] for line in (target / "SHA256SUMS").read_text("utf-8").splitlines()]
    assert listed == sorted(set(files) - {"SHA256SUMS"})
    assert release.check_package(target, draft=False) == []
    assert (target / "LICENSE").read_bytes() == (ROOT / "LICENSE-DATA").read_bytes()
    assert (target / "LICENSE-CODE").read_bytes() == (ROOT / "LICENSE").read_bytes()
    text = (target / "README.md").read_text("utf-8")
    assert card.missing_parts(text, draft=False) == []
    assert "(DRAFT)" not in text
    for lang in i18n.LANGUAGES:
        assert f"- Dr. Test {lang}, physician, Test clinic" in text
    assert CONTACT in text
    manifest = json.loads((target / "release.json").read_text("utf-8"))
    assert manifest["draft"] is False and manifest["problems"] == []
    assert manifest["cases_review_required"] is False
    assert all(state["valid"] for state in manifest["reviews"].values())


def test_the_renderings_hold_every_case_and_variant_with_text(repo, packs, tmp_path):
    """A-46: the texts exist only in the package; MR5 has no text of its own (A-37)."""
    target = release.write(_prepare(repo, packs), tmp_path / "out")
    variants = canonical.loads_lines((repo / COLLECTION / "variants" / "3" / "variants.jsonl").read_bytes())
    with_text = [variant for variant in variants if variant["mr"] != "MR5"]
    for lang in i18n.LANGUAGES:
        records = canonical.loads_lines((target / "data" / "renderings" / f"{lang}.jsonl").read_bytes())
        assert len(records) == 10 + len(with_text)
        assert {record["lang"] for record in records} == {lang}
        assert records[0]["item_id"] == "DEM-000001" and records[0]["mr"] is None
        assert all(record["text"].strip() for record in records)


# --- Refusals --------------------------------------------------------------------------------------------------------


def test_a_missing_review_record_stops_the_release(repo, packs):
    (repo / "review" / "en.yaml").unlink()
    _commit(repo)
    assert "no review record for en (PR-A02)" in _problems(repo, packs)


def test_an_unfilled_review_record_stops_the_release(repo, packs):
    manifest = review.read_manifest(repo / COLLECTION)
    (repo / "review" / "de.yaml").write_text(review.record_template("de", manifest, packs), encoding="utf-8")
    _commit(repo)
    assert "placeholder not filled in" in _problems(repo, packs)


def test_a_pre_review_alone_stops_the_release(repo, packs):
    _record(repo, "en", packs, role="pre_reviewer")
    assert "only pre-reviews" in _problems(repo, packs)


def test_zh_needs_a_physician_with_practice_in_china(repo, packs):
    _record(repo, "zh", packs, clinical_practice_country="DE")
    assert "zh needs a physician with clinical practice in China" in _problems(repo, packs)


def test_changed_zh_templates_stop_the_release(repo, packs):
    """PR-A06: the zh review must cover the current templates."""
    manifest = review.read_manifest(repo / COLLECTION)
    data = _filled("zh", manifest, packs)
    data["reviews"][0]["templates"]["templates/zh/case.j2"] = "0" * 64
    (repo / "review" / "zh.yaml").write_text(yamlio.dump_text(data), encoding="utf-8")
    _commit(repo)
    assert "templates/zh/case.j2 changed since the review (PR-A06)" in _problems(repo, packs)


def test_a_review_dated_in_the_future_stops_the_release(repo, packs):
    _record(repo, "de", packs, date="2027-01-01")
    assert "lies in the future" in _problems(repo, packs)


def test_from_version_0_5_the_case_sample_must_be_reviewed(repo, packs):
    """PR-A02: templates for 0.1, the sample of cases from 0.5."""
    manifest = review.read_manifest(repo / COLLECTION)
    data = _filled("en", manifest, packs)
    for key in ("collection", "collection_sha256", "cases"):
        data["reviews"][0].pop(key)
    (repo / "review" / "en.yaml").write_text(yamlio.dump_text(data), encoding="utf-8")
    _commit(repo)
    assert _prepare(repo, packs, version="0.1.0").problems == ()
    assert "no physician review of collection demo-10" in _problems(repo, packs, version="0.5.0")
    assert release.cases_required("1.0.0") and not release.cases_required("0.1.0.dev0")
    with pytest.raises(release.ReleaseError, match="cannot read the version"):
        release.cases_required("dev")


def test_a_placeholder_in_the_card_inputs_stops_the_release(repo, packs):
    (repo / "data" / "card.yaml").write_text(
        yamlio.dump_text({"contact": CONTACT, "synthehr_data_licence": "<PLATZHALTER: offen>"}), encoding="utf-8"
    )
    _commit(repo)
    assert "placeholder not filled in" in _problems(repo, packs)


def test_uncommitted_changes_stop_the_release(repo, packs):
    notice = repo / "NOTICE"
    notice.write_bytes(notice.read_bytes() + b"\n")
    assert "uncommitted changes" in _problems(repo, packs)


def test_a_release_needs_a_git_work_tree(repo, packs):
    shutil.rmtree(repo / ".git", onexc=lambda function, path, _: (os.chmod(path, stat.S_IWRITE), function(path)))
    assert "not a git work tree" in _problems(repo, packs)


def test_invalid_data_or_missing_files_stop_even_a_draft(repo, packs):
    cases = repo / COLLECTION / "cases.jsonl"
    original = cases.read_bytes()
    cases.write_bytes(original + b"{}" + b"\n")
    assert _problems(repo, packs, draft=True)
    cases.write_bytes(original)
    variants = repo / COLLECTION / "variants" / "3" / "variants.jsonl"
    lines = variants.read_bytes().splitlines(keepends=True)
    variants.write_bytes(b"".join(lines[1:]))
    assert "variants_sha256 does not match" in _problems(repo, packs, draft=True)
    variants.write_bytes(b"".join(lines))
    (repo / "LICENSE-DATA").unlink()
    assert "LICENSE-DATA: file is missing (packaged as LICENSE)" in _problems(repo, packs, draft=True)
    shutil.copy(ROOT / "LICENSE-DATA", repo / "LICENSE-DATA")
    (repo / "data" / "card.yaml").unlink()
    assert "card.yaml: file is missing" in _problems(repo, packs, draft=True)
    (repo / COLLECTION / "collection.json").unlink()
    assert "collection.json: file is missing" in _problems(repo, packs, draft=True)


def test_an_empty_collection_stops_the_release(repo, packs):
    empty = repo / "data" / "collections" / "empty"
    empty.mkdir()
    (empty / "cases.jsonl").write_bytes(b"")
    problems = "\n".join(_problems_for(empty, repo, packs))
    assert "cases.jsonl: no cases" in problems and "collection.json: file is missing" in problems


def _problems_for(directory: Path, repo: Path, packs: Path) -> tuple[str, ...]:
    with pytest.raises(release.ReleaseError) as caught:
        release.prepare(directory, repo=repo, root=packs, today=TODAY, draft=True)
    return caught.value.problems


def test_a_collection_without_variant_sets_is_released_without_them(repo, packs, tmp_path):
    shutil.rmtree(repo / COLLECTION / "variants")
    _commit(repo)
    target = release.write(_prepare(repo, packs), tmp_path / "out")
    metadata = card.front_matter((target / "README.md").read_text("utf-8"))
    assert metadata is not None
    assert "variants" not in [config["config_name"] for config in metadata["configs"]]
    assert not (target / "data" / "variants").exists()


def test_unreadable_review_records_are_shown_as_not_valid(repo, packs):
    (repo / "review" / "en.yaml").write_text("language: [\n", encoding="utf-8")
    (repo / "review" / "de.yaml").write_text("language: de\nreviews: []\n", encoding="utf-8")
    prepared = _prepare(repo, packs, draft=True)
    for lang in ("en", "de"):
        status = prepared.reviews[lang]
        assert not status.ok and status.reviews == () and status.placeholders == 0
    text = release.card_text(prepared)
    assert "### en\n\n- Not valid: " in text and "### de\n\n- Not valid: " in text


# --- Draft -----------------------------------------------------------------------------------------------------------


def test_a_draft_package_is_marked_and_complete(repo, packs, tmp_path):
    """A-41: without valid reviews only a draft: directory name and card are marked, findings are recorded."""
    manifest = review.read_manifest(repo / COLLECTION)
    for lang in i18n.LANGUAGES:
        (repo / "review" / f"{lang}.yaml").write_text(review.record_template(lang, manifest, packs), encoding="utf-8")
    assert "placeholder not filled in" in _problems(repo, packs)
    prepared = _prepare(repo, packs, draft=True, version="0.1.0")
    assert any("uncommitted changes" in problem for problem in prepared.problems)
    target = release.write(prepared, tmp_path / "out")
    assert target.name == "proof-demo-10-0.1.0-DRAFT"
    text = (target / "README.md").read_text("utf-8")
    assert "# Proof demo-10 (DRAFT)" in text
    for lang in i18n.LANGUAGES:
        assert i18n.text("release.draft", lang) in text
    assert release.check_package(target, draft=True) == []
    data = json.loads((target / "release.json").read_text("utf-8"))
    assert data["draft"] is True
    assert data["problems"] == list(prepared.problems)
    assert not any(state["valid"] for state in data["reviews"].values())
    assert any("placeholder" in problem for problem in release.check_package(target, draft=False))


def test_the_package_check_finds_every_change(repo, packs, tmp_path):
    target = release.write(_prepare(repo, packs), tmp_path / "out")
    (target / "data" / "cases.jsonl").write_bytes(b"changed\n")
    (target / "extra.txt").write_bytes(b"extra\n")
    (target / "NOTICE").unlink()
    problems = release.check_package(target, draft=False)
    assert "SHA256SUMS: data/cases.jsonl does not match its hash" in problems
    assert "SHA256SUMS: extra.txt is not listed" in problems
    assert "SHA256SUMS: NOTICE is listed but missing" in problems
    sums = target / "SHA256SUMS"
    sums.write_bytes(sums.read_bytes() + b"not a line\n" + sums.read_bytes().splitlines(keepends=True)[0])
    problems = release.check_package(target, draft=False)
    assert any("not '<sha256>  <path>'" in problem for problem in problems)
    assert any("is listed twice" in problem for problem in problems)
    (target / "README.md").unlink()
    assert any("README.md: file is missing" in problem for problem in release.check_package(target, draft=False))
    sums.unlink()
    assert release.check_package(target, draft=False) == [f"{sums}: file is missing"]


def test_an_existing_package_is_never_overwritten(repo, packs, tmp_path):
    prepared = _prepare(repo, packs)
    release.write(prepared, tmp_path / "out")
    with pytest.raises(release.ReleaseError, match="already exists"):
        release.write(prepared, tmp_path / "out")


def test_a_failed_package_check_leaves_nothing_behind(repo, packs, tmp_path, monkeypatch):
    prepared = _prepare(repo, packs)
    out = tmp_path / "out"
    staging = out / f".{release.package_name('demo-10', prepared.version, draft=False)}.partial"
    staging.mkdir(parents=True)
    (staging / "old.txt").write_bytes(b"left over\n")
    monkeypatch.setattr(release.card, "missing_parts", lambda text, draft: ["the card lacks something"])
    with pytest.raises(release.ReleaseError, match="the card lacks something"):
        release.write(prepared, out)
    assert list(out.iterdir()) == []


# --- Commands --------------------------------------------------------------------------------------------------------


def test_card_and_release_commands(repo, packs, tmp_path, monkeypatch):
    monkeypatch.chdir(repo)
    result = runner.invoke(app, ["card", "--set", str(COLLECTION), "--packs", str(packs)])
    assert result.exit_code == 0, result.output
    assert result.output.startswith("---\n") and "## Physician review" in result.output
    out = tmp_path / "card.md"
    result = runner.invoke(app, ["card", "--set", str(COLLECTION), "--packs", str(packs), "--out", str(out)])
    assert result.exit_code == 0 and out.read_text("utf-8").startswith("---\n")
    result = runner.invoke(
        app, ["release", "--set", str(COLLECTION), "--packs", str(packs), "--out", str(tmp_path / "rel")]
    )
    assert result.exit_code == 0, result.output
    assert (tmp_path / "rel").is_dir() and "-> " in result.output
    result = runner.invoke(
        app, ["release", "--set", str(COLLECTION), "--packs", str(packs), "--out", str(tmp_path / "rel")]
    )
    assert result.exit_code == 1 and "already exists" in result.output
    (repo / "review" / "en.yaml").unlink()
    result = runner.invoke(app, ["release", "--set", str(COLLECTION), "--packs", str(packs)])
    assert result.exit_code == 1 and "no review record for en" in result.output
    result = runner.invoke(app, ["card", "--set", str(COLLECTION), "--packs", str(packs)])
    assert result.exit_code == 1
    monkeypatch.setenv("PROOF_HOME", str(tmp_path / "home"))
    result = runner.invoke(app, ["release", "--set", str(COLLECTION), "--packs", str(packs), "--draft"])
    assert result.exit_code == 0, result.output
    assert "DRAFT, not a release and not meant for upload" in result.output
    package = next(iter((tmp_path / "home" / "releases").iterdir()))
    assert str(tmp_path) not in (package / "release.json").read_text("utf-8"), "no local path in the package"
    assert "draft: " in result.output
    assert next(iter((tmp_path / "home" / "releases").iterdir())).name.endswith("-DRAFT")
