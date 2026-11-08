"""Command line interface: notices in every help text (A-24, PR-D03), versions, UTF-8 output."""

from __future__ import annotations

import io
import os
import subprocess
import sys

import typer.main
from typer.testing import CliRunner

import proof
import proof_rules
from proof import cli
from proof.core import disclaimer, i18n

runner = CliRunner()


def _all_commands(command, path: tuple[str, ...] = ()):
    yield path, command
    for name, sub in getattr(command, "commands", {}).items():
        yield from _all_commands(sub, (*path, name))


def test_root_help_contains_all_notices():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for lang in i18n.LANGUAGES:
        for sentence in disclaimer.lines(lang):
            assert sentence in result.output


def test_every_command_help_contains_all_notices():
    root = typer.main.get_command(cli.app)
    for path, _command in _all_commands(root):
        result = runner.invoke(cli.app, [*path, "--help"])
        assert result.exit_code == 0, path
        for lang in i18n.LANGUAGES:
            for sentence in disclaimer.lines(lang):
                assert sentence in result.output, (path, lang)


def test_notices_keep_one_line_per_language():
    result = runner.invoke(cli.app, ["--help"])
    lines = [line.strip() for line in result.output.splitlines()]
    for lang in i18n.LANGUAGES:
        assert f"{lang}: {' '.join(disclaimer.lines(lang))}" in lines


def test_no_arguments_shows_help():
    result = runner.invoke(cli.app, [])
    assert "Usage:" in result.output
    assert disclaimer.lines("en")[0] in result.output


def test_version():
    result = runner.invoke(cli.app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"proof {proof.__version__} (proof_rules {proof_rules.__version__})"


def test_ensure_utf8_streams_reconfigures_legacy_encodings(monkeypatch):
    legacy = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    already = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", legacy)
    monkeypatch.setattr(sys, "stderr", already)
    cli._ensure_utf8_streams()
    assert sys.stdout.encoding == "utf-8"
    assert sys.stderr.encoding == "utf-8"
    sys.stdout.write("发热")


def test_console_script_prints_chinese_when_redirected():
    result = subprocess.run(
        [sys.executable, "-c", "import sys; sys.argv = ['proof', '--help']; from proof.cli import main; main()"],
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert disclaimer.lines("zh")[0].encode("utf-8") in result.stdout
