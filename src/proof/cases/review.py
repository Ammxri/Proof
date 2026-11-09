"""Physician review per language (PR-A02, PR-A06, PR-F05, A-23): sample, review packet and check of the record.

A review record ``review/<lang>.yaml`` lists one or more reviews of that language. Each review names the reviewer,
the role (``physician`` or ``pre_reviewer``), the clinical practice and its country, the date, the scope, the hashes
of the templates and labels reviewed (:func:`proof.render.templating.template_hashes`) and, for a collection, the
reviewed case ids. Missing information stays a clearly marked placeholder ``<PLATZHALTER: …>`` until it is delivered.

:func:`verify` accepts a record only if a physician (for zh with clinical practice in China) reviewed exactly the
current templates and, when a collection is named, every case of its sample. A pre-review is recorded but never
replaces the physician review (PR-A02).

:func:`sample` draws the cases a reviewer checks: at least 10 % of the collection, at least one case per target of the
plan, deterministic for a collection and language (A-71).
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictStr, StringConstraints, ValidationError, model_validator

from proof.cases import collection as collections
from proof.cases.model import CASE_ID_PATTERN, Case
from proof.core import disclaimer, i18n, yamlio
from proof.core.rng import Stream
from proof.render import templating
from proof.render.case_text import render_case
from proof.render.prompt import system_prompt
from proof_rules import loader
from proof_rules.model import Domain, Text

PLACEHOLDER = re.compile(r"<PLATZHALTER[^>]*>")
SAMPLE_PERCENT = 10
CHINA = "CN"
Sha256 = Annotated[StrictStr, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Language = Literal["zh", "en", "de"]


class ReviewError(Exception):
    """A packet or sample cannot be produced; ``problems`` lists every finding."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


# --- Record ----------------------------------------------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Review(_Model):
    """One review of one language."""

    name: Text
    role: Literal["physician", "pre_reviewer"]
    clinical_practice: Text
    clinical_practice_country: Annotated[StrictStr, StringConstraints(pattern=r"^[A-Z]{2}$")]
    date: dt.date
    scope: Text
    templates: Annotated[dict[StrictStr, Sha256], Field(min_length=1)]
    collection: StrictStr | None = None
    collection_sha256: Sha256 | None = None
    cases: tuple[Annotated[StrictStr, StringConstraints(pattern=CASE_ID_PATTERN)], ...] = ()

    @model_validator(mode="after")
    def _collection(self) -> Review:
        if (self.collection is None) != (self.collection_sha256 is None):
            raise ValueError("collection and collection_sha256 go together")
        if self.cases and self.collection is None:
            raise ValueError("reviewed cases need the collection they belong to")
        return self


class ReviewRecord(_Model):
    """``review/<lang>.yaml``."""

    language: Language
    reviews: Annotated[tuple[Review, ...], Field(min_length=1)]


def placeholders(data: Any, path: str = "") -> list[str]:
    """Every placeholder in a loaded YAML document, as ``path: placeholder``."""
    found = []
    if isinstance(data, str):
        found.extend(f"{path or '<root>'}: {match}" for match in PLACEHOLDER.findall(data))
    elif isinstance(data, Mapping):
        for key, value in data.items():
            found.extend(placeholders(value, f"{path}.{key}" if path else str(key)))
    elif isinstance(data, list | tuple):
        for index, value in enumerate(data):
            found.extend(placeholders(value, f"{path}[{index}]"))
    return found


# --- Sample ----------------------------------------------------------------------------------------------------------


