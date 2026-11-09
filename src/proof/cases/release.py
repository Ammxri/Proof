"""Release package of a collection (PR-F10, PR-A02, PR-A06, PR-C01, PR-D04, UF-04, A-27, A-41).

A package is one directory with the dataset card (``README.md`` with Hugging Face metadata), the cases, the variant
sets, the renderings of every case and variant in zh, en and de, the system prompts, the JSON Schemas, the rule packs
with their documentation, the review records, the licences, ``release.json`` with the provenance and ``SHA256SUMS``.

A release is refused unless every check holds (:func:`prepare`):

- the collection and every variant set validate (schema, keys recomputed, rebuilt from their seeds);
- each language has a valid physician review of the current templates (for zh with clinical practice in China),
  from version 0.5 on also of the sample of the collection's cases;
- ``data/card.yaml`` has no placeholder, and the repository is a git work tree without uncommitted changes;
- the card holds every required part and the package no placeholder.

``draft=True`` builds a draft package instead (A-41): the review, placeholder and git checks are reported in the card
and in ``release.json`` but do not stop it, and directory name and card are marked as draft. A draft is not a release
and is not meant for upload.
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

import proof
import proof_rules
from proof.cases import collection as collections
from proof.cases import review
from proof.cases.model import Case, case_json_schema, schema_text
from proof.cases.profiles import LabProfile
from proof.cases.sampler import SamplerError, SamplerSpec, load_sampler
from proof.core import canonical, i18n
from proof.core.hashing import sha256_bytes
from proof.core.manifest import GitState, ManifestBase, git_state, new_manifest
from proof.render.case_text import render_case
from proof.render.prompt import system_prompt
from proof.report import card
from proof.scoring.response import response_json_schema
from proof.variants import sets as variant_sets
from proof.variants.model import LanguagePair, Variant, variant_json_schema
from proof.variants.render import render_variant
from proof_rules import loader
from proof_rules.model import Domain

CARD_FILE = "README.md"
MANIFEST_FILE = "release.json"
SUMS_FILE = "SHA256SUMS"
CARD_INPUTS = Path("data") / "card.yaml"
REVIEW_DIR = Path("review")
DRAFT_SUFFIX = "-DRAFT"
DATA_DIR = "data"
CASES_REQUIRED_FROM = (0, 5)
# Package path -> file of the repository it is copied from.
REPOSITORY_FILES: dict[str, Path] = {
    "LICENSE": Path("LICENSE-DATA"),
    "LICENSE-CODE": Path("LICENSE"),
    "NOTICE": Path("NOTICE"),
    "rules/RULES.md": Path("docs") / "regeln.md",
}
SCHEMAS = {
    "schema/case.schema.json": case_json_schema,
    "schema/variant.schema.json": variant_json_schema,
    "schema/response.schema.json": response_json_schema,
}
_SKIPPED_PARTS = {"__pycache__"}
_VERSION = re.compile(r"^(\d+)\.(\d+)")


class ReleaseError(Exception):
    """The package cannot be built; ``problems`` lists every finding."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


# --- Manifest --------------------------------------------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CollectionRef(_Model):
    name: str
    cases_sha256: str


class VariantSetRef(_Model):
    variant_seed: int
    variants_sha256: str


class ReviewState(_Model):
    valid: bool
    physicians: int
    pre_reviewers: int
    sample: tuple[str, ...]
    covered: tuple[str, ...]
    problems: tuple[str, ...]


class ReleaseManifest(ManifestBase):
    """``release.json``."""

    kind: str = "release"
    package: str
    draft: bool
    cases_review_required: bool
    collection: CollectionRef
    variant_sets: tuple[VariantSetRef, ...]
    templates: dict[str, dict[str, str]]
    reviews: dict[str, ReviewState]
    problems: tuple[str, ...]


# --- Inputs ----------------------------------------------------------------------------------------------------------


def cases_required(version: str) -> bool:
    """Whether a release of ``version`` needs the physician review of the case sample (PR-A02: from 0.5)."""
    match = _VERSION.match(version)
    if match is None:
        raise ReleaseError([f"cannot read the version {version!r}"])
    return (int(match.group(1)), int(match.group(2))) >= CASES_REQUIRED_FROM


def package_name(collection_name: str, version: str, *, draft: bool) -> str:
    """``proof-<collection>-<version>``, with ``-DRAFT`` for a draft (A-41)."""
    return f"proof-{collection_name}-{version}" + (DRAFT_SUFFIX if draft else "")


@dataclass(frozen=True)
class VariantSet:
    directory: Path
    manifest: variant_sets.VariantSetManifest
    variants: tuple[Variant, ...]


