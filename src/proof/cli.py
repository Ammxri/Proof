"""Command line interface ``proof``.

Every command's help ends with the fixed notices in zh, en and de (A-24); register commands with ``epilog=EPILOG``.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Annotated, NoReturn

import typer

import proof
import proof_rules
from proof.cases import collection, profiles, review
from proof.cases.model import Case
from proof.core import canonical, disclaimer, i18n
from proof.core.paths import proof_home
from proof.harness import run as harness_run
from proof.harness.client import Reply
from proof.harness.providers import ProviderError, load_provider
from proof.render.case_text import RenderError, render_case
from proof.render.prompt import system_prompt
from proof.scoring import runs as scoring_runs
from proof.variants import sets as variant_sets
from proof.variants.generator import BUILT_MRS
from proof.variants.render import render_variant
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


# --- proof variants --------------------------------------------------------------------------------------------------

variants_app = typer.Typer(
    name="variants",
    help="Build and validate variants of a collection (metamorphic relations with expectations).",
    epilog=EPILOG,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)
app.add_typer(variants_app, name="variants")


@variants_app.command("build", epilog=EPILOG)
def variants_build(
    collection_dir: Annotated[
        Path, typer.Option("--collection", exists=True, file_okay=False, help="Collection directory.")
    ],
    variant_seed: Annotated[
        int, typer.Option("--variant-seed", help="Seed of the variants; a new seed, new variants.")
    ],
    per_case: Annotated[int, typer.Option("--per-case", help="Variants per relation and case (MR5: all pairs).")] = 1,
    mr: Annotated[
        list[str] | None, typer.Option("--mr", help="Relation to build; repeat for several (default: all built).")
    ] = None,
    out: Annotated[
        Path | None,
        typer.Option("--out", file_okay=False, help="Target directory (default: <collection>/variants/<seed>)."),
    ] = None,
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Build new variants of every case of a collection (PR-D02): same seed, same variants."""
    try:
        built = variant_sets.build(
            collection_dir, variant_seed, per_case=per_case, mrs=tuple(mr) if mr else BUILT_MRS, root=packs
        )
    except variant_sets.VariantSetError as exc:
        _fail(exc.problems)
    target = out if out is not None else variant_sets.default_directory(collection_dir, variant_seed)
    variants_path, manifest_path = variant_sets.write(built, target)
    summary = built.manifest.summary
    typer.echo(f"{built.manifest.collection}, variant seed {variant_seed}: {len(built.variants)} variants")
    typer.echo(f"  {variants_path}")
    typer.echo(f"  {manifest_path}")
    typer.echo(f"variants: {collection.counts_line(summary.variants)}")
    if any(summary.missing.values()):
        typer.echo(f"fewer than asked: {collection.counts_line(summary.missing)}")
    typer.echo(f"MR1 expected decisions: {collection.counts_line(summary.mr1_decisions)}")
    typer.echo(f"units per language (base cases and variants with a request): {summary.units_per_language}")


