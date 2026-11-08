"""Command line interface ``proof``.

Every command's help ends with the fixed notices in zh, en and de (A-24); register commands with ``epilog=EPILOG``.
"""

from __future__ import annotations

import sys
from typing import Annotated

import typer

import proof
import proof_rules
from proof.core import disclaimer

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
