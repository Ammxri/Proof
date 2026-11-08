"""Licence gate for the locked environment (PR-C03, A-26).

Lists every installed distribution with pip-licenses and classifies its licence:
- ``fail``: GPL or AGPL (strong copyleft), or no recognisable licence; the gate exits with status 1;
- ``report``: LGPL and other weak copyleft (MPL, EPL, CDDL); listed for a decision, exit status unaffected;
- ``ok``: everything else.
Recorded decisions in ``tools/license_decisions.toml`` override the classification for one package and version.

Usage: ``uv run python tools/check_licenses.py``
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

DECISIONS_FILE = Path(__file__).with_name("license_decisions.toml")

_TOKEN = re.compile(r"[A-Za-z0-9.+]+")
_STRONG_TOKEN = re.compile(r"^A?GPL(?:v?\d.*)?\+?$", re.IGNORECASE)
_WEAK_TOKEN = re.compile(r"^(?:LGPL|MPL|EPL|CDDL)(?:v?-?\d.*)?\+?$", re.IGNORECASE)
_STRONG_PHRASE = re.compile(r"(?<!Lesser )(?<!Library )\bGeneral Public License", re.IGNORECASE)
_AFFERO_PHRASE = re.compile(r"Affero General Public License", re.IGNORECASE)
_WEAK_PHRASE = re.compile(
    r"(?:Lesser|Library) General Public License|Mozilla Public License|Eclipse Public License|"
    r"Common Development and Distribution License",
    re.IGNORECASE,
)
_UNKNOWN = {"", "unknown", "none", "unknown license"}


@dataclass(frozen=True)
class Verdict:
    name: str
    version: str
    license: str
    verdict: str
    reason: str


def classify(license_text: str) -> tuple[str, str]:
    """Classify a licence string from package metadata; returns (verdict, reason)."""
    text = " ".join(license_text.split())
    if text.lower() in _UNKNOWN:
        return "fail", "no recognisable licence"
    tokens = _TOKEN.findall(text.replace("-", " ").replace("_", " "))
    joined = [token for token in _TOKEN.findall(text)]
    if (
        any(_STRONG_TOKEN.match(t) for t in tokens)
        or any(_STRONG_TOKEN.match(t) for t in joined)
        or _STRONG_PHRASE.search(text)
        or _AFFERO_PHRASE.search(text)
    ):
        return "fail", "strong copyleft (GPL/AGPL)"
    if any(_WEAK_TOKEN.match(t) for t in tokens + joined) or _WEAK_PHRASE.search(text):
        return "report", "weak copyleft, decision required"
    return "ok", ""


def load_decisions(path: Path = DECISIONS_FILE) -> dict[tuple[str, str], dict[str, str]]:
    """Recorded decisions keyed by (normalised name, version)."""
    if not path.exists():
        return {}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    decisions = {}
    for entry in data.get("decision", []):
        decisions[(entry["name"].lower().replace("_", "-"), entry["version"])] = entry
    return decisions


def evaluate(packages: list[dict[str, str]], decisions: dict[tuple[str, str], dict[str, str]]) -> list[Verdict]:
    """Verdicts for the packages reported by pip-licenses."""
    verdicts = []
    for package in packages:
        name, version, license_text = package["Name"], package["Version"], package["License"]
        decision = decisions.get((name.lower().replace("_", "-"), version))
        if decision is not None:
            verdicts.append(Verdict(name, version, license_text, decision["verdict"], decision["reason"]))
            continue
        verdict, reason = classify(license_text)
        verdicts.append(Verdict(name, version, license_text, verdict, reason))
    return verdicts


def installed_packages() -> list[dict[str, str]]:
    """All distributions of the running interpreter's environment, via pip-licenses."""
    result = subprocess.run(
        [sys.executable, "-m", "piplicenses", "--format=json", "--from=mixed", "--with-system"],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def main() -> int:
    verdicts = evaluate(installed_packages(), load_decisions())
    for item in sorted(verdicts, key=lambda v: (v.verdict != "fail", v.verdict != "report", v.name.lower())):
        note = f"  ({item.reason})" if item.reason else ""
        print(f"{item.verdict:6}  {item.name} {item.version}: {item.license}{note}")
    failed = [v for v in verdicts if v.verdict == "fail"]
    reported = [v for v in verdicts if v.verdict == "report"]
    print(f"\n{len(verdicts)} packages, {len(failed)} failed, {len(reported)} reported for a decision.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