@dataclass(frozen=True)
class Prepared:
    """Everything a package is built from, checked by :func:`prepare`."""

    repo: Path
    root: Path
    collection_dir: Path
    manifest: collections.CollectionManifest
    cases: tuple[Case, ...]
    variant_sets: tuple[VariantSet, ...]
    domain: Domain
    sampler: SamplerSpec
    profiles: tuple[LabProfile, ...]
    packs: tuple[str, ...]
    reviews: Mapping[str, review.LanguageStatus]
    inputs: card.CardInputs
    git: GitState | None
    version: str
    draft: bool
    problems: tuple[str, ...]
    """Findings that a draft records instead of stopping on them."""


def variant_set_dirs(collection_dir: Path) -> list[Path]:
    """The variant sets of a collection, ordered by variant seed."""
    base = collection_dir / variant_sets.VARIANTS_DIR
    if not base.is_dir():
        return []
    found = [path for path in base.iterdir() if path.is_dir() and path.name.isdigit()]
    return sorted(found, key=lambda path: int(path.name))


def _packs(domain_name: str, root: Path) -> tuple[str, ...]:
    config = loader.read_pack(root / domain_name).config
    uses = config.domain.uses if config.domain is not None else ()
    return (domain_name, *uses)


def prepare(
    collection_dir: Path,
    *,
    repo: Path,
    root: Path = loader.PACKS_ROOT,
    draft: bool = False,
    version: str = proof.__version__,
    today: dt.date | None = None,
) -> Prepared:
    """Read and check everything a package needs; raises :class:`ReleaseError` with every problem that stops it."""
    stop: list[str] = []
    report = collections.validate(collection_dir, root)
    stop += report.problems
    manifest_path = collection_dir / collections.MANIFEST_FILE
    if not manifest_path.is_file():
        stop.append(f"{manifest_path}: file is missing")
    sets = []
    for directory in variant_set_dirs(collection_dir):
        set_report = variant_sets.validate(directory, collection_dir, root)
        stop += set_report.problems
        if not set_report.problems:
            problems: list[str] = []
            variants = tuple(
                variant for _, variant in variant_sets.read_variants(directory / variant_sets.VARIANTS_FILE, problems)
            )
            set_manifest = variant_sets.VariantSetManifest.model_validate(
                canonical.loads((directory / variant_sets.MANIFEST_FILE).read_bytes())
            )
            sets.append(VariantSet(directory=directory, manifest=set_manifest, variants=variants))
    for target, source in REPOSITORY_FILES.items():
        if not (repo / source).is_file():
            stop.append(f"{repo / source}: file is missing (packaged as {target})")
    recorded: list[str] = []
    try:
        inputs, found = card.read_inputs(repo / CARD_INPUTS)
    except card.CardError as exc:
        raise ReleaseError([*stop, *exc.problems]) from exc
    recorded += [f"placeholder not filled in: {item}" for item in found]
    if stop:
        raise ReleaseError(stop)
    manifest = review.read_manifest(collection_dir)
    parsed: list[str] = []
    cases = tuple(case for _, case in collections.read_cases(collection_dir / collections.CASES_FILE, parsed))
    try:
        sampler = load_sampler(manifest.domain, root)
    except (loader.LoadError, SamplerError) as exc:  # pragma: no cover - the collection validated with this sampler
        raise ReleaseError(exc.problems) from exc
    required = cases_required(version)
    statuses = {
        lang: review.language_status(
            repo / REVIEW_DIR / f"{lang}.yaml",
            lang,
            collection_dir,
            cases_required=required,
            root=root,
            today=today,
        )
        for lang in i18n.LANGUAGES
    }
    for status in statuses.values():
        recorded += status.problems
    git = git_state(repo)
    if git is None:
        recorded.append(f"{repo}: not a git work tree; a release needs a committed state")
    elif git.dirty:
        recorded.append(f"{repo}: the work tree has uncommitted changes; commit them before a release")
    if recorded and not draft:
        raise ReleaseError(recorded)
    return Prepared(
        repo=repo,
        root=root,
        collection_dir=collection_dir,
        manifest=manifest,
        cases=cases,
        variant_sets=tuple(sets),
        domain=sampler.domain,
        sampler=sampler.spec,
        profiles=tuple(profile for _, profile in sorted(sampler.lab_profiles.items())),
        packs=_packs(manifest.domain, root),
        reviews=statuses,
        inputs=inputs,
        git=git,
        version=version,
        draft=draft,
        problems=tuple(recorded),
    )


# --- Contents --------------------------------------------------------------------------------------------------------


