"""Case collections (PR-D04, PR-L01): base cases as JSON Lines with a manifest (A-34, A-46, A-69).

A collection directory holds two files:

- ``cases.jsonl``: one case per line in canonical JSON, ordered by seed;
- ``collection.json``: the manifest. It records provenance (versions, hashes of every input), the seed range and target
  plan, the content hash and target of every case, the cases whose key misses their target (relabeled, PR-K04) and the
  distribution of determinability, red flags, diagnoses and critical fields.

:func:`validate` checks a collection completely: schema, canonical form, complete and valid facts, the key recomputed
by the rule set, the case rebuilt from its seed, and the manifest against the cases and the current inputs.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, ValidationError

import proof
from proof.cases.model import Case, case_json_schema, schema_text
from proof.cases.profiles import profile_name
from proof.cases.sampler import (
    SAMPLER_FILE,
    PlanEntry,
    RedFlagStatus,
    Sample,
    Sampler,
    SamplerError,
    load_sampler,
)
from proof.core import canonical
from proof.core.hashing import sha256_bytes, sha256_file, sha256_json, sha256_text
from proof.core.manifest import ManifestBase, new_manifest
from proof_rules import loader
from proof_rules.keys import FactError, compute_key

CASES_FILE = "cases.jsonl"
MANIFEST_FILE = "collection.json"
DEFAULT_ROOT = Path("data") / "collections"
VOLATILE_FIELDS = frozenset({"created_utc", "platform", "git"})

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[StrictInt, Field(ge=0)]


class CollectionError(Exception):
    """A collection cannot be built or read; ``problems`` lists every finding."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


# --- Manifest --------------------------------------------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TargetEntry(_Model):
    ddx: str
    red_flag: RedFlagStatus


class CaseEntry(_Model):
    case_id: str
    seed: Count
    sha256: Sha256
    target: TargetEntry
    relabeled: bool


class Inputs(_Model):
    """SHA-256 of all a case depends on: schema, active rules, catalog, vocabulary, sources, sampler, profiles."""

    schema_sha256: Sha256
    rules_sha256: Sha256
    catalog_sha256: Sha256
    vocabulary_sha256: Sha256
    sources_sha256: Sha256
    sampler_sha256: Sha256
    profiles_sha256: dict[str, Sha256]


class TargetCount(_Model):
    cases: Count
    relabeled: Count


class AgeRange(_Model):
    min: Count
    max: Count


class Summary(_Model):
    """Distribution of the collection, for the progress report and the dataset card.

    ``ddx_per_case`` and ``critical_fields_per_case`` are pairs (number per case, cases), ascending.
    """

    cases: Count
    relabeled: Count
    targets: dict[str, TargetCount]
    determinability: dict[str, Count]
    red_flags: dict[str, Count]
    ddx: dict[str, Count]
    ddx_per_case: tuple[tuple[Count, Count], ...]
    critical_fields: dict[str, Count]
    critical_fields_per_case: tuple[tuple[Count, Count], ...]
    sex: dict[str, Count]
    age: AgeRange


class CollectionManifest(ManifestBase):
    """``collection.json``: provenance, plan, cases with hashes and targets, distribution."""

    kind: Literal["collection"] = "collection"
    name: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$")]
    domain: str
    complaint: str
    seed_start: Count
    n: Annotated[StrictInt, Field(ge=1)]
    plan: tuple[PlanEntry, ...]
    inputs: Inputs
    cases_sha256: Sha256
    cases: tuple[CaseEntry, ...]
    summary: Summary

    def stable_json(self) -> dict[str, Any]:
        """The manifest without the fields that change from build to build (time, platform, git state)."""
        return {key: value for key, value in self.model_dump(mode="json").items() if key not in VOLATILE_FIELDS}


def manifest_text(manifest: CollectionManifest) -> str:
    """Readable, stable text of ``collection.json``: sorted keys, two-space indent, final newline."""
    return json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# --- Inputs and summary ----------------------------------------------------------------------------------------------


