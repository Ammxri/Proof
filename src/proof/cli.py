"""Command line interface ``proof``.

Every command's help ends with the fixed notices in zh, en and de (A-24); register commands with ``epilog=EPILOG``.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

import proof
import proof_rules
from proof.cases import collection, profiles
from proof.core import canonical, disclaimer
from proof_rules import loader
from proof_rules.explain import explain
from proof_rules.keys import FactError
from proof_rules.model import Domain

# "\b" stops click from re-wrapping the paragraph, so each language stays on its own line.
EPILOG = "\b\n" + disclaimer.block()

app = typer.Typer(
    name="proof",
    help="Proof - deterministic robustness test for clinical language models.",
    epilog=EPILOG,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
    pretty_exceptions_enable=False,
)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"proof {proof.__version__} (proof_rules {proof_rules.__version__})")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_show_version, is_eager=True, help="Show the versions and exit."),
    ] = False,
) -> None:
    """Proof - deterministic robustness test for clinical language models."""


# --- proof rules -----------------------------------------------------------------------------------------------------

rules_app = typer.Typer(
    name="rules",
    help="Check, list and explain the rule packs (keys come from rules, never from a language model).",
    epilog=EPILOG,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)
app.add_typer(rules_app, name="rules")

PacksOption = Annotated[
    Path, typer.Option("--packs", file_okay=False, help="Directory that holds the rule packs.", show_default=False)
]
DomainOption = Annotated[str, typer.Option("--domain", help="Name of the domain pack.")]


def _fail(problems: list[str] | tuple[str, ...]) -> NoReturn:
    for problem in problems:
        typer.echo(f"error: {problem}", err=True)
    raise typer.Exit(1)


def _domain(name: str, packs: Path) -> Domain:
    try:
        return loader.load_domain(name, packs)
    except loader.LoadError as exc:
        _fail(exc.problems)


@rules_app.command("check", epilog=EPILOG)
def rules_check(packs: PacksOption = loader.PACKS_ROOT) -> None:
    """Check every pack: files, references between them, unique ids, every rule's test vectors and every domain."""
    result = loader.check(packs)
    for pack in result.packs:
        typer.echo(f"pack {pack.name} ({pack.kind}): {pack.rules} rules, {pack.tests} test vectors")
    for domain in result.domains:
        typer.echo(
            f"domain {domain.name}: {domain.active_rules} active rules, {domain.fields} fields, "
            f"{domain.references} reference ranges"
        )
    if not result.ok:
        typer.echo(f"{len(result.problems)} problem(s)", err=True)
        _fail(result.problems)
    typer.echo("ok")


@rules_app.command("list", epilog=EPILOG)
def rules_list(domain: DomainOption = "fever", packs: PacksOption = loader.PACKS_ROOT) -> None:
    """List the active rules of a domain, one tab-separated line per rule."""
    loaded = _domain(domain, packs)
    typer.echo("id\tkind\ttarget\trequires\tsources\tstatus\tmigrated_from")
    for rule in loaded.rules:
        sources = ",".join(source.ref for source in rule.sources)
        typer.echo(
            f"{rule.id}\t{rule.kind}\t{rule.target}\t{','.join(rule.requires)}\t{sources}\t{rule.status}\t"
            f"{rule.migrated_from or '-'}"
        )


