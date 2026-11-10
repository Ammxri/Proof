"""Variants MR1, MR3, MR5 and variant sets (PR-F06, PR-M00, PR-MR1, PR-MR3, PR-MR5, PR-D02, A-74, A-75, A-89).

MR2, MR4, MR6 and MR7 are tested in ``test_variant_relations.py``.
"""

from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from pathlib import Path

import jsonschema
import pytest
from typer.testing import CliRunner

from proof.cases import collection
from proof.cases.model import Case
from proof.cli import app
from proof.core import canonical
from proof.core.i18n import LANGUAGES
from proof.render.case_text import RenderError, render_case
from proof.variants import generator, sets
from proof.variants.model import (
    DEFAULT_ORDER,
    UNCHANGED,
    AbsoluteExpectation,
    InvariantExpectation,
    LanguagePair,
    PermuteSections,
    RemoveField,
    Variant,
    variant_json_schema,
)
from proof.variants.render import render_variant
from proof_rules import loader

ROOT = Path(__file__).resolve().parents[2]
FEVER_100 = ROOT / "data" / "collections" / "fever-100"
FEVER_VARIANTS = FEVER_100 / "variants" / "1"
runner = CliRunner()


@pytest.fixture(scope="module")
def fever():
    return loader.load_domain("fever")


@pytest.fixture(scope="module")
def cases() -> dict[str, Case]:
    data = (FEVER_100 / collection.CASES_FILE).read_bytes()
    return {case.case_id: case for case in (Case.model_validate(item) for item in canonical.loads_lines(data))}


@pytest.fixture(scope="module")
def committed() -> list[tuple[bytes, Variant]]:
    problems: list[str] = []
    parsed = sets.read_variants(FEVER_VARIANTS / sets.VARIANTS_FILE, problems)
    assert problems == []
    return parsed


@pytest.fixture
def demo_set(tmp_path, fixture_packs) -> tuple[Path, Path, Path]:
    """A demo collection of 10 cases with variant seed 3, in writable copies."""
    packs = tmp_path / "packs"
    shutil.copytree(fixture_packs, packs)
    directory = tmp_path / "demo-10"
    collection.write(collection.build("demo", 10, 1, name="demo-10", root=packs), directory)
    variants = sets.default_directory(directory, 3)
    sets.write(sets.build(directory, 3, root=packs), variants)
    return directory, variants, packs


# --- The committed set of Fever-100 ----------------------------------------------------------------------------------


def test_the_committed_set_is_valid():
    report = sets.validate(FEVER_VARIANTS)
    assert report.ok, "\n".join(report.problems)
    assert report.by_mr == {"MR1": 100, "MR3": 100, "MR5": 300}


def test_every_variant_passes_the_schema_and_carries_its_expectation(committed):
    """KONZEPT U6: each variant passes Pydantic (when read) and the JSON Schema, with a machine-readable expectation."""
    validator = jsonschema.Draft202012Validator(variant_json_schema())
    for line, variant in committed:
        validator.validate(json.loads(line))
        assert isinstance(variant.expectation, AbsoluteExpectation | InvariantExpectation)


def test_mr1_expects_what_the_engine_gives_on_the_variant(committed, cases):
    """PR-MR1: ask, unless another red flag stays visible; the removed field is among the questions."""
    seen = Counter()
    for _, variant in committed:
        if variant.mr != "MR1":
            continue
        base = cases[variant.case_id]
        assert isinstance(variant.change, RemoveField)
        field = variant.change.field
        assert field in base.key.critical_fields
        assert set(variant.facts) == set(base.facts) - {field}
        expectation = variant.expectation
        assert isinstance(expectation, AbsoluteExpectation)
        assert expectation.decision == variant.key.determinability
        expected = "refer_urgent" if variant.key.red_flags else "ask"
        assert expectation.decision == expected
        assert expectation.questions_include == (field,) == variant.key.required_questions
        seen[expectation.decision] += 1
    assert set(seen) == {"ask", "refer_urgent"}


