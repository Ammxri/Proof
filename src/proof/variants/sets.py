"""Variant sets of a collection (A-46, A-75): ``variants/<variant seed>/`` with ``variants.jsonl`` and a manifest.

A variant set belongs to one collection and one variant seed. ``variants.jsonl`` holds one variant per line in
canonical JSON; ``variants.json`` records the collection and its content hash, the variant seed, the relations, the
hashes of all inputs, the hash of every variant and a summary. :func:`validate` checks each variant against its base
case and rebuilds the whole set from the seed.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, ValidationError

import proof
from proof.cases import collection as collections
from proof.cases.model import Case, schema_text
from proof.cases.sampler import SamplerError, load_sampler
from proof.core import canonical
from proof.core.hashing import sha256_bytes, sha256_text
from proof.core.manifest import ManifestBase, new_manifest
from proof.variants.generator import BUILT_MRS, REQUESTED_MRS, VariantError, check_options, generate
from proof.variants.model import MR, AbsoluteExpectation, LanguagePair, PermuteSections, RemoveField, Variant
from proof.variants.model import variant_json_schema as _variant_schema
from proof_rules import loader
from proof_rules.keys import FactError, compute_variant_key
from proof_rules.model import Domain

VARIANTS_DIR = "variants"
VARIANTS_FILE = "variants.jsonl"
MANIFEST_FILE = "variants.json"
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[StrictInt, Field(ge=0)]


class VariantSetError(Exception):
    """A variant set cannot be built or read; ``problems`` lists every finding."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VariantEntry(_Model):
    variant_id: str
    sha256: Sha256


class VariantInputs(collections.Inputs):
    """The inputs of the collection plus the variant schema."""

    variant_schema_sha256: Sha256


class VariantSummary(_Model):
    """Counts per relation; for MR1 the decisions expected and the fields left out."""

    variants: dict[MR, Count]
    missing: dict[MR, Count]
    units_per_language: Count
    mr1_decisions: dict[str, Count]
    mr1_removed: dict[str, Count]


class VariantSetManifest(ManifestBase):
    """``variants.json``."""

    kind: Literal["variants"] = "variants"
    collection: str
    collection_sha256: Sha256
    domain: str
    variant_seed: Annotated[StrictInt, Field(ge=0)]
    per_case: Annotated[StrictInt, Field(ge=1)]
    mrs: tuple[MR, ...]
    inputs: VariantInputs
    variants_sha256: Sha256
    variants: tuple[VariantEntry, ...]
    summary: VariantSummary

    def stable_json(self) -> dict[str, Any]:
        return {
            key: value for key, value in self.model_dump(mode="json").items() if key not in collections.VOLATILE_FIELDS
        }


def default_directory(collection_dir: Path, variant_seed: int) -> Path:
    return collection_dir / VARIANTS_DIR / str(variant_seed)


def variants_bytes(variants: Iterable[Variant]) -> bytes:
    return canonical.dumps_lines(variant.to_json() for variant in variants)


def summarize(variants: Sequence[Variant], missing: dict[str, int], mrs: Sequence[str], cases: int) -> VariantSummary:
    counts = Counter(variant.mr for variant in variants)
    decisions: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    for variant in variants:
        if variant.mr == "MR1":
            assert isinstance(variant.expectation, AbsoluteExpectation)  # noqa: S101 - MR1 is absolute (model)
            assert isinstance(variant.change, RemoveField)  # noqa: S101 - MR1 removes a field (model)
            decisions[variant.expectation.decision] += 1
            removed[variant.change.field] += 1
    requested = sum(counts[mr] for mr in REQUESTED_MRS)
    return VariantSummary(
        variants={mr: counts[mr] for mr in mrs},
        missing={mr: count for mr, count in missing.items()},
        units_per_language=cases + requested,
        mr1_decisions={key: decisions[key] for key in sorted(decisions)},
        mr1_removed={key: removed[key] for key in sorted(removed)},
    )


# --- Loading the collection ------------------------------------------------------------------------------------------