def input_hashes(sampler: Sampler, root: Path) -> Inputs:
    domain = sampler.domain
    directory = root / domain.name / loader.PROFILES_DIR
    return Inputs(
        schema_sha256=sha256_text(schema_text(case_json_schema())),
        rules_sha256=sha256_json([rule.model_dump(mode="json") for rule in domain.rules]),
        catalog_sha256=sha256_json(domain.catalog.model_dump(mode="json")),
        vocabulary_sha256=sha256_json(domain.vocabulary.model_dump(mode="json")),
        sources_sha256=sha256_json(domain.sources.model_dump(mode="json")),
        sampler_sha256=sha256_json(sampler.spec.model_dump(mode="json")),
        profiles_sha256={code: sha256_file(directory / profile_name(code)) for code in sorted(sampler.lab_profiles)},
    )


def _counts(counter: Counter[str]) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter)}


def _pairs(counter: Counter[int]) -> tuple[tuple[int, int], ...]:
    return tuple((key, counter[key]) for key in sorted(counter))


def summarize(samples: Sequence[Sample]) -> Summary:
    targets: dict[str, list[int]] = {}
    determinability: Counter[str] = Counter()
    red_flags: Counter[str] = Counter()
    ddx: Counter[str] = Counter()
    ddx_per_case: Counter[int] = Counter()
    critical: Counter[str] = Counter()
    critical_per_case: Counter[int] = Counter()
    sex: Counter[str] = Counter()
    ages = []
    for sample in samples:
        key = sample.case.key
        counts = targets.setdefault(sample.target.label, [0, 0])
        counts[0] += 1
        counts[1] += sample.relabeled
        determinability[key.determinability] += 1
        red_flags.update(key.red_flags)
        ddx.update(key.ddx)
        ddx_per_case[len(key.ddx)] += 1
        critical.update(key.critical_fields)
        critical_per_case[len(key.critical_fields)] += 1
        sex[sample.case.patient.sex] += 1
        ages.append(sample.case.patient.age)
    return Summary(
        cases=len(samples),
        relabeled=sum(sample.relabeled for sample in samples),
        targets={label: TargetCount(cases=c, relabeled=r) for label, (c, r) in sorted(targets.items())},
        determinability=_counts(determinability),
        red_flags=_counts(red_flags),
        ddx=_counts(ddx),
        ddx_per_case=_pairs(ddx_per_case),
        critical_fields=_counts(critical),
        critical_fields_per_case=_pairs(critical_per_case),
        sex=_counts(sex),
        age=AgeRange(min=min(ages), max=max(ages)),
    )


# --- Building --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Built:
    """A built collection: its samples, the bytes of ``cases.jsonl``, the manifest and the slowest case."""

    samples: tuple[Sample, ...]
    cases_bytes: bytes
    manifest: CollectionManifest
    max_seconds: float


def cases_bytes(cases: Iterable[Case]) -> bytes:
    """``cases.jsonl``: canonical JSON, one case per line."""
    return canonical.dumps_lines(case.to_json() for case in cases)


def check_seeds(n: int, seed_start: int) -> None:
    if n < 1:
        raise CollectionError([f"n must be at least 1, got {n}"])
    if seed_start < 0 or seed_start + n - 1 > 999_999:
        raise CollectionError([f"seeds {seed_start}..{seed_start + n - 1} do not fit six digits (0..999999)"])


def build(
    domain: str,
    n: int,
    seed_start: int,
    *,
    name: str | None = None,
    root: Path = loader.PACKS_ROOT,
) -> Built:
    """Sample ``n`` cases with seeds ``seed_start .. seed_start + n - 1`` and describe them in a manifest."""
    check_seeds(n, seed_start)
    try:
        sampler = load_sampler(domain, root)
    except (loader.LoadError, SamplerError) as exc:
        raise CollectionError(exc.problems) from exc
    samples = []
    slowest = 0.0
    for seed in range(seed_start, seed_start + n):
        started = time.perf_counter()
        samples.append(sampler.sample(seed))
        slowest = max(slowest, time.perf_counter() - started)
    data = cases_bytes(sample.case for sample in samples)
    base = new_manifest("collection", repo_dir=Path(proof.__file__).resolve().parent)
    manifest = CollectionManifest(
        **{**base.model_dump(), "kind": "collection"},
        name=name or f"{domain}-{n}",
        domain=sampler.domain.name,
        complaint=sampler.domain.complaint,
        seed_start=seed_start,
        n=n,
        plan=sampler.spec.plan,
        inputs=input_hashes(sampler, root),
        cases_sha256=sha256_bytes(data),
        cases=tuple(
            CaseEntry(
                case_id=sample.case.case_id,
                seed=sample.case.seed,
                sha256=sha256_json(sample.case.to_json()),
                target=TargetEntry(ddx=sample.target.ddx, red_flag=sample.target.red_flag),
                relabeled=sample.relabeled,
            )
            for sample in samples
        ),
        summary=summarize(samples),
    )
    return Built(samples=tuple(samples), cases_bytes=data, manifest=manifest, max_seconds=slowest)