@rules_app.command("explain", epilog=EPILOG)
def rules_explain(
    case: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Case JSON with a 'facts' object.")],
    domain: Annotated[
        str | None, typer.Option("--domain", help="Domain pack; by default the one matching the case's complaint.")
    ] = None,
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Explain the key of a case: every rule's evaluation, the key and the ablation of each field."""
    try:
        data = canonical.loads(case.read_bytes())
    except (ValueError, UnicodeDecodeError) as exc:
        _fail([f"{case}: {exc}"])
    if not isinstance(data, dict) or not isinstance(data.get("facts"), dict):
        _fail([f"{case}: expected a JSON object with a 'facts' object"])
    name = domain
    if name is None:
        complaint = data.get("complaint")
        name = loader.domain_for_complaint(complaint, packs) if isinstance(complaint, str) else None
        if name is None:
            _fail([f"{case}: no domain pack for complaint {complaint!r}; pass --domain"])
    stored = data.get("key")
    try:
        lines = explain(_domain(name, packs), data["facts"], stored if isinstance(stored, dict) else None)
    except FactError as exc:
        _fail([f"{case}: {problem}" for problem in exc.problems])
    if "case_id" in data:
        typer.echo(f"case: {data['case_id']}")
    for line in lines:
        typer.echo(line)


# --- proof labs ------------------------------------------------------------------------------------------------------

labs_app = typer.Typer(
    name="labs",
    help="Build lab profiles from the SynthEHR biochemistry CSV (the CSV is only read, SynthEHR is never run).",
    epilog=EPILOG,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)
app.add_typer(labs_app, name="labs")


def _format_reference(reference: dict[str, int | float]) -> str:
    lower, upper = reference.get("lower"), reference.get("upper")
    return f"{'' if lower is None else lower}-{'' if upper is None else upper}"


@labs_app.command("build", epilog=EPILOG)
def labs_build(
    csv_path: Annotated[
        Path, typer.Option("--csv", exists=True, dir_okay=False, help="SynthEHR Biochemistry.csv (only read).")
    ],
    generator: Annotated[str, typer.Option("--generator", help="Generator and version, e.g. 'SynthEHR 2.0.1'.")],
    command: Annotated[str, typer.Option("--command", help="Command line the CSV was generated with.")],
    seed: Annotated[int, typer.Option("--seed", help="Seed the CSV was generated with.")],
    generated_on: Annotated[str, typer.Option("--generated-on", help="Date the CSV was generated (YYYY-MM-DD).")],
    domain: DomainOption = "fever",
    packs: PacksOption = loader.PACKS_ROOT,
    out: Annotated[
        Path | None,
        typer.Option("--out", file_okay=False, help="Target directory (default: profiles/ of the domain pack)."),
    ] = None,
) -> None:
    """Write one profile per lab field of the domain: reference range, counts, quantiles per status, provenance."""
    try:
        day = date.fromisoformat(generated_on)
    except ValueError:
        _fail([f"--generated-on: expected a date YYYY-MM-DD, got {generated_on!r}"])
    try:
        catalog = loader.load_domain(domain, packs, require_references=False).catalog
    except loader.LoadError as exc:
        _fail(exc.problems)
    provenance = profiles.Provenance(generator=generator, command=command, seed=seed, generated_on=day)
    try:
        built = profiles.build_profiles(csv_path, catalog, provenance)
    except profiles.ProfileError as exc:
        _fail(exc.problems)
    target = out if out is not None else packs / domain / loader.PROFILES_DIR
    for code, path in zip(sorted(built), profiles.write_profiles(built, target), strict=True):
        profile = built[code]
        counts = profile["counts"]
        by_status = ", ".join(f"{status} {count}" for status, count in counts["patients_by_status"].items())
        typer.echo(
            f"{profile['fact_code']}: reference {_format_reference(profile['reference'])} {profile['unit']}, "
            f"{counts['rows_used']} of {counts['rows']} rows, {counts['patients']} patients ({by_status}) -> {path}"
        )


# --- proof cases -----------------------------------------------------------------------------------------------------

cases_app = typer.Typer(
    name="cases",
    help="Build and validate case collections (facts from the sampler, keys from the rule set).",
    epilog=EPILOG,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)
app.add_typer(cases_app, name="cases")


@cases_app.command("build", epilog=EPILOG)
def cases_build(
    n: Annotated[int, typer.Option("--n", help="Number of base cases.")],
    seed_start: Annotated[int, typer.Option("--seed-start", help="Seed of the first case; seeds are consecutive.")],
    domain: DomainOption = "fever",
    out: Annotated[
        Path | None,
        typer.Option("--out", file_okay=False, help="Target directory (default: data/collections/<domain>-<n>)."),
    ] = None,
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Sample base cases, compute their keys and write cases.jsonl and collection.json."""
    target = out if out is not None else collection.DEFAULT_ROOT / f"{domain}-{n}"
    try:
        built = collection.build(domain, n, seed_start, name=target.name, root=packs)
    except collection.CollectionError as exc:
        _fail(exc.problems)
    cases_path, manifest_path = collection.write(built, target)
    summary = built.manifest.summary
    typer.echo(f"{built.manifest.name}: {n} cases, seeds {seed_start}-{seed_start + n - 1}")
    typer.echo(f"  {cases_path}")
    typer.echo(f"  {manifest_path}")
    typer.echo(f"relabeled: {summary.relabeled} of {summary.cases}")
    typer.echo(f"determinability: {collection.counts_line(summary.determinability)}")
    typer.echo(f"red flags: {collection.counts_line(summary.red_flags)}")
    typer.echo(f"diagnoses per case (number: cases): {collection.pairs_line(summary.ddx_per_case)}")
    typer.echo(f"critical fields per case (number: cases): {collection.pairs_line(summary.critical_fields_per_case)}")
    typer.echo(f"slowest case (sampling, key with ablation): {built.max_seconds * 1000:.1f} ms")


@cases_app.command("validate", epilog=EPILOG)
def cases_validate(
    path: Annotated[Path, typer.Argument(exists=True, help="Collection directory or a cases JSONL file.")],
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Check schema, facts, keys (recomputed), reproduction from the seed and the manifest of a collection."""
    report = collection.validate(path, packs)
    if not report.ok:
        typer.echo(f"{len(report.problems)} problem(s) in {path}", err=True)
        _fail(report.problems or [f"{path}: no cases"])
    typer.echo(
        f"{path}: {report.cases} cases valid, {report.relabeled} relabeled; slowest key with ablation "
        f"{report.max_key_seconds * 1000:.1f} ms"
    )


def _ensure_utf8_streams() -> None:
    """Redirected output on Windows defaults to a legacy code page that cannot encode Chinese; use UTF-8 instead."""
    for stream in (sys.stdout, sys.stderr):
        encoding = (getattr(stream, "encoding", None) or "").lower().replace("-", "")
        if encoding != "utf8" and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def main() -> None:
    """Entry point of the ``proof`` console script."""
    _ensure_utf8_streams()
    app()