def _collection(directory: Path, root: Path) -> tuple[collections.CollectionManifest, list[Case], Domain]:
    path = directory / collections.MANIFEST_FILE
    if not path.is_file():
        raise VariantSetError([f"{path}: file is missing"])
    try:
        manifest = collections.CollectionManifest.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise VariantSetError([f"{path}: {exc}"]) from exc
    problems: list[str] = []
    cases_path = directory / collections.CASES_FILE
    cases = [case for _, case in collections.read_cases(cases_path, problems)] if cases_path.is_file() else []
    if not cases_path.is_file():
        problems.append(f"{cases_path}: file is missing")
    if not problems and sha256_bytes(cases_path.read_bytes()) != manifest.cases_sha256:
        problems.append(f"{cases_path}: does not match collection.json; validate the collection first")
    if problems:
        raise VariantSetError(problems)
    try:
        domain = load_sampler(manifest.domain, root).domain
    except (loader.LoadError, SamplerError) as exc:
        raise VariantSetError(exc.problems) from exc
    return manifest, cases, domain


# --- Building --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BuiltSet:
    variants: tuple[Variant, ...]
    data: bytes
    manifest: VariantSetManifest


def build(
    collection_dir: Path,
    variant_seed: int,
    *,
    per_case: int = 1,
    mrs: Sequence[str] = BUILT_MRS,
    root: Path = loader.PACKS_ROOT,
) -> BuiltSet:
    """Build the variants of every case of a collection for one variant seed."""
    try:
        chosen = check_options(variant_seed, per_case, mrs)
    except VariantError as exc:
        raise VariantSetError([str(exc)]) from exc
    manifest, cases, domain = _collection(collection_dir, root)
    generated = generate(cases, domain, variant_seed, per_case=per_case, mrs=chosen)
    data = variants_bytes(generated.variants)
    sampler = load_sampler(manifest.domain, root)
    inputs = VariantInputs(
        **collections.input_hashes(sampler, root).model_dump(),
        variant_schema_sha256=sha256_text(schema_text(_variant_schema())),
    )
    base = new_manifest("variants", repo_dir=Path(proof.__file__).resolve().parent)
    set_manifest = VariantSetManifest(
        **{**base.model_dump(), "kind": "variants"},
        collection=manifest.name,
        collection_sha256=manifest.cases_sha256,
        domain=domain.name,
        variant_seed=variant_seed,
        per_case=per_case,
        mrs=chosen,
        inputs=inputs,
        variants_sha256=sha256_bytes(data),
        variants=tuple(
            VariantEntry(variant_id=variant.variant_id, sha256=sha256_bytes(canonical.dumps_bytes(variant.to_json())))
            for variant in generated.variants
        ),
        summary=summarize(generated.variants, dict(generated.missing), chosen, len(cases)),
    )
    return BuiltSet(variants=generated.variants, data=data, manifest=set_manifest)