def write(built: Built, directory: Path) -> tuple[Path, Path]:
    """Write ``cases.jsonl`` and ``collection.json`` into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    cases_path = directory / CASES_FILE
    manifest_path = directory / MANIFEST_FILE
    cases_path.write_bytes(built.cases_bytes)
    manifest_path.write_bytes(manifest_text(built.manifest).encode("utf-8"))
    return cases_path, manifest_path


# --- Reading and validating ------------------------------------------------------------------------------------------


def _model_problems(exc: ValidationError, where: str) -> list[str]:
    problems = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(part) for part in error["loc"])
        message = error["msg"].removeprefix("Value error, ")
        problems.append(f"{where}: {location}: {message}" if location else f"{where}: {message}")
    return problems


def read_cases(path: Path, problems: list[str]) -> list[tuple[bytes, Case]]:
    """The lines of a JSONL file with their parsed cases; every problem is appended to ``problems``."""
    data = path.read_bytes()
    if not data:
        problems.append(f"{path}: no cases")
        return []
    if not data.endswith(b"\n"):
        problems.append(f"{path}: the last line must end with a newline")
        data += b"\n"
    result = []
    for number, line in enumerate(data[:-1].split(b"\n"), start=1):
        where = f"{path}:{number}"
        try:
            parsed = canonical.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            problems.append(f"{where}: {exc}")
            continue
        try:
            case = Case.model_validate(parsed)
        except ValidationError as exc:
            problems.extend(_model_problems(exc, where))
            continue
        if canonical.dumps_bytes(parsed) != line:
            problems.append(f"{where}: not in canonical JSON form")
        result.append((line, case))
    return result


@dataclass
class Report:
    """Result of :func:`validate`."""

    path: Path
    cases: int = 0
    relabeled: int = 0
    max_key_seconds: float = 0.0
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems and self.cases > 0


def _resolve(path: Path) -> tuple[Path, Path | None]:
    if path.is_dir():
        manifest = path / MANIFEST_FILE
        return path / CASES_FILE, manifest if manifest.is_file() else None
    return path, None


def _check_case(
    line: bytes,
    case: Case,
    samplers: dict[str, Sampler | None],
    root: Path,
    report: Report,
) -> Sample | None:
    where = f"{case.case_id}"
    name = loader.domain_for_complaint(case.complaint, root)
    if name is None:
        report.problems.append(f"{where}: no domain pack for complaint {case.complaint!r}")
        return None
    if name not in samplers:
        try:
            samplers[name] = load_sampler(name, root)
        except (loader.LoadError, SamplerError) as exc:
            samplers[name] = None
            report.problems.extend(f"domain {name}: {problem}" for problem in exc.problems)
    sampler = samplers[name]
    if sampler is None:
        return None
    domain = sampler.domain
    if not case.case_id.startswith(domain.case_prefix + "-"):
        report.problems.append(f"{where}: id prefix differs from {domain.case_prefix} of domain {domain.name}")
    age = sampler.spec.patient.age
    if not age.lower <= case.patient.age <= age.upper:
        report.problems.append(f"{where}: age {case.patient.age} outside {age.lower}..{age.upper} of the domain")
    missing = sorted(set(domain.catalog.codes()) - set(case.facts))
    if missing:
        report.problems.append(f"{where}: base case lacks facts {', '.join(missing)} (A-07)")
    started = time.perf_counter()
    try:
        key = compute_key(domain, case.facts)
    except FactError as exc:
        report.problems.extend(f"{where}: {problem}" for problem in exc.problems)
        return None
    report.max_key_seconds = max(report.max_key_seconds, time.perf_counter() - started)
    if key != case.key:
        report.problems.append(f"{where}: stored key differs from the key the rule set computes")
    sample = sampler.sample(case.seed)
    if canonical.dumps_bytes(sample.case.to_json()) != line:
        report.problems.append(f"{where}: differs from the case the sampler draws for seed {case.seed}")
    return Sample(case=case, target=sample.target)


def _check_manifest(path: Path, report: Report, lines: Sequence[bytes], samples: Sequence[Sample], root: Path) -> None:
    try:
        data_json = canonical.loads(path.read_bytes())
    except (ValueError, UnicodeDecodeError) as exc:
        report.problems.append(f"{path}: {exc}")
        return
    try:
        manifest = CollectionManifest.model_validate(data_json)
    except ValidationError as exc:
        report.problems.extend(_model_problems(exc, str(path)))
        return
    data = b"".join(line + b"\n" for line in lines)
    if manifest.cases_sha256 != sha256_bytes(data):
        report.problems.append(f"{path}: cases_sha256 does not match {CASES_FILE}")
    if manifest.n != len(lines) or len(manifest.cases) != len(lines):
        report.problems.append(
            f"{path}: lists {len(manifest.cases)} of n={manifest.n} cases, the file has {len(lines)}"
        )
    expected_seeds = list(range(manifest.seed_start, manifest.seed_start + manifest.n))
    if [entry.seed for entry in manifest.cases] != expected_seeds:
        report.problems.append(f"{path}: seeds are not {manifest.seed_start}..{manifest.seed_start + manifest.n - 1}")
    for entry, line, sample in zip(manifest.cases, lines, samples, strict=False):
        if entry.sha256 != sha256_bytes(line) or entry.case_id != sample.case.case_id:
            report.problems.append(f"{path}: entry {entry.case_id} does not match the case in {CASES_FILE}")
        target = TargetEntry(ddx=sample.target.ddx, red_flag=sample.target.red_flag)
        if entry.target != target or entry.relabeled != sample.relabeled:
            report.problems.append(f"{path}: target or relabeling of {entry.case_id} differs from the sampler")
    if len(samples) == len(lines) and manifest.summary != summarize(samples):
        report.problems.append(f"{path}: summary differs from the cases")
    try:
        sampler = load_sampler(manifest.domain, root)
    except (loader.LoadError, SamplerError):
        return  # reported for the cases already
    current = input_hashes(sampler, root)
    for name, value in manifest.inputs.model_dump().items():
        if getattr(current, name) != value:
            report.problems.append(f"{path}: input {name} changed since the collection was built")
    if tuple(manifest.plan) != tuple(sampler.spec.plan):
        report.problems.append(f"{path}: plan differs from {SAMPLER_FILE}")  # pragma: no cover - sampler hash differs


def validate(path: Path, root: Path = loader.PACKS_ROOT) -> Report:
    """Check a collection directory (or a JSONL file) completely; see the module docstring."""
    cases_path, manifest_path = _resolve(path)
    report = Report(path=path)
    if not cases_path.is_file():
        report.problems.append(f"{cases_path}: file is missing")
        return report
    problems: list[str] = []
    parsed = read_cases(cases_path, problems)
    report.problems.extend(problems)
    seen: set[str] = set()
    samplers: dict[str, Sampler | None] = {}
    samples: list[Sample] = []
    previous = -1
    for line, case in parsed:
        if case.case_id in seen:
            report.problems.append(f"{case.case_id}: appears twice")
        seen.add(case.case_id)
        if case.seed <= previous:
            report.problems.append(f"{case.case_id}: cases must be ordered by ascending seed")
        previous = case.seed
        sample = _check_case(line, case, samplers, root, report)
        if sample is not None:
            samples.append(sample)
    report.cases = len(parsed)
    report.relabeled = sum(sample.relabeled for sample in samples)
    if manifest_path is not None and not problems:
        _check_manifest(manifest_path, report, [line for line, _ in parsed], samples, root)
    return report


def counts_line(counts: Mapping[str, int]) -> str:
    """``answer 42, refer_urgent 58``."""
    return ", ".join(f"{key} {value}" for key, value in counts.items()) or "-"


def pairs_line(pairs: Sequence[tuple[int, int]]) -> str:
    """``1: 2 cases, 2: 8 cases``."""
    return ", ".join(f"{number}: {cases}" for number, cases in pairs) or "-"
