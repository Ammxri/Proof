"""Dataset card of a release package (PR-F10, PR-A01, PR-A02, PR-C01, PR-D03, A-24, A-27).

The card is the package's ``README.md`` with Hugging Face metadata in its front matter. It states where the cases come
from, how the keys are computed and from which rules, who reviewed which language, the limits of the reference and the
licences, and it carries the fixed notices in zh, en and de. Everything it says is read from the collection, its
variant sets, the rule packs, the review records and ``data/card.yaml``; :func:`missing_parts` checks a card text for
every required part.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StrictStr, StringConstraints, ValidationError

from proof.cases import review as reviews
from proof.cases.collection import CollectionManifest
from proof.cases.profiles import LabProfile
from proof.cases.sampler import RangeBackground, SamplerSpec
from proof.core import disclaimer, i18n, yamlio
from proof.core.manifest import GitState
from proof.render import templating
from proof.variants.sets import VariantSetManifest
from proof_rules.model import Domain

REPOSITORY_URL = "https://github.com/Ammxri/Proof"
SPLIT = "test"
SECTIONS: tuple[str, ...] = (
    "Notices",
    "Dataset summary",
    "Provenance",
    "Rules and keys",
    "Physician review",
    "Limitations",
    "Licence",
    "Files",
    "Contact",
)
METADATA_KEYS: tuple[str, ...] = (
    "pretty_name",
    "license",
    "language",
    "language_details",
    "annotations_creators",
    "language_creators",
    "source_datasets",
    "size_categories",
    "tags",
    "configs",
)
LANGUAGE_TAGS = {"zh": "zh-Hans", "en": "en", "de": "de"}
DRAFT_KEY = "release.draft"
LANGUAGE_NAMES = {"zh": "Chinese (simplified, zh-Hans)", "en": "English", "de": "German"}


class CardError(Exception):
    """The card inputs cannot be read; ``problems`` lists every finding."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


