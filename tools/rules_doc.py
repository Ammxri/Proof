"""Generate ``docs/regeln.md`` from the rule packs (PR-A03: the rules are public and every rule names its source).

The document is generated, never edited by hand. A test compares the committed file with a fresh rendering.

Usage:
    uv run python tools/rules_doc.py            # write docs/regeln.md
    uv run python tools/rules_doc.py --check    # exit 1 if docs/regeln.md is out of date
"""

from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

from proof.core import disclaimer
from proof_rules import loader
from proof_rules.logic import condition_text
from proof_rules.model import Domain, FieldDef, MigrationTable, Rule, Source, Term

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "regeln.md"
KIND_TEXT = {"red_flag": "red flag", "ddx": "differential diagnosis"}
STATUS_TEXT = {"draft_unreviewed": "draft, not reviewed by a physician"}


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(header: Iterable[str], rows: Iterable[Iterable[object]]) -> list[str]:
    header = list(header)
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(_cell(value) for value in row) + " |" for row in rows]
    return lines


def _labels(item: FieldDef | Term) -> str:
    labels = item.labels
    if isinstance(item, FieldDef):
        return " / ".join(f"{lang}: {getattr(labels, lang).name}" for lang in ("en", "de", "zh"))
    return " / ".join(f"{lang}: {getattr(labels, lang)}" for lang in ("en", "de", "zh"))


def _field_row(field: FieldDef) -> list[object]:
    kind = "enum: " + ", ".join(field.values) if field.type == "enum" else field.type
    unit = field.unit or "-"
    bounds = "not set (no source yet; required once a domain uses the field)" if unit != "-" else "-"
    if field.bounds is not None:
        source = field.bounds.source
        upper = "no upper limit" if field.bounds.upper is None else field.bounds.upper
        bounds = f"{field.bounds.lower} to {upper} ({source.ref}: {source.locator})"
    return [f"`{field.code}`", _labels(field), kind, unit, bounds]


def _sources(rule: Rule) -> str:
    return "; ".join(f"{source.ref}: {source.locator}" for source in rule.sources)


def _rule_rows(rules: Iterable[Rule]) -> list[list[object]]:
    return [
        [
            f"`{rule.id}`",
            KIND_TEXT[rule.kind],
            f"`{rule.target}`",
            condition_text(rule.when),
            _sources(rule),
            rule.migrated_from or "-",
        ]
        for rule in rules
    ]


def _source_rows(sources: Iterable[Source]) -> list[list[object]]:
    return [
        [
            source.id,
            source.citation,
            source.kind.replace("_", " "),
            source.url,
            source.terms,
            source.terms_checked_on.isoformat(),
            source.permitted_use,
        ]
        for source in sources
    ]


def _domain_section(domain: Domain) -> list[str]:
    lines = [
        f"## Domain `{domain.name}`",
        "",
        f"Complaint `{domain.complaint}`, case ids `{domain.case_prefix}-nnnnnn`, {len(domain.rules)} active rules, "
        f"{len(domain.catalog.fields)} facts.",
        "",
        "### Facts",
        "",
        *_table(["Code", "Name", "Type", "Unit", "Physiological bounds"], map(_field_row, domain.catalog.fields)),
        "",
        "### Answer codes",
        "",
        *_table(
            ["Code", "Kind", "Name"],
            [
                *([f"`{term.code}`", "red flag", _labels(term)] for term in domain.vocabulary.red_flags),
                *([f"`{term.code}`", "differential diagnosis", _labels(term)] for term in domain.vocabulary.ddx),
            ],
        ),
        "",
        "### Reference ranges",
        "",
        *_table(
            ["Fact", "Lower", "Upper"],
            (
                [f"`{code}`", "-" if ref.lower is None else ref.lower, "-" if ref.upper is None else ref.upper]
                for code, ref in sorted(domain.references.items())
            ),
        ),
        "",
        "### Active rules",
        "",
        *_table(["Rule", "Kind", "Target", "Condition", "Sources", "Migrated from"], _rule_rows(domain.rules)),
        "",
    ]
    return lines