def manifest_text(manifest: VariantSetManifest) -> str:
    return json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write(built: BuiltSet, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    variants_path = directory / VARIANTS_FILE
    manifest_path = directory / MANIFEST_FILE
    variants_path.write_bytes(built.data)
    manifest_path.write_bytes(manifest_text(built.manifest).encode("utf-8"))
    return variants_path, manifest_path


# --- Validation ------------------------------------------------------------------------------------------------------


@dataclass
class Report:
    path: Path
    variants: int = 0
    by_mr: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and self.variants > 0


def read_variants(path: Path, problems: list[str]) -> list[tuple[bytes, Variant]]:
    """The lines of a variants file with their parsed variants; problems are appended."""
    data = path.read_bytes()
    if not data:
        problems.append(f"{path}: no variants")
        return []
    if not data.endswith(b"\n"):
        problems.append(f"{path}: the last line must end with a newline")
        data += b"\n"
    result = []
    for number, line in enumerate(data[:-1].split(b"\n"), start=1):
        where = f"{path}:{number}"
        try:
            parsed = canonical.loads(line)
            variant = Variant.model_validate(parsed)
        except ValidationError as exc:
            problems.extend(
                f"{where}: {'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors(include_url=False)
            )
            continue
        except (ValueError, UnicodeDecodeError) as exc:
            problems.append(f"{where}: {exc}")
            continue
        if canonical.dumps_bytes(parsed) != line:
            problems.append(f"{where}: not in canonical JSON form")
        result.append((line, variant))
    return result


def check_variant(variant: Variant, base: Case, domain: Domain) -> list[str]:
    """Why a variant does not follow from its base case under the rules; empty if it does."""
    where = variant.variant_id
    problems = []
    change = variant.change
    if isinstance(change, RemoveField):
        expected_facts = {code: value for code, value in base.facts.items() if code != change.field}
        if change.field not in base.facts:
            problems.append(f"{where}: removes {change.field}, which the base case does not have")
        if change.field not in base.key.critical_fields:
            problems.append(f"{where}: MR1 must remove a critical field, {change.field} is not critical")
    else:
        expected_facts = dict(base.facts)
    if variant.facts != expected_facts:
        problems.append(f"{where}: facts differ from the base case with the change applied")
        return problems
    try:
        key = compute_variant_key(domain, variant.facts, base.facts)
    except FactError as exc:
        return [f"{where}: {problem}" for problem in exc.problems]
    if key != variant.key:
        problems.append(f"{where}: stored key differs from the key the rule set computes")
    expectation = variant.expectation
    if isinstance(expectation, AbsoluteExpectation):
        assert isinstance(change, RemoveField)  # noqa: S101 - only MR1 is absolute (model)
        if expectation.decision != key.determinability or expectation.questions_include != (change.field,):
            problems.append(f"{where}: expectation must be the engine's decision and the removed field as question")
    elif isinstance(change, PermuteSections | LanguagePair) and variant.key.required_questions:
        problems.append(f"{where}: a variant with all facts has no required question")
    return problems


def validate(directory: Path, collection_dir: Path | None = None, root: Path = loader.PACKS_ROOT) -> Report:
    """Check a variant set: every variant against its base case, the manifest, and a rebuild from the seed."""
    report = Report(path=directory)
    variants_path = directory / VARIANTS_FILE
    manifest_path = directory / MANIFEST_FILE
    for path in (variants_path, manifest_path):
        if not path.is_file():
            report.problems.append(f"{path}: file is missing")
    if report.problems:
        return report
    try:
        manifest = VariantSetManifest.model_validate(canonical.loads(manifest_path.read_bytes()))
    except (ValueError, UnicodeDecodeError) as exc:
        report.problems.append(f"{manifest_path}: {exc}")
        return report
    collection_dir = collection_dir if collection_dir is not None else directory.parent.parent
    try:
        collection_manifest, cases, domain = _collection(collection_dir, root)
    except VariantSetError as exc:
        report.problems.extend(exc.problems)
        return report
    if (collection_manifest.name, collection_manifest.cases_sha256) != (
        manifest.collection,
        manifest.collection_sha256,
    ):
        report.problems.append(f"{manifest_path}: belongs to another collection or an older version of it")
    parsed = read_variants(variants_path, report.problems)
    report.variants = len(parsed)
    report.by_mr = dict(Counter(variant.mr for _, variant in parsed))
    by_id = {case.case_id: case for case in cases}
    seen: set[str] = set()
    for _, variant in parsed:
        if variant.variant_id in seen:
            report.problems.append(f"{variant.variant_id}: appears twice")
        seen.add(variant.variant_id)
        base = by_id.get(variant.case_id)
        if base is None:
            report.problems.append(f"{variant.variant_id}: no base case {variant.case_id} in {collection_dir}")
            continue
        if variant.variant_seed != manifest.variant_seed:
            report.problems.append(f"{variant.variant_id}: variant seed differs from the set's")
        report.problems.extend(check_variant(variant, base, domain))
    data = variants_path.read_bytes()
    if manifest.variants_sha256 != sha256_bytes(data):
        report.problems.append(f"{manifest_path}: variants_sha256 does not match {VARIANTS_FILE}")
    if [entry.variant_id for entry in manifest.variants] != [variant.variant_id for _, variant in parsed]:
        report.problems.append(f"{manifest_path}: the list of variants differs from {VARIANTS_FILE}")
    try:
        rebuilt = build(collection_dir, manifest.variant_seed, per_case=manifest.per_case, mrs=manifest.mrs, root=root)
    except VariantSetError as exc:  # pragma: no cover - the collection loaded above
        report.problems.extend(exc.problems)
        return report
    if rebuilt.data != data:
        report.problems.append(f"{variants_path}: differs from the variants the seed {manifest.variant_seed} gives")
    if rebuilt.manifest.stable_json() != manifest.stable_json():
        report.problems.append(f"{manifest_path}: differs from a rebuild (inputs, entries or summary changed)")
    return report