class CardInputs(BaseModel):
    """``data/card.yaml``: what the card states that no file of the repository records."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contact: Annotated[StrictStr, StringConstraints(min_length=1, strip_whitespace=True)]
    synthehr_data_licence: Annotated[StrictStr, StringConstraints(min_length=1, strip_whitespace=True)]


def read_inputs(path: Path) -> tuple[CardInputs, list[str]]:
    """The card inputs and every placeholder still in them (``path: placeholder``)."""
    if not path.is_file():
        raise CardError([f"{path}: file is missing"])
    try:
        data = yamlio.load_file(path)
    except yamlio.YamlError as exc:
        raise CardError([str(exc)]) from exc
    try:
        inputs = CardInputs.model_validate(data)
    except ValidationError as exc:
        problems = []
        for error in exc.errors(include_url=False):
            location = ".".join(str(part) for part in error["loc"])
            problems.append(f"{path}: {location}: {error['msg']}")
        raise CardError(problems) from exc
    return inputs, [f"{path}: {item}" for item in reviews.placeholders(data)]


@dataclass(frozen=True)
class VariantSetInfo:
    path: str
    manifest: VariantSetManifest


@dataclass(frozen=True)
class CardContext:
    """Everything the card states; assembled by :mod:`proof.cases.release`."""

    collection: CollectionManifest
    collection_path: str
    variant_sets: tuple[VariantSetInfo, ...]
    domain: Domain
    sampler: SamplerSpec
    profiles: tuple[LabProfile, ...]
    packs: tuple[str, ...]
    reviews: Mapping[str, reviews.LanguageStatus]
    inputs: CardInputs
    files: tuple[tuple[str, str], ...]
    renderings: Mapping[str, str]
    proof_version: str
    rules_version: str
    git: GitState | None
    draft: bool


# --- Front matter ----------------------------------------------------------------------------------------------------


def size_category(count: int) -> str:
    """Hugging Face size category of a dataset with ``count`` cases."""
    for limit, label in ((1_000, "n<1K"), (10_000, "1K<n<10K"), (100_000, "10K<n<100K"), (1_000_000, "100K<n<1M")):
        if count < limit:
            return label
    return "n>1M"


def _metadata(context: CardContext) -> dict[str, Any]:
    collection = context.collection
    configs: list[dict[str, Any]] = [
        {"config_name": "cases", "data_files": [{"split": SPLIT, "path": f"{context.collection_path}/cases.jsonl"}]}
    ]
    if context.variant_sets:
        configs.append(
            {
                "config_name": "variants",
                "data_files": [
                    {"split": SPLIT, "path": f"{item.path}/variants.jsonl"} for item in context.variant_sets
                ],
            }
        )
    for lang in i18n.LANGUAGES:
        configs.append(
            {"config_name": f"renderings_{lang}", "data_files": [{"split": SPLIT, "path": context.renderings[lang]}]}
        )
    return {
        "pretty_name": f"Proof {collection.name}",
        "license": "cc-by-4.0",
        "language": list(i18n.LANGUAGES),
        "language_details": [LANGUAGE_TAGS[lang] for lang in i18n.LANGUAGES],
        "annotations_creators": ["machine-generated"],
        "language_creators": ["machine-generated"],
        "source_datasets": ["original"],
        "size_categories": [size_category(len(collection.cases))],
        "tags": ["medical", "clinical", "evaluation", "robustness", "synthetic", collection.domain],
        "configs": configs,
    }


# --- Sections --------------------------------------------------------------------------------------------------------


def _table(header: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def _percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f} %" if whole else "n/a"


def _notices(context: CardContext) -> list[str]:
    lines = []
    if context.draft:
        lines += _quote(["**DRAFT**", *(f"**{lang}:** {i18n.text(DRAFT_KEY, lang)}" for lang in i18n.LANGUAGES)])
    lines += ["## Notices", ""]
    lines += _quote([f"**{lang}:** {_sentences(disclaimer.lines(lang), lang)}" for lang in i18n.LANGUAGES])
    return lines


def _sentences(sentences: Sequence[str], lang: str) -> str:
    """Sentences of one language as a paragraph; Chinese sentences follow each other without a space."""
    return ("" if lang == "zh" else " ").join(sentences)


def _quote(paragraphs: Sequence[str]) -> list[str]:
    lines = []
    for index, paragraph in enumerate(paragraphs):
        if index:
            lines.append(">")
        lines.append(f"> {paragraph}")
    return [*lines, ""]


def _summary(context: CardContext) -> list[str]:
    collection = context.collection
    summary = collection.summary
    labels = templating.labels(context.domain, "en")
    n = len(collection.cases)
    lines = ["## Dataset summary", ""]
    lines += [
        f"{collection.name} holds {n} synthetic adult patients with the presenting complaint "
        f"{labels['complaint'].lower()} (domain `{collection.domain}`). Each case is a set of coded facts (history, "
        "examination, vital signs, laboratory) with a key that an open rule set computes: the decision "
        "(`answer`, `ask` or `refer_urgent`), the red flags, the differential diagnoses as codes and the critical "
        "fields. A model under test reads the case as text in "
        + ", ".join(LANGUAGE_NAMES[lang] for lang in i18n.LANGUAGES)
        + " and answers in a fixed JSON format; Proof compares the answer with the key.",
        "",
    ]
    if context.variant_sets:
        lines += [
            "Variants change a case in one defined way and carry the expected answer or the expected invariance: "
            "MR1 removes a critical field (the model should ask for it), MR3 permutes the sections (the answer should "
            "not change), MR5 compares the answers to the same case in two languages.",
            "",
        ]
    rows: list[list[Any]] = [["cases", n]]
    for item in context.variant_sets:
        variants = item.manifest.summary.variants
        detail = ", ".join(f"{mr} {count}" for mr, count in variants.items())
        rows.append([f"variants, seed {item.manifest.variant_seed}", f"{sum(variants.values())} ({detail})"])
        rows.append(
            [f"model inputs per language, seed {item.manifest.variant_seed}", item.manifest.summary.units_per_language]
        )
    lines += [*_table(["", "count"], rows), ""]
    lines += ["Decision of the key:", ""]
    lines += _table(
        ["decision", "cases", "share"],
        [[f"`{key}`", value, _percent(value, n)] for key, value in summary.determinability.items()],
    )
    lines += ["", "Red flags in the keys:", ""]
    lines += _table(
        ["red flag", "cases"],
        [[f"`{code}` ({labels['red_flags'][code]})", value] for code, value in summary.red_flags.items()]
        or [["none", 0]],
    )
    lines += ["", "Differential diagnoses in the keys (a case can carry several):", ""]
    lines += _table(
        ["diagnosis", "cases", "share"],
        [[f"`{code}` ({labels['ddx'][code]})", value, _percent(value, n)] for code, value in summary.ddx.items()],
    )
    lines += [
        "",
        f"Patients: age {summary.age.min}–{summary.age.max}, "
        + ", ".join(f"sex {sex}: {count}" for sex, count in summary.sex.items())
        + ".",
        "",
    ]
    return lines


def _provenance(context: CardContext) -> list[str]:
    collection = context.collection
    first, last = collection.seed_start, collection.seed_start + collection.n - 1
    lines = ["## Provenance", ""]
    lines += [
        "- **Synthetic, no patient data.** Proof's sampler draws every case from its seed: "
        f"seeds {first}–{last}; the same seed gives a byte-identical case on Windows and Linux.",
        f"- **Target plan.** Seed s gets target (s - 1) mod {len(collection.plan)} of the plan "
        "(a diagnosis and whether a red flag is present); the sampler reaches the target through the rules alone. "
        f"{collection.summary.relabeled} cases did not reach their target and carry the key the rules compute.",
        "- **Generation parameters, not epidemiology.** How often a finding appears in the background and the "
        "sampling ranges are generation parameters; they say nothing about how often anything occurs in patients.",
    ]
    ranged = [
        (code, background, background.reference)
        for code, background in context.sampler.facts.items()
        if isinstance(background, RangeBackground) and background.reference is not None
    ]
    if ranged:
        lines += [
            "- **Own ranges with source.** Numeric facts without SynthEHR data use reference ranges from the cited "
            "sources (status within the range or outside it):",
            "",
        ]
        rows = []
        for code, background, reference in ranged:
            limits = _limits(reference.lower, reference.upper)
            sample = f"{background.sample.lower}–{background.sample.upper}"
            rows.append([f"`{code}`", sample, limits, f"{reference.source.ref}: {reference.source.locator}"])
        lines += ["  " + line for line in _table(["fact", "sampled", "reference", "source"], rows)]
        lines += [""]
    if context.profiles:
        lines += [
            "- **Lab values from SynthEHR profiles.** The lab values are drawn from profiles built once from SynthEHR "
            "output (read as CSV only; no SynthEHR code is part of Proof). Rows outside the physiological bounds, "
            "with another unit, without value or with another reference range were discarded:",
            "",
        ]
        rows = []
        for profile in context.profiles:
            counts = profile.counts
            rows.append(
                [
                    f"`{profile.fact_code}`",
                    profile.unit,
                    counts.rows,
                    counts.rows_used,
                    counts.rows_outside_bounds,
                    counts.rows_other_unit,
                    counts.rows_no_value,
                    counts.rows_other_reference,
                    counts.patients,
                ]
            )
        header = [
            "fact",
            "unit",
            "rows",
            "used",
            "outside bounds",
            "other unit",
            "no value",
            "other reference",
            "patients",
        ]
        lines += ["  " + line for line in _table(header, rows)]
        lines += [""]
        origins = sorted(
            {
                (p.provenance.generator, p.provenance.seed, p.provenance.csv_rows, p.provenance.csv_sha256)
                for p in context.profiles
            }
        )
        for generator, seed, rows_total, digest in origins:
            lines.append(f"  Source: {generator}, seed {seed}, {rows_total} CSV rows, SHA-256 `{digest}`.")
        lines += [""]
    lines += [
        f"- **Build.** Proof {context.proof_version}, rules {context.rules_version}; collection built at commit "
        f"`{_commit(collection.git)}`"
        + "".join(
            f", variant set {item.manifest.variant_seed} at `{_commit(item.manifest.git)}`"
            for item in context.variant_sets
        )
        + f"; this package at `{_commit(context.git)}`"
        + (" with uncommitted changes" if context.git and context.git.dirty else "")
        + f". Cases SHA-256 `{collection.cases_sha256}`; the hashes of every input are in "
        f"`{context.collection_path}/collection.json`.",
        "",
    ]
    return lines


def _limits(lower: float | None, upper: float | None) -> str:
    """A reference range with inclusive limits: ``36.0–38.0``, ``≤ 4`` or ``≥ 101``."""
    if lower is None:
        return f"≤ {upper}"
    if upper is None:
        return f"≥ {lower}"
    return f"{lower}–{upper}"


def _commit(git: GitState | None) -> str:
    return git.commit if git is not None else "unknown"


def _rules(context: CardContext) -> list[str]:
    domain = context.domain
    kinds = Counter(rule.kind for rule in domain.rules)
    statuses = Counter(rule.status for rule in domain.rules)
    cited = sorted({source.ref for rule in domain.rules for source in rule.sources})
    register = {source.id: source for source in domain.sources.sources}
    lines = ["## Rules and keys", ""]
    lines += [
        "The keys come from the rule set alone: deterministic, three-valued, and no language model is involved in "
        "keys or scoring. A field is critical when removing it changes the key (ablation). Every rule names its "
        "source with the exact location; criteria and thresholds are restated in our own words, and the terms of "
        "every source were checked before use.",
        "",
        f"The domain `{domain.name}` uses the packs {', '.join(f'`{name}`' for name in context.packs)} with "
        f"{len(domain.rules)} active rules ("
        + ", ".join(f"{kind} {count}" for kind, count in sorted(kinds.items()))
        + f") citing {len(cited)} sources. Rule status: "
        + ", ".join(f"`{status}` {count}" for status, count in sorted(statuses.items()))
        + ".",
        "",
    ]
    if statuses.get("draft_unreviewed"):
        lines += [
            "**Every rule with status `draft_unreviewed` is a draft and has not been reviewed by a physician.**",
            "",
        ]
    lines += ["Sources of the active rules:", ""]
    lines += [f"- `{ref}`: {register[ref].citation} <{register[ref].url}>" for ref in cited]
    lines += [
        "",
        "`rules/RULES.md` lists every rule with its condition, source and locator; `rules/<pack>/` holds the packs "
        "themselves, including each source's terms of use.",
        "",
    ]
    return lines


def _review_line(item: reviews.Review, collection: CollectionManifest) -> str:
    role = "physician" if item.role == "physician" else "pre-review (does not replace the physician review)"
    checked = (
        len(item.cases)
        if item.collection == collection.name and item.collection_sha256 == collection.cases_sha256
        else 0
    )
    return (
        f"- {item.name}, {role}, {item.clinical_practice} ({item.clinical_practice_country}), {item.date}: "
        f"{item.scope}; {checked} cases of this version of {collection.name}."
    )


def _review(context: CardContext) -> list[str]:
    collection = context.collection
    lines = ["## Physician review", ""]
    lines += [
        "Each language needs a physician review of its templates and labels and of a sample of at least 10 % of the "
        "cases (at least one per target), for zh by a physician with clinical practice in China. A pre-review by a "
        "medical student is recorded but does not replace it. The records are in `review/`.",
        "",
    ]
    required = any(status.cases_required for status in context.reviews.values())
    if not required:
        lines += [
            "For this version the review of the templates is required; the review of the sample of cases is "
            "required from version 0.5 on.",
            "",
        ]
    rows = []
    for lang in i18n.LANGUAGES:
        status = context.reviews[lang]
        physicians = sum(item.role == "physician" for item in status.reviews)
        pre = sum(item.role == "pre_reviewer" for item in status.reviews)
        rows.append(
            [
                lang,
                "valid" if status.ok else "not valid",
                physicians,
                pre,
                f"{len(status.covered)} of {len(status.sample)}",
            ]
        )
    lines += _table(
        ["language", "status", "physician reviews", "pre-reviews", f"sample cases of {collection.name} reviewed"], rows
    )
    lines += [""]
    for lang in i18n.LANGUAGES:
        status = context.reviews[lang]
        lines += [f"### {lang}", ""]
        lines += [_review_line(item, collection) for item in status.reviews]
        if not status.ok:
            if status.placeholders:
                lines.append(f"- Not reviewed yet: `{status.path.name}` still has {status.placeholders} placeholders.")
            else:
                lines += [f"- Not valid: {problem}" for problem in status.problems]
        lines += [""]
    return lines


def _limitations(context: CardContext) -> list[str]:
    reference = i18n.text("disclaimer.reference", "en")
    lines = ["## Limitations", ""]
    lines += [
        f"- {reference} The keys reflect the cited sources and Proof's documented readings of them.",
        "- The rules are drafts until a physician per language has reviewed them (see above).",
        "- The red flag qSOFA ≥ 2 follows Sepsis-3 (2016), as the product requirements prescribe. The Surviving "
        "Sepsis Campaign 2021 advises against qSOFA as the only screening tool; the key reflects qSOFA, not current "
        "screening practice.",
        "- The lab distributions are synthetic (SynthEHR) and describe no real population; the background "
        "frequencies and sampling ranges are generation parameters.",
        "- The distribution of decisions and diagnoses follows the target plan and the rules, not the frequency of "
        "diseases; many cases carry several laboratory diagnoses.",
        "- The case texts in all three languages come from templates; their wording is part of the physician review.",
        "- A model's score measures agreement with this reference on synthetic cases; it is no statement about "
        "clinical performance.",
        "",
    ]
    return lines


def _licence(context: CardContext) -> list[str]:
    return [
        "## Licence",
        "",
        "- Cases, variants, renderings and prompts: Creative Commons Attribution 4.0 International "
        "(CC BY 4.0, `LICENSE`).",
        "- Rule packs, schemas and the rule documentation come from the Proof repository and are licensed under the "
        "Apache License 2.0 (`LICENSE-CODE`); see `NOTICE`.",
        "- The lab profiles are aggregated from SynthEHR output. SynthEHR's code is licensed under GPL-3.0; its README "
        "states no licence for the generated data. Status: " + context.inputs.synthehr_data_licence,
        "- The cited sources are not reproduced; each source's terms and the permitted use are recorded in "
        "`rules/<pack>/sources.yaml`.",
        "",
    ]


def _files(context: CardContext) -> list[str]:
    lines = ["## Files", ""]
    lines += _table(["path", "content"], [[f"`{path}`", text] for path, text in context.files])
    lines += [
        "",
        "`SHA256SUMS` lists the SHA-256 of every other file; check it with `sha256sum -c SHA256SUMS`.",
        "",
    ]
    return lines


def _contact(context: CardContext) -> list[str]:
    return ["## Contact", "", f"{context.inputs.contact}. Code and issues: <{REPOSITORY_URL}>.", ""]


def render(context: CardContext) -> str:
    """The card text: front matter, title, then the sections of :data:`SECTIONS` in order."""
    front = yamlio.dump_text(_metadata(context))
    title = f"# Proof {context.collection.name}" + (" (DRAFT)" if context.draft else "")
    lines = ["---", front.rstrip("\n"), "---", "", title, ""]
    for part in (
        _notices,
        _summary,
        _provenance,
        _rules,
        _review,
        _limitations,
        _licence,
        _files,
        _contact,
    ):
        lines += part(context)
    return "\n".join(lines).rstrip("\n") + "\n"


# --- Check -----------------------------------------------------------------------------------------------------------


def front_matter(text: str) -> dict[str, Any] | None:
    """The metadata of a card, or ``None`` if it has no front matter."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    data = yamlio.load_text(text[4:end], source="front matter")
    return data if isinstance(data, dict) else None


def missing_parts(text: str, *, draft: bool) -> list[str]:
    """Every required part the card text lacks: metadata, notices in zh/en/de, sections, draft marking."""
    problems = []
    try:
        metadata = front_matter(text)
    except yamlio.YamlError as exc:
        metadata = None
        problems.append(f"front matter: {exc}")
    if metadata is None:
        problems.append("the card has no Hugging Face front matter")
    else:
        problems += [f"front matter lacks {key}" for key in METADATA_KEYS if key not in metadata]
    for lang in i18n.LANGUAGES:
        for line in disclaimer.lines(lang):
            if line not in text:
                problems.append(f"the card lacks the notice in {lang}: {line}")
    headings = [line[3:].strip() for line in text.splitlines() if line.startswith("## ")]
    problems += [f"the card lacks the section {name!r}" for name in SECTIONS if name not in headings]
    marked = all(i18n.text(DRAFT_KEY, lang) in text for lang in i18n.LANGUAGES) and "(DRAFT)" in text
    if draft and not marked:
        problems.append("a draft card must be marked as draft in zh, en and de")
    if not draft and any(i18n.text(DRAFT_KEY, lang) in text for lang in i18n.LANGUAGES):
        problems.append("a release card must not carry the draft notice")
    return problems