def test_mr3_changes_only_the_order(committed, cases, fever):
    """PR-MR3: same facts and key; the text has the same lines, only the sections move."""
    for _, variant in committed:
        if variant.mr != "MR3":
            continue
        base = cases[variant.case_id]
        assert isinstance(variant.change, PermuteSections)
        assert variant.change.order != DEFAULT_ORDER
        assert variant.facts == base.facts
        assert variant.key.model_dump(exclude={"required_questions"}) == base.key.model_dump()
        assert variant.key.required_questions == ()
        assert variant.expectation == InvariantExpectation(kind="invariant", compare=UNCHANGED)
    for _, variant in [item for item in committed if item[1].mr == "MR3"][:15]:
        base = cases[variant.case_id]
        for lang in LANGUAGES:
            original = render_case(base, fever, lang).text
            permuted = render_variant(variant, base, fever, lang).text
            assert original != permuted
            strip = lambda text: sorted(re.sub(r"^### \d\. ", "### ", line) for line in text.splitlines())  # noqa: E731
            assert strip(original) == strip(permuted)


def test_mr5_pairs_the_three_languages(committed, cases):
    """PR-MR5, A-37: three pairs per base case, compared without a request of their own."""
    pairs = Counter()
    for _, variant in committed:
        if variant.mr != "MR5":
            continue
        assert isinstance(variant.change, LanguagePair)
        assert variant.facts == cases[variant.case_id].facts
        assert variant.expectation == InvariantExpectation(kind="invariant", compare=UNCHANGED)
        pairs[variant.case_id] += 1
        assert variant.variant_id.endswith("-".join(variant.change.langs))
    assert len(pairs) == 100 and set(pairs.values()) == {3}
    variant = next(variant for _, variant in committed if variant.mr == "MR5")
    with pytest.raises(RenderError, match="MR5 compares the base case in two languages"):
        render_variant(variant, cases[variant.case_id], loader.load_domain("fever"), "de")


def test_same_seed_same_variants_new_seed_new_variants(committed):
    """PR-D02: the committed set is rebuilt byte for byte; another seed draws other fields and orders.

    The committed set is the one of v0.1 with MR1, MR3 and MR5 (A-89); it is rebuilt with these relations.
    """
    rebuilt = sets.build(FEVER_100, 1, mrs=("MR1", "MR3", "MR5"))
    assert rebuilt.data == b"".join(line + b"\n" for line, _ in committed)
    other = sets.build(FEVER_100, 2, mrs=("MR1", "MR3", "MR5"))
    assert other.data != rebuilt.data
    changes = {variant.variant_id: variant.change for variant in rebuilt.variants if variant.mr != "MR5"}
    differing = sum(variant.change != changes[variant.variant_id] for variant in other.variants if variant.mr != "MR5")
    assert differing > 100, "a new seed changes most MR1 and MR3 choices"


def test_the_manifest_records_the_set(committed):
    manifest = sets.VariantSetManifest.model_validate_json((FEVER_VARIANTS / sets.MANIFEST_FILE).read_bytes())
    assert (manifest.collection, manifest.variant_seed, manifest.per_case) == ("fever-100", 1, 1)
    assert manifest.mrs == ("MR1", "MR3", "MR5")
    assert manifest.summary.variants == {"MR1": 100, "MR3": 100, "MR5": 300}
    assert manifest.summary.units_per_language == 300
    assert sum(manifest.summary.mr1_decisions.values()) == 100
    assert [entry.variant_id for entry in manifest.variants] == [variant.variant_id for _, variant in committed]
    assert manifest.git is None or not manifest.git.dirty, "build the variant set from a committed tree"


# --- Generator options -----------------------------------------------------------------------------------------------


def test_several_variants_per_case_draw_without_repetition(cases, fever):
    chosen = list(cases.values())[:5]
    generated = generator.generate(chosen, fever, 7, per_case=3, mrs=("MR1", "MR3"))
    for case in chosen:
        mine = [variant for variant in generated.variants if variant.case_id == case.case_id]
        fields = [variant.change.field for variant in mine if isinstance(variant.change, RemoveField)]
        orders = [variant.change.order for variant in mine if isinstance(variant.change, PermuteSections)]
        assert len(fields) == min(3, len(case.key.critical_fields)) and len(set(fields)) == len(fields)
        assert len(orders) == 3 and len(set(orders)) == 3
    many = generator.generate(chosen[:1], fever, 7, per_case=30, mrs=("MR1", "MR3"))
    assert many.missing["MR3"] == 30 - 23
    assert many.missing["MR1"] == 30 - len(chosen[0].key.critical_fields)
    assert len(generator.PERMUTED_ORDERS) == 23