def _renderings(prepared: Prepared, lang: str) -> bytes:
    """One line per case and per variant with a text of its own, in collection order (A-46)."""
    by_case: dict[str, list[Variant]] = {}
    for item in prepared.variant_sets:
        for variant in item.variants:
            if not isinstance(variant.change, LanguagePair):
                by_case.setdefault(variant.case_id, []).append(variant)
    records = []
    for case in prepared.cases:
        records.append(
            {
                "case_id": case.case_id,
                "item_id": case.case_id,
                "lang": lang,
                "mr": None,
                "text": render_case(case, prepared.domain, lang).text,
                "variant_seed": None,
            }
        )
        for variant in by_case.get(case.case_id, []):
            records.append(
                {
                    "case_id": case.case_id,
                    "item_id": variant.variant_id,
                    "lang": lang,
                    "mr": variant.mr,
                    "text": render_variant(variant, case, prepared.domain, lang).text,
                    "variant_seed": variant.variant_seed,
                }
            )
    return canonical.dumps_lines(records)


def _pack_files(prepared: Prepared) -> dict[str, bytes]:
    files = {}
    for name in prepared.packs:
        base = prepared.root / name
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(base)
            if path.is_file() and not _SKIPPED_PARTS.intersection(relative.parts) and path.suffix != ".pyc":
                files[f"rules/{name}/{relative.as_posix()}"] = path.read_bytes()
    return files


def _descriptions(prepared: Prepared, collection_path: str) -> tuple[tuple[str, str], ...]:
    rows = [
        (CARD_FILE, "this dataset card"),
        (f"{collection_path}/cases.jsonl", "the cases with their keys (`schema/case.schema.json`)"),
        (f"{collection_path}/collection.json", "seeds, target plan, input hashes and distribution of the cases"),
    ]
    for item in prepared.variant_sets:
        seed = item.manifest.variant_seed
        rows.append(
            (
                f"{collection_path}/variants/{seed}/",
                f"variants of seed {seed} with their expectation (`variants.jsonl`, `schema/variant.schema.json`) "
                "and their manifest (`variants.json`)",
            )
        )
    rows += [
        (f"{collection_path}/renderings/<lang>.jsonl", "the text of every case and variant in zh, en and de"),
        (f"{collection_path}/prompts/system_<lang>.txt", "the system prompt: answer format and every allowed code"),
        ("schema/", "JSON Schemas of case, variant and answer"),
        ("rules/<pack>/", "the rule packs: catalog, vocabulary, rules with test vectors, sources with their terms"),
        ("rules/RULES.md", "every rule with its condition, source and locator"),
        ("review/<lang>.yaml", "the physician review records"),
        (MANIFEST_FILE, "provenance of this package and the result of the release checks"),
        ("LICENSE", "CC BY 4.0 (cases, variants, renderings, prompts)"),
        ("LICENSE-CODE", "Apache License 2.0 (rule packs, schemas, rule documentation)"),
        ("NOTICE", "copyright and licence notice"),
        (SUMS_FILE, "SHA-256 of every other file"),
    ]
    return tuple(rows)


def card_context(prepared: Prepared, collection_path: str = DATA_DIR) -> card.CardContext:
    return card.CardContext(
        collection=prepared.manifest,
        collection_path=collection_path,
        variant_sets=tuple(
            card.VariantSetInfo(path=f"{collection_path}/variants/{item.manifest.variant_seed}", manifest=item.manifest)
            for item in prepared.variant_sets
        ),
        domain=prepared.domain,
        sampler=prepared.sampler,
        profiles=prepared.profiles,
        packs=prepared.packs,
        reviews=prepared.reviews,
        inputs=prepared.inputs,
        files=_descriptions(prepared, collection_path),
        renderings={lang: f"{collection_path}/renderings/{lang}.jsonl" for lang in i18n.LANGUAGES},
        proof_version=proof.__version__,
        rules_version=proof_rules.__version__,
        git=prepared.git,
        draft=prepared.draft,
    )


def card_text(prepared: Prepared) -> str:
    """The dataset card of the package."""
    return card.render(card_context(prepared))


def _manifest(prepared: Prepared, name: str) -> ReleaseManifest:
    base = new_manifest("release")
    return ReleaseManifest(
        **{**base.model_dump(), "kind": "release", "git": prepared.git},
        package=name,
        draft=prepared.draft,
        cases_review_required=cases_required(prepared.version),
        collection=CollectionRef(name=prepared.manifest.name, cases_sha256=prepared.manifest.cases_sha256),
        variant_sets=tuple(
            VariantSetRef(variant_seed=item.manifest.variant_seed, variants_sha256=item.manifest.variants_sha256)
            for item in prepared.variant_sets
        ),
        templates={lang: review.current_hashes(lang, prepared.root) for lang in i18n.LANGUAGES},
        reviews={
            lang: ReviewState(
                valid=status.ok,
                physicians=sum(item.role == "physician" for item in status.reviews),
                pre_reviewers=sum(item.role == "pre_reviewer" for item in status.reviews),
                sample=status.sample,
                covered=status.covered,
                problems=status.problems,
            )
            for lang, status in prepared.reviews.items()
        },
        problems=prepared.problems,
    )


