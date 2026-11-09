"""Case collections: Fever-100 (PR-F01, PR-F03, PR-F04, PR-K01, PR-K04, PR-A05, PR-D04, PR-L01) and validation."""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import jsonschema
import pytest

from proof.cases import collection
from proof.cases.collection import CollectionError, CollectionManifest
from proof.cases.model import Case, case_json_schema
from proof.cases.sampler import Sample, Target
from proof.core import canonical
from proof.core.hashing import sha256_bytes
from proof_rules import loader
from proof_rules.keys import compute_key

FEVER_100 = Path(__file__).resolve().parents[2] / "data" / "collections" / "fever-100"
CODE = re.compile(r"^[A-Za-z0-9_.\-]+$")


@pytest.fixture(scope="module")
def fever_lines() -> list[bytes]:
    data = (FEVER_100 / collection.CASES_FILE).read_bytes()
    assert data.endswith(b"\n")
    return data[:-1].split(b"\n")


@pytest.fixture(scope="module")
def fever_cases(fever_lines) -> list[Case]:
    return [Case.model_validate(canonical.loads(line)) for line in fever_lines]


@pytest.fixture(scope="module")
def fever_manifest() -> CollectionManifest:
    return CollectionManifest.model_validate(canonical.loads((FEVER_100 / collection.MANIFEST_FILE).read_bytes()))


@pytest.fixture
def demo_collection(tmp_path, fixture_packs) -> tuple[Path, Path]:
    """A demo collection with 12 cases in a writable directory, built from a writable copy of the test packs."""
    packs = tmp_path / "packs"
    shutil.copytree(fixture_packs, packs)
    built = collection.build("demo", 12, 1, name="demo-12", root=packs)
    directory = tmp_path / "demo-12"
    collection.write(built, directory)
    return directory, packs


# --- Fever-100 -------------------------------------------------------------------------------------------------------


def test_fever_100_is_valid(fever_cases):
    report = collection.validate(FEVER_100)
    assert report.ok, "\n".join(report.problems)
    assert report.cases == 100 == len(fever_cases)
    assert [case.case_id for case in fever_cases] == [f"FEV-{seed:06d}" for seed in range(1, 101)]


def test_fever_100_passes_the_json_schema(fever_lines):
    """PR-F01: every case passes Pydantic (above) and the JSON Schema."""
    validator = jsonschema.Draft202012Validator(case_json_schema())
    for line in fever_lines:
        validator.validate(json.loads(line))


def test_fever_100_is_rebuilt_byte_for_byte(fever_lines, fever_manifest):
    """PR-F03, PR-A05: the committed cases come from sampler and rules alone and are reproduced from their seeds."""
    built = collection.build("fever", 100, 1)
    assert built.cases_bytes == b"".join(line + b"\n" for line in fever_lines)
    assert built.manifest.stable_json() == fever_manifest.stable_json()


def test_key_with_ablation_takes_less_than_one_second_per_case(fever_cases):
    """PR-F04 (A-29): measured over the whole collection, on Windows and Linux in the CI."""
    domain = loader.load_domain("fever")
    slowest = 0.0
    for case in fever_cases:
        started = time.perf_counter()
        key = compute_key(domain, case.facts)
        slowest = max(slowest, time.perf_counter() - started)
        assert key == case.key
    assert slowest < 1.0, f"slowest key took {slowest:.3f} s"


def test_cases_hold_codes_and_values_but_no_free_text(fever_cases):
    """PR-K01: a case is a set of coded facts; every string in it is a code."""

    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    for case in fever_cases:
        for text in strings(case.to_json()):
            assert CODE.match(text), (case.case_id, text)