def _migration_section(pack_name: str, table: MigrationTable) -> list[str]:
    migrated = sum(1 for entry in table.entries if entry.migrated)
    rows = []
    for entry in table.entries:
        if not entry.items:
            rows.append([entry.key, entry.condition, "-", "-", entry.reason or ""])
        for item in entry.items:
            rows.append(
                [
                    entry.key,
                    entry.condition,
                    item.text,
                    ", ".join(f"`{rule}`" for rule in item.rules) or "not migrated",
                    " ".join(text for text in (item.reason, item.note, entry.note) if text),
                ]
            )
        if entry.items and entry.reason:
            rows.append([entry.key, entry.condition, "-", "-", entry.reason])
    return [
        f"### Migration table of `{pack_name}`",
        "",
        f"Source: `{table.source.file}`, table `{table.source.table}`, SHA-256 `{table.source.sha256}`. "
        f"{migrated} of {len(table.entries)} keys are migrated to at least one rule.",
        "",
        *_table(["Legacy key", "Condition", "Prototype text", "Rules", "Reason / note"], rows),
        "",
    ]


def render(root: Path = loader.PACKS_ROOT) -> str:
    """The whole document for the packs in ``root``."""
    result = loader.check(root)
    if not result.ok:
        raise loader.LoadError(result.problems)
    packs = [loader.read_pack(root / summary.name) for summary in result.packs]
    lines = [
        "# Proof rules",
        "",
        "Generated from the rule packs by `tools/rules_doc.py`; do not edit by hand.",
        "",
        *(f"> {line}  " for line in disclaimer.block().splitlines()),
        "",
        "Every rule is a **draft, not reviewed by a physician** (status `draft_unreviewed`). Rules state criteria and "
        "thresholds in our own words and cite their source with a locator; no text or table of a source is copied. "
        "Keys are computed from these rules with three-valued logic, never by a language model.",
        "",
    ]
    for summary in result.domains:
        lines += _domain_section(loader.load_domain(summary.name, root))
    lines += ["## Packs", ""]
    for pack in packs:
        lines += [f"### Pack `{pack.name}` ({pack.config.kind}, {len(pack.rules)} rules)", ""]
        if pack.config.kind == "library":
            rows = (
                [*_field_row(field)[:2], field.unit or "-", ", ".join(field.synthehr.codes) if field.synthehr else "-",
                 _field_row(field)[4]]
                for field in pack.catalog.fields
            )  # fmt: skip
            lines += [
                "Facts of the library; a domain uses those its active rules need.",
                "",
                *_table(["Code", "Name", "Unit", "SynthEHR codes", "Physiological bounds"], rows),
                "",
            ]
        lines += [
            *_table(["Rule", "Kind", "Target", "Condition", "Sources", "Migrated from"], _rule_rows(pack.rules)),
            "",
        ]
        if pack.migration is not None:
            lines += _migration_section(pack.name, pack.migration)
    lines += ["## Sources", ""]
    sources = sorted((source for pack in packs for source in pack.sources.sources), key=lambda source: source.id)
    lines += _table(
        ["Id", "Citation", "Kind", "URL", "Terms", "Terms checked on", "Permitted use"], _source_rows(sources)
    )
    lines.append("")
    status = sorted({STATUS_TEXT[rule.status] for pack in packs for rule in pack.rules})
    lines += [f"Rule status: {', '.join(status) or '-'}.", ""]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if argv not in ([], ["--check"]):
        print(__doc__, file=sys.stderr)
        return 2
    text = render()
    if argv == ["--check"]:
        current = OUTPUT.read_bytes().decode("utf-8") if OUTPUT.exists() else ""
        if current != text:
            print(f"{OUTPUT} is out of date; run: uv run python tools/rules_doc.py", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_bytes(text.encode("utf-8"))
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
