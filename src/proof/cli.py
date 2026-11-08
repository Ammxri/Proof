"""Command line interface ``proof``.

Every command's help ends with the fixed notices in zh, en and de (A-24); register commands with ``epilog=EPILOG``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, NoReturn

import typer

import proof
import proof_rules
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