@pytest.mark.parametrize(
    ("seed", "per_case", "mrs", "message"),
    [
        (-1, 1, ("MR1",), "variant seed must not be negative"),
        (1, 0, ("MR1",), "per_case must be at least 1"),
        (1, 1, ("MR8",), "relations not available: MR8"),
        (1, 1, (), "choose at least one relation"),
    ],
)
def test_bad_options_are_refused(seed, per_case, mrs, message):
    with pytest.raises(generator.VariantError, match=message):
        generator.check_options(seed, per_case, mrs)


def test_only_chosen_relations_are_built(demo_set, fixture_packs):
    directory, _, packs = demo_set
    built = sets.build(directory, 3, mrs=("MR3",), root=packs)
    assert {variant.mr for variant in built.variants} == {"MR3"}
    assert built.manifest.summary.units_per_language == 20
    with pytest.raises(sets.VariantSetError, match="per_case must be at least 1"):
        sets.build(directory, 3, per_case=0, root=packs)


# --- Validation ------------------------------------------------------------------------------------------------------


def test_a_demo_set_is_valid(demo_set):
    _, variants, packs = demo_set
    report = sets.validate(variants, root=packs)
    assert report.ok, report.problems
    assert report.by_mr == {"MR1": 10, "MR2": 10, "MR3": 10, "MR4": 10, "MR5": 30, "MR6": 10, "MR7": 10}


def _rewrite(path: Path, index: int, change) -> None:
    lines = path.read_bytes()[:-1].split(b"\n")
    data = canonical.loads(lines[index])
    change(data)
    lines[index] = canonical.dumps_bytes(data)
    path.write_bytes(b"\n".join(lines) + b"\n")


@pytest.mark.parametrize(
    ("index", "change", "messages"),
    [
        (
            0,
            lambda d: d["key"].update({"determinability": "answer"}),
            ["stored key differs", "differs from the variants"],
        ),
        (
            0,
            lambda d: d["expectation"].update({"questions_include": []}),
            ["expectation must be the engine's decision"],
        ),
        (0, lambda d: d["facts"].pop("exam.rash"), ["facts differ from the base case"]),
        # Index 2 is the first MR3 variant (each case lists MR1, MR2, MR3, MR4, MR5, MR6, MR7).
        (2, lambda d: d["facts"].update({"exam.rash": not d["facts"]["exam.rash"]}), ["facts differ"]),
        (2, lambda d: d["key"].update({"required_questions": ["exam.rash"]}), ["only MR1 has a required question"]),
        (0, lambda d: d.update({"variant_seed": 9}), ["variant seed differs from the set's"]),
        (
            0,
            lambda d: d.update({"case_id": "DEM-000099", "variant_id": "DEM-000099-MR1-1"}),
            ["no base case DEM-000099"],
        ),
    ],
)
def test_validation_finds_changed_variants(demo_set, index, change, messages):
    _, variants, packs = demo_set
    _rewrite(variants / sets.VARIANTS_FILE, index, change)
    text = "\n".join(sets.validate(variants, root=packs).problems)
    for message in messages:
        assert message in text


def test_validation_checks_mr1_fields(demo_set):
    directory, variants, packs = demo_set
    base = next(case for _, case in collection.read_cases(directory / collection.CASES_FILE, []))
    non_critical = sorted(set(base.facts) - set(base.key.critical_fields))[0]

    def change(data):
        facts = dict(base.facts)
        facts.pop(non_critical)
        data.update(facts=facts, change={"kind": "remove_field", "field": non_critical})
        data["expectation"]["questions_include"] = [non_critical]

    _rewrite(variants / sets.VARIANTS_FILE, 0, change)
    assert "must remove a critical field" in "\n".join(sets.validate(variants, root=packs).problems)


def test_validation_checks_files_and_manifest(demo_set):
    _, variants, packs = demo_set
    path = variants / sets.VARIANTS_FILE
    lines = path.read_bytes()[:-1].split(b"\n")
    path.write_bytes(b"\n".join([lines[0], lines[0], b"{broken"]))
    text = "\n".join(sets.validate(variants, root=packs).problems)
    assert "appears twice" in text and ":3: " in text and "must end with a newline" in text
    assert "variants_sha256 does not match" in text and "list of variants differs" in text
    path.write_bytes(b"")
    assert "no variants" in "\n".join(sets.validate(variants, root=packs).problems)
    manifest = variants / sets.MANIFEST_FILE
    manifest.write_text("{", encoding="utf-8")
    assert "variants.json" in "\n".join(sets.validate(variants, root=packs).problems)
    manifest.unlink()
    assert "file is missing" in "\n".join(sets.validate(variants, root=packs).problems)