def test_fever_100_manifest_records_provenance_and_distribution(fever_manifest, fever_lines):
    manifest = fever_manifest
    assert manifest.kind == "collection" and manifest.name == "fever-100" and manifest.domain == "fever"
    assert (manifest.seed_start, manifest.n) == (1, 100)
    assert manifest.cases_sha256 == sha256_bytes(b"".join(line + b"\n" for line in fever_lines))
    assert len(manifest.plan) == 7
    summary = manifest.summary
    assert summary.cases == 100
    assert summary.relabeled == sum(entry.relabeled for entry in manifest.cases)
    assert sum(summary.determinability.values()) == 100
    assert set(summary.determinability) <= {"answer", "refer_urgent"}
    assert sum(target.cases for target in summary.targets.values()) == 100
    assert sum(cases for _, cases in summary.ddx_per_case) == 100
    assert set(manifest.inputs.profiles_sha256) == {
        "lab.bilirubin_umol_l",
        "lab.creatinine_umol_l",
        "lab.crp_mg_l",
        "lab.lactate_mmol_l",
    }
    assert manifest.git is None or not manifest.git.dirty, "build the collection from a committed tree"


# --- Building and validating -----------------------------------------------------------------------------------------


def test_build_write_and_validate(demo_collection):
    directory, packs = demo_collection
    report = collection.validate(directory, packs)
    assert report.ok, report.problems
    assert (report.cases, report.relabeled) == (12, 0)
    assert report.max_key_seconds < 1.0
    manifest = CollectionManifest.model_validate(canonical.loads((directory / "collection.json").read_bytes()))
    assert manifest.name == "demo-12"
    assert collection.manifest_text(manifest).encode("utf-8") == (directory / "collection.json").read_bytes()
    # A JSONL file alone is validated without manifest.
    assert collection.validate(directory / "cases.jsonl", packs).ok


def test_relabeled_cases_are_counted(fever_cases):
    """PR-K04: a key that misses its target is counted per target and in total."""
    sample = Sample(case=fever_cases[2], target=Target("ddx.pneumonia", "absent"))
    assert not sample.relabeled
    wrong = Sample(case=sample.case, target=Target("ddx.pneumonia", "present"))
    summary = collection.summarize([sample, wrong])
    assert summary.relabeled == 1
    assert summary.targets["ddx.pneumonia/present"].relabeled == 1
    assert summary.targets["ddx.pneumonia/absent"].relabeled == 0


def _rewrite_line(path: Path, index: int, change) -> None:
    lines = path.read_bytes()[:-1].split(b"\n")
    data = canonical.loads(lines[index])
    change(data)
    lines[index] = canonical.dumps_bytes(data)
    path.write_bytes(b"\n".join(lines) + b"\n")


@pytest.mark.parametrize(
    ("change", "messages"),
    [
        (
            lambda d: d["key"].update({"determinability": "answer", "red_flags": []}),
            ["stored key differs", "differs from the case the sampler draws", "cases_sha256 does not match"],
        ),
        (lambda d: d["facts"].update({"vital.temp_c": 36.6}), ["differs from the case the sampler draws"]),
        (lambda d: d["facts"].pop("exam.rash"), ["base case lacks facts exam.rash"]),
        (lambda d: d["facts"].update({"vital.temp_c": 99.0}), ["outside the physiological bounds"]),
        (lambda d: d.update({"complaint": "headache"}), ["no domain pack for complaint 'headache'"]),
        (lambda d: d.update({"case_id": "XYZ-000001"}), ["id prefix differs from DEM"]),
        (lambda d: d["patient"].update({"age": 70}), ["age 70 outside 18..30"]),
        (lambda d: d.update({"facts": {}}), ["at least 1 item"]),
    ],
)
def test_validation_finds_changed_cases(demo_collection, change, messages):
    directory, packs = demo_collection
    _rewrite_line(directory / "cases.jsonl", 0, change)
    report = collection.validate(directory, packs)
    assert not report.ok
    text = "\n".join(report.problems)
    for message in messages:
        assert message in text


