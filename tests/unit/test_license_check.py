"""Licence gate classification (PR-C03, A-26)."""

from __future__ import annotations

import importlib.util
import sys

import pytest


@pytest.fixture(scope="module")
def gate(request):
    path = request.config.rootpath / "tools" / "check_licenses.py"
    spec = importlib.util.spec_from_file_location("check_licenses", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_licenses"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "text",
    [
        "GPL",
        "GPLv3",
        "GPL-3.0-or-later",
        "GPL-2.0+",
        "AGPL-3.0",
        "GNU General Public License v3 (GPLv3)",
        "GNU Affero General Public License v3",
        "MIT OR GPL-2.0",
    ],
)
def test_strong_copyleft_fails(gate, text):
    assert gate.classify(text)[0] == "fail"


@pytest.mark.parametrize(
    "text",
    [
        "LGPL-3.0",
        "LGPLv2+",
        "GNU Lesser General Public License v3 (LGPLv3)",
        "GNU Library General Public License",
        "Mozilla Public License 2.0 (MPL 2.0)",
        "MPL-2.0",
        "EPL-2.0",
        "CDDL-1.0",
    ],
)
def test_weak_copyleft_is_reported(gate, text):
    assert gate.classify(text)[0] == "report"


@pytest.mark.parametrize(
    "text",
    ["MIT", "BSD-3-Clause", "Apache-2.0 OR BSD-2-Clause", "Apache Software License", "PSF-2.0", "ISC License (ISCL)"],
)
def test_permissive_is_ok(gate, text):
    assert gate.classify(text) == ("ok", "")


@pytest.mark.parametrize("text", ["", "UNKNOWN", "  ", "None"])
def test_unknown_licence_fails(gate, text):
    assert gate.classify(text)[0] == "fail"


def test_recorded_decision_overrides_classification(gate, tmp_path):
    decisions_file = tmp_path / "decisions.toml"
    decisions_file.write_text(
        '[[decision]]\nname = "Some_Pkg"\nversion = "1.0"\nverdict = "ok"\nreason = "decided"\n', encoding="utf-8"
    )
    decisions = gate.load_decisions(decisions_file)
    packages = [
        {"Name": "some-pkg", "Version": "1.0", "License": "UNKNOWN"},
        {"Name": "some-pkg", "Version": "2.0", "License": "UNKNOWN"},
    ]
    verdicts = gate.evaluate(packages, decisions)
    assert [v.verdict for v in verdicts] == ["ok", "fail"]
    assert gate.load_decisions(tmp_path / "missing.toml") == {}


def test_recorded_decisions_are_complete(gate):
    decisions = gate.load_decisions()
    assert decisions, "tools/license_decisions.toml holds the owner's decisions"
    for (name, version), entry in decisions.items():
        assert set(entry) == {"name", "version", "verdict", "reason"}, name
        assert entry["verdict"] in {"ok", "fail"}, name
        assert version and entry["reason"].strip(), name
    # MPL-2.0 certifi is allowed by decision D-10, only for the version that was checked.
    assert decisions[("certifi", "2026.10.23")]["verdict"] == "ok"
    classified = gate.classify("Mozilla Public License 2.0 (MPL 2.0)")
    assert classified[0] == "report", "without a decision MPL is still reported"
