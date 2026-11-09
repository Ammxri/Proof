"""Profiles of runs and comparison of two runs (PR-F08, PR-P02, PR-D02, UF-02, UF-05).

The scoring reads a run directory (``manifest.json``, ``units.jsonl``) as plain files and takes each unit's key from
the collection and variant set the run names; it never imports the test-run client and never calls a model
(PR-N04). ``profile.json`` holds every metric with numerator and denominator and no value that combines metrics.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from proof.cases import collection as collections
from proof.core.hashing import sha256_bytes
from proof.core.manifest import utc_now
from proof.scoring.metrics import NA, Evaluated, Expected, Truth, UnitInput, evaluate, metrics
from proof.scoring.response import AllowedCodes
from proof.variants import sets as variant_sets
from proof.variants.model import AbsoluteExpectation, Variant
from proof_rules import loader

MANIFEST_FILE = "manifest.json"
UNITS_FILE = "units.jsonl"
PROFILE_FILE = "profile.json"
PROFILE_VERSION = 1


class ScoringError(Exception):
    """A run cannot be scored; ``problems`` lists every finding."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


@dataclass(frozen=True)
class LoadedRun:
    directory: Path
    manifest: dict[str, Any]
    inputs: tuple[UnitInput, ...]
    allowed: AllowedCodes
    langs: tuple[str, ...]


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise ScoringError([f"{path}: file is missing"])
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ScoringError([f"{path}: {exc}"]) from exc


def _read_units(path: Path) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        raise ScoringError([f"{path}: file is missing"])
    latest: dict[str, dict[str, Any]] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            latest[record["unit_id"]] = record
        except (ValueError, KeyError, TypeError) as exc:
            raise ScoringError([f"{path}:{number}: {exc}"]) from exc
    return latest


def _truths(collection_dir: Path, variants_dir: Path | None, config: Mapping[str, Any]) -> tuple[dict, dict, str]:
    """Key and expectation of every item (case id or variant id) the run may have asked."""
    manifest_path = collection_dir / collections.MANIFEST_FILE
    cases_path = collection_dir / collections.CASES_FILE
    if not cases_path.is_file() or sha256_bytes(cases_path.read_bytes()) != config.get("collection_sha256"):
        raise ScoringError([f"{cases_path}: missing or not the cases the run used"])
    domain_name = _read_json(manifest_path).get("domain")
    problems: list[str] = []
    truths: dict[str, Truth] = {}
    expected: dict[str, Expected] = {}
    for _, case in collections.read_cases(cases_path, problems):
        key = case.key
        truths[case.case_id] = Truth(
            key.determinability, frozenset(key.red_flags), frozenset(key.ddx), frozenset(), complete=True
        )
    if variants_dir is not None:
        path = variants_dir / variant_sets.VARIANTS_FILE
        if not path.is_file() or sha256_bytes(path.read_bytes()) != config.get("variants_sha256"):
            raise ScoringError([f"{path}: missing or not the variant set the run used"])
        variant: Variant
        for _, variant in variant_sets.read_variants(path, problems):
            key = variant.key
            complete = variant.change.kind != "remove_field"
            truths[variant.variant_id] = Truth(
                key.determinability,
                frozenset(key.red_flags),
                frozenset(key.ddx),
                frozenset(key.required_questions),
                complete=complete,
            )
            spec = variant.expectation
            if isinstance(spec, AbsoluteExpectation):
                expected[variant.variant_id] = Expected(
                    "absolute", decision=spec.decision, questions_include=frozenset(spec.questions_include)
                )
            else:
                expected[variant.variant_id] = Expected("invariant", compare=tuple(spec.compare))
    if problems:
        raise ScoringError(problems)
    return truths, expected, str(domain_name)