def test_validation_finds_format_problems(demo_collection):
    directory, packs = demo_collection
    path = directory / "cases.jsonl"
    lines = path.read_bytes()[:-1].split(b"\n")
    pretty = json.dumps(json.loads(lines[0]), indent=1).replace("\n", " ").encode("utf-8")
    path.write_bytes(b"\n".join([pretty, lines[2], lines[1], lines[2], b"{broken"]))
    text = "\n".join(collection.validate(directory, packs).problems)
    assert "not in canonical JSON form" in text
    assert "must be ordered by ascending seed" in text
    assert "DEM-000003: appears twice" in text
    assert ":5: " in text  # the broken JSON line
    assert "must end with a newline" in text
    path.write_bytes(b"")
    assert "no cases" in "\n".join(collection.validate(directory, packs).problems)
    path.unlink()
    assert "file is missing" in "\n".join(collection.validate(directory, packs).problems)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["summary"].update({"relabeled": 5}), "summary differs from the cases"),
        (lambda d: d.update({"cases_sha256": "0" * 64}), "cases_sha256 does not match"),
        (lambda d: d.update({"n": 13}), "lists 12 of n=13 cases"),
        (lambda d: d.update({"seed_start": 2}), "seeds are not 2..13"),
        (lambda d: d["cases"][0].update({"sha256": "0" * 64}), "entry DEM-000001 does not match"),
        (lambda d: d["cases"][0]["target"].update({"red_flag": "absent"}), "target or relabeling of DEM-000001"),
        (lambda d: d["inputs"].update({"rules_sha256": "0" * 64}), "input rules_sha256 changed"),
        (lambda d: d.update({"kind": "run"}), "Input should be 'collection'"),
    ],
)
def test_validation_checks_the_manifest(demo_collection, change, message):
    directory, packs = demo_collection
    path = directory / "collection.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")
    assert message in "\n".join(collection.validate(directory, packs).problems)


def test_validation_detects_changed_inputs(demo_collection, edit_yaml):
    directory, packs = demo_collection
    edit_yaml(packs / "demo/sampler.yaml", lambda d: d["facts"]["exam.rash"].update({"p_true": [1, 3]}))
    text = "\n".join(collection.validate(directory, packs).problems)
    assert "input sampler_sha256 changed" in text
    assert "differs from the case the sampler draws" in text


def test_validation_reports_broken_manifests_and_packs(demo_collection):
    directory, packs = demo_collection
    (packs / "demo/sampler.yaml").unlink()
    problems = collection.validate(directory, packs).problems
    assert len([problem for problem in problems if problem.startswith("domain demo:")]) == 1
    assert "file is missing" in "\n".join(problems)
    (directory / "collection.json").write_text("{", encoding="utf-8")
    assert "collection.json" in "\n".join(collection.validate(directory, packs).problems)


def test_a_case_built_for_another_plan_is_reported(demo_collection, edit_yaml):
    directory, packs = demo_collection
    edit_yaml(packs / "demo/sampler.yaml", lambda d: d["plan"].reverse())
    text = "\n".join(collection.validate(directory, packs).problems)
    assert "target or relabeling of DEM-000001 differs from the sampler" in text
    assert "input sampler_sha256 changed" in text


@pytest.mark.parametrize(
    ("n", "seed_start", "message"),
    [(0, 1, "n must be at least 1"), (5, -1, "do not fit six digits"), (2, 999_999, "do not fit six digits")],
)
def test_seed_ranges_are_checked(n, seed_start, message):
    with pytest.raises(CollectionError, match=message):
        collection.build("fever", n, seed_start)


def test_unknown_domains_are_reported():
    with pytest.raises(CollectionError, match="no pack 'nope'"):
        collection.build("nope", 1, 1)


def test_text_helpers():
    assert collection.counts_line({"answer": 4, "refer_urgent": 6}) == "answer 4, refer_urgent 6"
    assert collection.counts_line({}) == "-"
    assert collection.pairs_line([(1, 2), (3, 4)]) == "1: 2, 3: 4"
    assert collection.pairs_line([]) == "-"