@variants_app.command("validate", epilog=EPILOG)
def variants_validate(
    path: Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Variant set directory.")],
    collection_dir: Annotated[
        Path | None,
        typer.Option("--collection", exists=True, file_okay=False, help="Collection (default: two levels up)."),
    ] = None,
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Check every variant against its base case and rebuild the set from its seed."""
    report = variant_sets.validate(path, collection_dir, packs)
    if not report.ok:
        typer.echo(f"{len(report.problems)} problem(s) in {path}", err=True)
        _fail(report.problems or [f"{path}: no variants"])
    by_mr = ", ".join(f"{mr} {count}" for mr, count in sorted(report.by_mr.items()))
    typer.echo(f"{path}: {report.variants} variants valid ({by_mr})")


# --- proof render ----------------------------------------------------------------------------------------------------

LangOption = Annotated[str, typer.Option("--lang", help="Language: zh, en or de.")]


def _check_lang(lang: str) -> None:
    if lang not in i18n.LANGUAGES:
        _fail([f"--lang: expected one of {', '.join(i18n.LANGUAGES)}, got {lang!r}"])


def _load_case(source: Path, case_id: str | None) -> Case:
    if source.is_dir() or source.suffix == ".jsonl":
        path = source / collection.CASES_FILE if source.is_dir() else source
        problems: list[str] = []
        cases = [case for _, case in collection.read_cases(path, problems)] if path.is_file() else []
        if problems or not cases:
            _fail(problems or [f"{path}: no cases"])
        if case_id is None and len(cases) > 1:
            _fail([f"{path} holds {len(cases)} cases; choose one with --case-id"])
        chosen = [case for case in cases if case_id is None or case.case_id == case_id]
        if not chosen:
            _fail([f"{path}: no case {case_id}"])
        return chosen[0]
    try:
        case = Case.model_validate(canonical.loads(source.read_bytes()))
    except (ValueError, UnicodeDecodeError) as exc:
        _fail([f"{source}: {exc}"])
    if case_id is not None and case.case_id != case_id:
        _fail([f"{source}: holds {case.case_id}, not {case_id}"])
    return case


@app.command("render", epilog=EPILOG)
def render(
    source: Annotated[
        Path, typer.Argument(exists=True, help="Case JSON file, cases JSONL file or collection directory.")
    ],
    lang: LangOption,
    case_id: Annotated[str | None, typer.Option("--case-id", help="Case to show from a JSONL file.")] = None,
    variants: Annotated[
        Path | None,
        typer.Option("--variants", exists=True, file_okay=False, help="Variant set directory, with --variant-id."),
    ] = None,
    variant_id: Annotated[str | None, typer.Option("--variant-id", help="Variant to show instead of the case.")] = None,
    with_prompt: Annotated[
        bool, typer.Option("--system-prompt", help="Show the system prompt of the domain before the case text.")
    ] = False,
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Show the text of a case or variant in one language, as a model receives it."""
    _check_lang(lang)
    variant = None
    if (variants is None) != (variant_id is None):
        _fail(["--variants and --variant-id go together"])
    if variants is not None:
        problems: list[str] = []
        path = variants / variant_sets.VARIANTS_FILE
        found = [v for _, v in variant_sets.read_variants(path, problems) if v.variant_id == variant_id]
        if not found:
            _fail(problems or [f"{path}: no variant {variant_id}"])
        variant = found[0]
        case_id = variant.case_id
    case = _load_case(source, case_id)
    name = loader.domain_for_complaint(case.complaint, packs)
    if name is None:
        _fail([f"{case.case_id}: no domain pack for complaint {case.complaint!r}"])
    domain = _domain(name, packs)
    try:
        rendering = render_case(case, domain, lang) if variant is None else render_variant(variant, case, domain, lang)
    except RenderError as exc:
        _fail([f"{variant_id or case.case_id}: {problem}" for problem in exc.problems])
    if with_prompt:
        typer.echo(system_prompt(domain, lang))
        typer.echo("-" * 40)
    typer.echo(rendering.text, nl=False)


# --- proof run -------------------------------------------------------------------------------------------------------


def _progress(number: int, total: int, unit: harness_run.Unit, reply: Reply, cached: bool) -> None:
    source = "cache" if cached else "request"
    typer.echo(f"  {number}/{total} {unit.unit_id}: {reply.status} ({source})")


@app.command("run", epilog=EPILOG)
def run(
    provider_file: Annotated[
        Path | None, typer.Option("--provider", dir_okay=False, help="Provider YAML (see providers/).")
    ] = None,
    collection_dir: Annotated[
        Path | None,
        typer.Option("--set", file_okay=False, help="Collection directory, e.g. data/collections/fever-100."),
    ] = None,
    variants_dir: Annotated[
        Path | None, typer.Option("--variants", file_okay=False, help="Variant set directory (MR1, MR3 units).")
    ] = None,
    langs: Annotated[list[str] | None, typer.Option("--lang", help="Language; repeat (default: zh, en, de).")] = None,
    max_cases: Annotated[
        int | None, typer.Option("--max-cases", help="Only the first N cases and their variants.")
    ] = None,
    out: Annotated[
        Path | None, typer.Option("--out", file_okay=False, help="Run directory (default: $PROOF_HOME/runs/<id>).")
    ] = None,
    resume: Annotated[
        Path | None, typer.Option("--resume", file_okay=False, help="Continue this run: send units without answer.")
    ] = None,
    from_manifest: Annotated[
        Path | None, typer.Option("--from-manifest", help="Repeat the run this manifest describes (new directory).")
    ] = None,
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Send every unit to a model: temperature 0, no second attempt, replies cached by request hash."""
    modes = sum(value is not None for value in (provider_file, resume, from_manifest))
    if modes != 1:
        _fail(["choose exactly one of --provider (new run), --resume or --from-manifest"])
    try:
        if provider_file is not None:
            if collection_dir is None:
                _fail(["--provider needs --set"])
            config = harness_run.configure(
                load_provider(provider_file),
                collection_dir,
                variants_dir=variants_dir,
                langs=tuple(langs) if langs else i18n.LANGUAGES,
                max_cases=max_cases,
            )
            directory = out
        elif resume is not None:
            config = harness_run.read_manifest(resume).config
            directory = resume
        else:
            assert from_manifest is not None  # noqa: S101 - one mode is set
            config = harness_run.read_manifest(from_manifest).config
            directory = out
        outcome = harness_run.execute(config, directory, resume=resume is not None, root=packs, progress=_progress)
    except (ProviderError, harness_run.RunError) as exc:
        _fail(exc.problems)
    manifest = outcome.manifest
    units = manifest.units
    typer.echo(f"run {manifest.run_id}: {manifest.status} -> {outcome.directory}")
    typer.echo(
        f"units: {units.ok} ok, {units.error} error, {units.open} open of {units.total}; {units.requests} requests"
    )
    typer.echo(f"tokens: {manifest.tokens.prompt} prompt, {manifest.tokens.completion} completion")
    cost = manifest.cost
    typer.echo(f"cost: {cost if isinstance(cost, str) else f'{cost.amount} {cost.currency}'}")
    typer.echo(f"models: {', '.join(manifest.models_reported) or '-'}")
    if manifest.ollama is not None:
        typer.echo(f"ollama: {json.dumps(manifest.ollama, ensure_ascii=False, sort_keys=True)}")
    if manifest.status != "complete":
        raise typer.Exit(1)


# --- proof score / proof compare -------------------------------------------------------------------------------------


def _ratio_text(ratio: dict) -> str:
    value = ratio["value"]
    shown = value if isinstance(value, str) else f"{value:.4f}"
    return f"{shown} ({ratio['numerator']}/{ratio['denominator']})"


def _split_lines(name: str, split: dict) -> list[str]:
    by_lang = ", ".join(f"{lang} {_ratio_text(ratio)}" for lang, ratio in split["by_lang"].items())
    return [f"{name}: {_ratio_text(split['all'])}; {by_lang}"]


def _profile_lines(data: dict) -> list[str]:
    m = data["metrics"]
    units = m["units"]
    lines = [
        f"run {data['run_id']} ({data['run_status']}), model {', '.join(data['models_reported']) or '-'}",
        f"units: {units['answered']} answered ({units['valid']} valid, {units['invalid']} invalid), "
        f"{units['errors']} without answer, of {units['total']}",
    ]
    lines += _split_lines("S1 decision", m["S1_decision"])
    lines += _split_lines("S2 questions recall", m["S2_questions"]["recall"])
    lines += _split_lines("S2 questions precision", m["S2_questions"]["precision"])
    lines += _split_lines("S3 red flags, complete", m["S3_red_flags"]["complete"])
    lines += _split_lines("S3 red flags, incomplete", m["S3_red_flags"]["incomplete"])
    lines += _split_lines("S4 diagnoses", m["S4_diagnoses"])
    for mr, item in m["S5_invariance"].items():
        lines.append(
            f"S5 invariance {mr}: violations {_ratio_text(item['violation_rate'])}, left out: "
            f"{item['invalid_excluded']} invalid, {item['missing_excluded']} without partner"
        )
    for name, item in m["S6_language_spread"].items():
        lines.append(f"S6 spread of {name}: {item['value']}")
    lines += _split_lines("S7 format", m["S7_format"])
    return lines


RunArgument = Annotated[Path, typer.Argument(exists=True, file_okay=False, help="Run directory.")]


@app.command("score", epilog=EPILOG)
def score(run_dir: RunArgument, packs: PacksOption = loader.PACKS_ROOT) -> None:
    """Score a run deterministically: S1–S7 with numerators and denominators, written to profile.json."""
    try:
        path, data = scoring_runs.write_profile(scoring_runs.load_run(run_dir, packs))
    except scoring_runs.ScoringError as exc:
        _fail(exc.problems)
    for line in _profile_lines(data):
        typer.echo(line)
    typer.echo(f"-> {path}")


@app.command("compare", epilog=EPILOG)
def compare(
    run_a: RunArgument,
    run_b: RunArgument,
    out: Annotated[Path | None, typer.Option("--out", dir_okay=False, help="Write the comparison as JSON.")] = None,
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Compare two runs: every metric that changed and every unit whose evaluation changed."""
    try:
        result = scoring_runs.compare(scoring_runs.load_run(run_a, packs), scoring_runs.load_run(run_b, packs))
    except scoring_runs.ScoringError as exc:
        _fail(exc.problems)
    typer.echo(f"a: {result['a']['run_id']} ({', '.join(result['a']['models']) or '-'})")
    typer.echo(f"b: {result['b']['run_id']} ({', '.join(result['b']['models']) or '-'})")
    typer.echo(f"metrics changed: {len(result['metrics'])}")
    for change in result["metrics"]:
        typer.echo(f"  {change['metric']}: {change['a']} -> {change['b']} (delta {change['delta']})")
    typer.echo(f"units changed: {len(result['units_changed'])}")
    for change in result["units_changed"]:
        typer.echo(f"  {change['unit_id']}: {change['a']} -> {change['b']}")
    if result["units_only_in_a"] or result["units_only_in_b"]:
        typer.echo(f"units only in a: {len(result['units_only_in_a'])}, only in b: {len(result['units_only_in_b'])}")
    if out is not None:
        out.write_bytes((json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
        typer.echo(f"-> {out}")


# --- proof review ----------------------------------------------------------------------------------------------------

review_app = typer.Typer(
    name="review",
    help="Physician review per language: sample of cases, review packet and check of the review record (PR-A02).",
    epilog=EPILOG,
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)
app.add_typer(review_app, name="review")

CollectionOption = Annotated[
    Path, typer.Option("--collection", exists=True, file_okay=False, help="Collection directory with collection.json.")
]


@review_app.command("sample", epilog=EPILOG)
def review_sample(lang: LangOption, collection_dir: CollectionOption) -> None:
    """List the cases a reviewer of one language checks: at least 10 %, at least one per target, deterministic."""
    _check_lang(lang)
    try:
        manifest = review.read_manifest(collection_dir)
    except review.ReviewError as exc:
        _fail(exc.problems)
    chosen = review.sample(manifest, lang)
    typer.echo(f"{manifest.name}, {lang}: {len(chosen)} of {len(manifest.cases)} cases")
    for case_id in chosen:
        typer.echo(case_id)


@review_app.command("packet", epilog=EPILOG)
def review_packet(
    lang: LangOption,
    collection_dir: CollectionOption,
    out: Annotated[
        Path | None,
        typer.Option(
            "--out", file_okay=False, help="Target directory (default: $PROOF_HOME/review/<collection>/<lang>)."
        ),
    ] = None,
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Write the review packet: document with prompt and sample cases, record template, templates and labels."""
    _check_lang(lang)
    try:
        manifest = review.read_manifest(collection_dir)
        target = out if out is not None else proof_home() / "review" / manifest.name / lang
        written = review.packet(lang, collection_dir, target, packs)
    except review.ReviewError as exc:
        _fail(exc.problems)
    for path in written:
        typer.echo(str(path))


@review_app.command("verify", epilog=EPILOG)
def review_verify(
    lang: LangOption,
    record: Annotated[
        Path | None, typer.Option("--record", dir_okay=False, help="Review record (default: review/<lang>.yaml).")
    ] = None,
    collection_dir: Annotated[
        Path | None,
        typer.Option("--collection", exists=True, file_okay=False, help="Also require the sample of this collection."),
    ] = None,
    packs: PacksOption = loader.PACKS_ROOT,
) -> None:
    """Check a review record: filled in, by a physician, covering the current templates (and the sample)."""
    _check_lang(lang)
    path = record if record is not None else Path("review") / f"{lang}.yaml"
    try:
        report = review.verify(path, lang, collection_dir=collection_dir, root=packs)
    except review.ReviewError as exc:
        _fail(exc.problems)
    if not report.ok:
        typer.echo(f"{len(report.problems)} problem(s) in {path}", err=True)
        _fail(report.problems)
    typer.echo(f"{path}: valid; {report.physicians} physician review(s), {report.pre_reviewers} pre-review(s)")


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