def load_run(directory: Path, root: Path = loader.PACKS_ROOT, base_dir: Path | None = None) -> LoadedRun:
    """Read a run and attach to each unit its key and expectation.

    Collection and variant paths in the manifest are taken relative to ``base_dir`` (default: the current directory,
    as when the run was started).
    """
    manifest = _read_json(directory / MANIFEST_FILE)
    if manifest.get("kind") != "run":
        raise ScoringError([f"{directory / MANIFEST_FILE}: not a run manifest"])
    config = manifest.get("config", {})
    base = base_dir if base_dir is not None else Path.cwd()
    collection_dir = base / config["collection"]
    variants_dir = base / config["variants"] if config.get("variants") else None
    truths, expected, domain_name = _truths(collection_dir, variants_dir, config)
    allowed = AllowedCodes.of(loader.load_domain(domain_name, root))
    inputs = []
    for record in _read_units(directory / UNITS_FILE).values():
        item = record["item_id"]
        if item not in truths:
            raise ScoringError([f"{record['unit_id']}: no key for {item} in the run's collection or variant set"])
        inputs.append(
            UnitInput(
                unit_id=record["unit_id"],
                item_id=item,
                case_id=record["case_id"],
                mr=record.get("mr"),
                lang=record["lang"],
                status="ok" if record.get("status") == "ok" else "error",
                text=record.get("text"),
                truth=truths[item],
                expected=expected.get(item),
            )
        )
    langs = tuple(config.get("langs") or sorted({unit.lang for unit in inputs}))
    return LoadedRun(directory=directory, manifest=manifest, inputs=tuple(inputs), allowed=allowed, langs=langs)


def profile(run: LoadedRun) -> dict[str, Any]:
    """The profile of a run: provenance and the separate metrics (no combined value, PR-P02)."""
    manifest = run.manifest
    provider = manifest.get("config", {}).get("provider", {})
    return {
        "kind": "profile",
        "profile_version": PROFILE_VERSION,
        "created_utc": utc_now(),
        "deterministic": True,
        "run_id": manifest.get("run_id"),
        "run_status": manifest.get("status"),
        "provider": {key: provider.get(key) for key in ("name", "api", "model", "origin", "region")},
        "models_reported": manifest.get("models_reported", []),
        "collection": manifest.get("config", {}).get("collection"),
        "variant_seed": manifest.get("seeds", {}).get("variant_seed"),
        "langs": list(run.langs),
        "metrics": metrics(run.inputs, run.allowed, run.langs),
    }


def write_profile(run: LoadedRun) -> tuple[Path, dict[str, Any]]:
    data = profile(run)
    path = run.directory / PROFILE_FILE
    path.write_bytes((json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path, data


# --- Comparison ------------------------------------------------------------------------------------------------------


def flatten(data: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    """Every value of a metrics tree under a dotted path: ratios and spreads by their ``value``."""
    result: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping) and "value" in value:
            result[path] = value["value"]
        elif isinstance(value, Mapping):
            result.update(flatten(value, path))
        else:
            result[path] = value
    return result


def _unit_view(item: Evaluated) -> dict[str, Any]:
    truth = item.unit.truth
    return {
        "valid": item.valid,
        "decision": item.decision,
        "decision_correct": item.decision == truth.determinability,
        "red_flags_found": len(item.red_flags & truth.red_flags),
        "diagnosis_hit": bool(item.ddx & truth.ddx),
        "required_questions_found": len(item.questions & truth.required_questions),
    }


def compare(first: LoadedRun, second: LoadedRun) -> dict[str, Any]:
    """Changes per metric and per unit between two runs (regression, UF-05)."""
    a = flatten(metrics(first.inputs, first.allowed, first.langs))
    b = flatten(metrics(second.inputs, second.allowed, second.langs))
    changes = []
    for path in sorted(set(a) | set(b)):
        old, new = a.get(path, NA), b.get(path, NA)
        if old == new:
            continue
        numeric = isinstance(old, int | float) and isinstance(new, int | float)
        changes.append({"metric": path, "a": old, "b": new, "delta": round(new - old, 4) if numeric else NA})
    units_a = {unit.unit_id: unit for unit in first.inputs}
    units_b = {unit.unit_id: unit for unit in second.inputs}
    unit_changes = []
    for unit_id in sorted(set(units_a) & set(units_b)):
        before = _unit_view(evaluate(units_a[unit_id], first.allowed)) if units_a[unit_id].status == "ok" else None
        after = _unit_view(evaluate(units_b[unit_id], second.allowed)) if units_b[unit_id].status == "ok" else None
        if before != after:
            unit_changes.append({"unit_id": unit_id, "a": before, "b": after})
    return {
        "kind": "comparison",
        "a": {"run_id": first.manifest.get("run_id"), "models": first.manifest.get("models_reported", [])},
        "b": {"run_id": second.manifest.get("run_id"), "models": second.manifest.get("models_reported", [])},
        "metrics": changes,
        "units_changed": unit_changes,
        "units_only_in_a": sorted(set(units_a) - set(units_b)),
        "units_only_in_b": sorted(set(units_b) - set(units_a)),
    }