def contents(prepared: Prepared) -> dict[str, bytes]:
    """Every file of the package except ``SHA256SUMS``, keyed by its path in the package."""
    name = package_name(prepared.manifest.name, prepared.version, draft=prepared.draft)
    files: dict[str, bytes] = {}
    files[CARD_FILE] = card_text(prepared).encode("utf-8")
    for target, source in REPOSITORY_FILES.items():
        files[target] = (prepared.repo / source).read_bytes()
    for target, schema in SCHEMAS.items():
        files[target] = schema_text(schema()).encode("utf-8")
    source_dir = prepared.collection_dir
    files[f"{DATA_DIR}/cases.jsonl"] = (source_dir / collections.CASES_FILE).read_bytes()
    files[f"{DATA_DIR}/collection.json"] = (source_dir / collections.MANIFEST_FILE).read_bytes()
    for item in prepared.variant_sets:
        seed = item.manifest.variant_seed
        for file_name in (variant_sets.VARIANTS_FILE, variant_sets.MANIFEST_FILE):
            files[f"{DATA_DIR}/variants/{seed}/{file_name}"] = (item.directory / file_name).read_bytes()
    for lang in i18n.LANGUAGES:
        files[f"{DATA_DIR}/renderings/{lang}.jsonl"] = _renderings(prepared, lang)
        files[f"{DATA_DIR}/prompts/system_{lang}.txt"] = system_prompt(prepared.domain, lang).encode("utf-8")
        record = prepared.repo / REVIEW_DIR / f"{lang}.yaml"
        if record.is_file():
            files[f"review/{lang}.yaml"] = record.read_bytes()
    files.update(_pack_files(prepared))
    files[MANIFEST_FILE] = _manifest(prepared, name).to_canonical_json() + b"\n"
    return dict(sorted(files.items()))


def sums_text(files: Mapping[str, bytes]) -> str:
    """``SHA256SUMS`` in the format of ``sha256sum``: hash, two spaces, path with forward slashes."""
    return "".join(f"{sha256_bytes(data)}  {path}\n" for path, data in sorted(files.items()))


def check_package(directory: Path, *, draft: bool) -> list[str]:
    """Check a written package: ``SHA256SUMS`` lists every other file once with its hash; the card is complete.

    A release (``draft=False``) must hold no placeholder in any text file.
    """
    problems: list[str] = []
    sums = directory / SUMS_FILE
    if not sums.is_file():
        return [f"{sums}: file is missing"]
    listed: dict[str, str] = {}
    for number, line in enumerate(sums.read_bytes().decode("utf-8").splitlines(), start=1):
        digest, separator, path = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest) or not path:
            problems.append(f"{SUMS_FILE} line {number}: not '<sha256>  <path>'")
            continue
        if path in listed:
            problems.append(f"{SUMS_FILE}: {path} is listed twice")
        listed[path] = digest
    present = {path.relative_to(directory).as_posix(): path for path in directory.rglob("*") if path.is_file()}
    present.pop(SUMS_FILE, None)
    for path in sorted(set(present) - set(listed)):
        problems.append(f"{SUMS_FILE}: {path} is not listed")
    for path in sorted(set(listed) - set(present)):
        problems.append(f"{SUMS_FILE}: {path} is listed but missing")
    for path in sorted(set(listed) & set(present)):
        if sha256_bytes(present[path].read_bytes()) != listed[path]:
            problems.append(f"{SUMS_FILE}: {path} does not match its hash")
    card_path = directory / CARD_FILE
    if card_path.is_file():
        problems += [
            f"{CARD_FILE}: {problem}" for problem in card.missing_parts(card_path.read_text("utf-8"), draft=draft)
        ]
    else:
        problems.append(f"{card_path}: file is missing")
    if not draft:
        for path, file in sorted(present.items()):
            if file.suffix in {".md", ".yaml", ".json", ".jsonl", ".txt"} or file.name in REPOSITORY_FILES:
                for item in review.PLACEHOLDER.findall(file.read_bytes().decode("utf-8")):
                    problems.append(f"{path}: placeholder {item}")
    return problems


def write(prepared: Prepared, out: Path) -> Path:
    """Write the package into ``out/<package name>``; refuses an existing directory and checks what it wrote."""
    name = package_name(prepared.manifest.name, prepared.version, draft=prepared.draft)
    target = out / name
    if target.exists():
        raise ReleaseError([f"{target}: already exists; choose another --out or remove it"])
    files = contents(prepared)
    staging = out / f".{name}.partial"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        for path, data in files.items():
            destination = staging / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (staging / SUMS_FILE).write_bytes(sums_text(files).encode("utf-8"))
        problems = check_package(staging, draft=prepared.draft)
        if problems:
            raise ReleaseError(problems)
        staging.rename(target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target