def test_validation_detects_another_collection_or_changed_inputs(demo_set, edit_yaml):
    directory, variants, packs = demo_set
    manifest = variants / sets.MANIFEST_FILE
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["collection_sha256"] = "0" * 64
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert "belongs to another collection" in "\n".join(sets.validate(variants, root=packs).problems)
    data["collection_sha256"] = json.loads((directory / "collection.json").read_text(encoding="utf-8"))["cases_sha256"]
    data["summary"]["mr1_decisions"] = {}
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert "differs from a rebuild" in "\n".join(sets.validate(variants, root=packs).problems)


def test_the_collection_must_be_intact(demo_set, tmp_path):
    directory, variants, packs = demo_set
    with (directory / collection.CASES_FILE).open("ab") as handle:
        handle.write(b"")
    data = (directory / collection.CASES_FILE).read_bytes()
    (directory / collection.CASES_FILE).write_bytes(data.replace(b'"age":', b'"age": ', 1))
    text = "\n".join(sets.validate(variants, root=packs).problems)
    assert "does not match collection.json" in text or "not in canonical JSON form" in text
    with pytest.raises(sets.VariantSetError, match=r"collection\.json: file is missing"):
        sets.build(tmp_path / "nowhere", 1, root=packs)
    (directory / "collection.json").write_text("{}", encoding="utf-8")
    with pytest.raises(sets.VariantSetError, match="Field required"):
        sets.build(directory, 1, root=packs)


# --- Command line ----------------------------------------------------------------------------------------------------


def test_variants_commands(demo_set, tmp_path):
    directory, _, packs = demo_set
    args = ["variants", "build", "--collection", str(directory), "--variant-seed", "5", "--packs", str(packs)]
    result = runner.invoke(app, [*args, "--mr", "MR1", "--mr", "MR3", "--per-case", "2"])
    assert result.exit_code == 0, result.output
    assert "demo-10, variant seed 5: " in result.output and "variants: MR1 " in result.output
    target = directory / "variants" / "5"
    result = runner.invoke(app, ["variants", "validate", str(target), "--packs", str(packs)])
    assert result.exit_code == 0, result.output
    assert "variants valid (MR1 " in result.output
    out = tmp_path / "elsewhere"
    result = runner.invoke(app, [*args, "--out", str(out), "--per-case", "30", "--mr", "MR3"])
    assert result.exit_code == 0 and "fewer than asked: MR3 70" in result.output
    result = runner.invoke(
        app, ["variants", "validate", str(out), "--collection", str(directory), "--packs", str(packs)]
    )
    assert result.exit_code == 0, result.output
    result = runner.invoke(app, [*args, "--mr", "MR8"])
    assert result.exit_code == 1 and "relations not available: MR8" in result.output
    (target / sets.VARIANTS_FILE).write_bytes(b"")
    result = runner.invoke(app, ["variants", "validate", str(target), "--packs", str(packs)])
    assert result.exit_code == 1 and "problem(s)" in result.output


def test_render_a_variant(demo_set):
    directory, variants, packs = demo_set
    args = ["render", str(directory), "--lang", "en", "--packs", str(packs), "--variants", str(variants)]
    result = runner.invoke(app, [*args, "--variant-id", "DEM-000001-MR3-1"])
    assert result.exit_code == 0, result.output
    headings = [line for line in result.output.splitlines() if line.startswith("###")]
    assert headings != ["### 1. History", "### 2. Examination", "### 3. Vital signs", "### 4. Laboratory"]
    result = runner.invoke(app, [*args, "--variant-id", "DEM-000001-MR5-zh-en"])
    assert result.exit_code == 1 and "has no text" in result.output
    result = runner.invoke(app, [*args, "--variant-id", "DEM-000001-MR9-1"])
    assert result.exit_code == 1 and "no variant DEM-000001-MR9-1" in result.output
    result = runner.invoke(app, ["render", str(directory), "--lang", "en", "--variant-id", "DEM-000001-MR3-1"])
    assert result.exit_code == 1 and "--variants and --variant-id go together" in result.output