def sample_size(cases: int) -> int:
    """At least 10 % of the cases, rounded up, and at least one (PR-A02)."""
    return max(1, -(-cases * SAMPLE_PERCENT // 100))


def sample(manifest: collections.CollectionManifest, lang: str) -> tuple[str, ...]:
    """The case ids a reviewer of ``lang`` checks, ordered by seed (A-71).

    The cases are shuffled with a stream of the collection's name, content hash and the language. The first case of
    each target in that order is taken first, then further cases in that order until the sample is full.
    """
    templating.check_language(lang)
    size = sample_size(len(manifest.cases))
    stream = Stream("review-sample", manifest.name, manifest.cases_sha256, lang)
    shuffled = stream.shuffled(list(manifest.cases))
    chosen: list[collections.CaseEntry] = []
    targets: set[tuple[str, str]] = set()
    for entry in shuffled:
        target = (entry.target.ddx, entry.target.red_flag)
        if len(chosen) < size and target not in targets:
            chosen.append(entry)
            targets.add(target)
    for entry in shuffled:
        if len(chosen) >= size:
            break
        if entry not in chosen:
            chosen.append(entry)
    return tuple(entry.case_id for entry in sorted(chosen, key=lambda entry: entry.seed))


# --- Current hashes --------------------------------------------------------------------------------------------------


@cache
def _domains(root: str) -> tuple[Domain, ...]:
    path = Path(root)
    return tuple(loader.load_domain(name, path) for name in loader.domains(path))


def all_domains(root: Path = loader.PACKS_ROOT) -> tuple[Domain, ...]:
    """Every domain pack of ``root``, loaded once per process (a review runs on fixed packs)."""
    return _domains(str(root.resolve()))


def domain_named(name: str, root: Path = loader.PACKS_ROOT) -> Domain:
    for domain in all_domains(root):
        if domain.name == name:
            return domain
    raise ReviewError([f"no domain pack {name!r} in {root}"])


def current_hashes(lang: str, root: Path = loader.PACKS_ROOT) -> dict[str, str]:
    """Hashes of the templates of ``lang`` and the labels of every domain in that language."""
    return templating.template_hashes(lang, all_domains(root))


# --- Verification ----------------------------------------------------------------------------------------------------


@dataclass
class VerifyReport:
    path: Path
    lang: str
    problems: list[str] = field(default_factory=list)
    physicians: int = 0
    pre_reviewers: int = 0

    @property
    def ok(self) -> bool:
        return not self.problems


def _hash_differences(recorded: Mapping[str, str], current: Mapping[str, str]) -> list[str]:
    differences = []
    for name in sorted(set(recorded) | set(current)):
        if name not in recorded:
            differences.append(f"{name} is not covered")
        elif name not in current:
            differences.append(f"{name} no longer exists")
        elif recorded[name] != current[name]:
            differences.append(f"{name} changed since the review")
    return differences


def verify(
    path: Path,
    lang: str,
    *,
    collection_dir: Path | None = None,
    root: Path = loader.PACKS_ROOT,
    today: dt.date | None = None,
) -> VerifyReport:
    """Check the review record of ``lang``; see the module docstring for the conditions."""
    templating.check_language(lang)
    report = VerifyReport(path=path, lang=lang)
    if not path.is_file():
        report.problems.append(f"{path}: no review record for {lang} (PR-A02)")
        return report
    try:
        data = yamlio.load_file(path)
    except yamlio.YamlError as exc:
        report.problems.append(str(exc))
        return report
    found = placeholders(data)
    if found:
        report.problems.extend(f"{path}: placeholder not filled in: {item}" for item in found)
        return report
    try:
        record = ReviewRecord.model_validate(data)
    except ValidationError as exc:
        for error in exc.errors(include_url=False):
            location = ".".join(str(part) for part in error["loc"])
            report.problems.append(f"{path}: {location}: {error['msg'].removeprefix('Value error, ')}")
        return report
    if record.language != lang:
        report.problems.append(f"{path}: the record is for {record.language}, not {lang}")
    report.physicians = sum(review.role == "physician" for review in record.reviews)
    report.pre_reviewers = sum(review.role == "pre_reviewer" for review in record.reviews)
    today = today or dt.date.today()
    for index, review in enumerate(record.reviews):
        if review.date > today:
            report.problems.append(f"{path}: reviews[{index}].date {review.date} lies in the future")
    eligible = [review for review in record.reviews if review.role == "physician"]
    if not eligible:
        report.problems.append(f"{path}: only pre-reviews; a pre-review does not replace the physician review (PR-A02)")
        return report
    if lang == "zh":
        eligible = [review for review in eligible if review.clinical_practice_country == CHINA]
        if not eligible:
            report.problems.append(f"{path}: zh needs a physician with clinical practice in China (PR-A02)")
            return report
    current = current_hashes(lang, root)
    if not any(dict(review.templates) == current for review in eligible):
        latest = max(eligible, key=lambda review: review.date)
        report.problems.extend(
            f"{path}: {difference} (PR-A06)" for difference in _hash_differences(latest.templates, current)
        )
    if collection_dir is not None:
        _verify_cases(path, collection_dir, eligible, lang, report)
    return report


def _eligible(reviews: Iterable[Review], lang: str) -> list[Review]:
    """Reviews that count as the physician review of ``lang`` (for zh with clinical practice in China)."""
    return [
        review
        for review in reviews
        if review.role == "physician" and (lang != "zh" or review.clinical_practice_country == CHINA)
    ]


def _of_collection(reviews: Iterable[Review], manifest: collections.CollectionManifest) -> list[Review]:
    return [
        review
        for review in reviews
        if review.collection == manifest.name and review.collection_sha256 == manifest.cases_sha256
    ]


@dataclass(frozen=True)
class LanguageStatus:
    """Review state of one language for a dataset card or release (PR-A02, PR-A06).

    ``problems`` is empty exactly when the review is valid; the sample counts only when ``cases_required``.
    ``reviews`` holds the entries of the record once it is complete and well-formed.
    """

    lang: str
    path: Path
    problems: tuple[str, ...]
    reviews: tuple[Review, ...]
    placeholders: int
    sample: tuple[str, ...]
    covered: tuple[str, ...]
    cases_required: bool

    @property
    def ok(self) -> bool:
        return not self.problems


def language_status(
    path: Path,
    lang: str,
    collection_dir: Path,
    *,
    cases_required: bool,
    root: Path = loader.PACKS_ROOT,
    today: dt.date | None = None,
) -> LanguageStatus:
    """Check the record of ``lang`` as :func:`verify` does and collect what a dataset card shows about it.

    ``covered`` lists the sample cases of the collection that a counting physician review of this version of the
    collection checked; the sample is required for validity only when ``cases_required``.
    """
    manifest = read_manifest(collection_dir)
    report = verify(path, lang, collection_dir=collection_dir if cases_required else None, root=root, today=today)
    reviews: tuple[Review, ...] = ()
    found = 0
    if path.is_file():
        try:
            data = yamlio.load_file(path)
        except yamlio.YamlError:
            data = None
        found = len(placeholders(data))
        if data is not None and not found:
            try:
                reviews = ReviewRecord.model_validate(data).reviews
            except ValidationError:
                reviews = ()
    chosen = sample(manifest, lang)
    checked = {case_id for review in _of_collection(_eligible(reviews, lang), manifest) for case_id in review.cases}
    return LanguageStatus(
        lang=lang,
        path=path,
        problems=tuple(report.problems),
        reviews=reviews,
        placeholders=found,
        sample=chosen,
        covered=tuple(case_id for case_id in chosen if case_id in checked),
        cases_required=cases_required,
    )


def _verify_cases(path: Path, directory: Path, eligible: Sequence[Review], lang: str, report: VerifyReport) -> None:
    manifest = read_manifest(directory)
    reviews = _of_collection(eligible, manifest)
    if not reviews:
        report.problems.append(f"{path}: no physician review of collection {manifest.name} in its current form")
        return
    covered = {case_id for review in reviews for case_id in review.cases}
    missing = [case_id for case_id in sample(manifest, lang) if case_id not in covered]
    if missing:
        report.problems.append(f"{path}: sample cases not reviewed: {', '.join(missing)}")


# --- Packet ----------------------------------------------------------------------------------------------------------


def read_manifest(directory: Path) -> collections.CollectionManifest:
    path = directory / collections.MANIFEST_FILE
    if not path.is_file():
        raise ReviewError([f"{path}: file is missing"])
    try:
        return collections.CollectionManifest.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise ReviewError([f"{path}: {exc}"]) from exc


def _read_collection(directory: Path) -> tuple[collections.CollectionManifest, dict[str, Case]]:
    manifest = read_manifest(directory)
    problems: list[str] = []
    cases = {case.case_id: case for _, case in collections.read_cases(directory / collections.CASES_FILE, problems)}
    if problems:
        raise ReviewError(problems)
    return manifest, cases


def record_template(lang: str, manifest: collections.CollectionManifest, root: Path = loader.PACKS_ROOT) -> str:
    """Text of a review record for ``lang`` with the current hashes and the sample; personal data as placeholders."""
    data = {
        "language": lang,
        "reviews": [
            {
                "name": "<PLATZHALTER: Name der Ärztin oder des Arztes>",
                "role": "physician",
                "clinical_practice": "<PLATZHALTER: Klinik oder Praxis>",
                "clinical_practice_country": "<PLATZHALTER: Ländercode nach ISO 3166-1, für zh CN>",
                "date": "<PLATZHALTER: Datum der Prüfung, JJJJ-MM-TT>",
                "scope": "<PLATZHALTER: Umfang der Prüfung>",
                "templates": current_hashes(lang, root),
                "collection": manifest.name,
                "collection_sha256": manifest.cases_sha256,
                "cases": list(sample(manifest, lang)),
            }
        ],
    }
    comment = (
        f"Physician review record for {lang} (PR-A02, A-23). Replace every placeholder; a pre-review gets its own\n"
        "entry with role pre_reviewer. Generated by 'proof review packet'; check it with 'proof review verify'."
    )
    return yamlio.dump_text(data, comment=comment)


def _labelled(codes: Sequence[str], names: Mapping[str, str], none: str) -> str:
    return ", ".join(f"`{code}` ({names[code]})" for code in codes) or none


def packet_text(lang: str, manifest: collections.CollectionManifest, cases: Mapping[str, Case], root: Path) -> str:
    """The Markdown document of a review packet in the reviewer's language."""
    t = i18n.table(lang)
    domain = domain_named(manifest.domain, root)
    labels = templating.labels(domain, lang)
    field_names = {code: item["name"] for code, item in labels["fields"].items()}
    targets = {entry.case_id: entry.target for entry in manifest.cases}
    lines = [f"# {t['review.title']} ({lang})", "", *(f"> {line}" for line in disclaimer.lines(lang)), ""]
    lines += [t["review.intro"].format(collection=manifest.name), "", f"## 1 {t['review.templates_heading']}", ""]
    lines += [t["review.templates_task"], "", "| Name | SHA-256 |", "|---|---|"]
    lines += [f"| `{name}` | `{digest}` |" for name, digest in current_hashes(lang, root).items()]
    lines += ["", f"### {t['review.prompt_heading']}", "", "```text", system_prompt(domain, lang).rstrip("\n"), "```"]
    lines += ["", f"## 2 {t['review.cases_heading']}", "", t["review.cases_task"], ""]
    for case_id in sample(manifest, lang):
        case = cases[case_id]
        key = case.key
        target = targets[case_id]
        lines += [f"### {case_id}", "", "```text", render_case(case, domain, lang).text.rstrip("\n"), "```", ""]
        lines += [
            f"- {t['review.target']}: `{target.ddx}` ({labels['ddx'][target.ddx]}), {t['review.red_flag']} "
            f"`{target.red_flag}`",
            f"- {t['review.determinability']}: `{key.determinability}`",
            f"- {t['review.red_flags']}: {_labelled(key.red_flags, labels['red_flags'], t['review.none'])}",
            f"- {t['review.ddx']}: {_labelled(key.ddx, labels['ddx'], t['review.none'])}",
            f"- {t['review.critical_fields']}: {_labelled(key.critical_fields, field_names, t['review.none'])}",
            "",
        ]
    lines += [f"## 3 {t['review.record_heading']}", "", t["review.record_task"].format(lang=lang), ""]
    return "\n".join(lines)


def packet(lang: str, directory: Path, out: Path, root: Path = loader.PACKS_ROOT) -> list[Path]:
    """Write the review packet of ``lang`` for a collection into ``out``; returns the written files."""
    templating.check_language(lang)
    manifest, cases = _read_collection(directory)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    document = out / f"packet_{lang}.md"
    document.write_bytes(packet_text(lang, manifest, cases, root).encode("utf-8"))
    written.append(document)
    record = out / f"review_{lang}.yaml"
    record.write_bytes(record_template(lang, manifest, root).encode("utf-8"))
    written.append(record)
    for name in templating.TEMPLATE_FILES:
        target = out / "templates" / lang / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(templating.template_bytes(lang, name))
        written.append(target)
    domain = domain_named(manifest.domain, root)
    labels_path = out / f"labels_{domain.name}_{lang}.json"
    labels_path.write_bytes(templating.canonical_labels(domain, lang) + b"\n")
    written.append(labels_path)
    return written
