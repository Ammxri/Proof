"""Shared test fixtures."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from proof.core import yamlio
from proof_rules import loader
from proof_rules.model import Domain

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PACKS = REPO_ROOT / "tests" / "fixtures" / "packs"
FIXTURE_CASES = REPO_ROOT / "tests" / "fixtures" / "cases"

# Facts of the case in PRD §5 (FEV-000123).
PRD_FACTS: dict[str, Any] = {
    "vital.temp_c": 39.2,
    "vital.resp_rate": 24,
    "vital.sbp": 96,
    "vital.mental_status": "altered",
    "hx.onset_days": 2,
    "hx.cough": True,
    "lab.crp_mg_l": 180,
    "lab.wbc_g_l": 15.2,
}


@pytest.fixture
def repo_root() -> Path:
    """Root directory of the repository."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def demo() -> Domain:
    """The synthetic test domain ``demo`` with the library pack ``labx``."""
    return loader.load_domain("demo", FIXTURE_PACKS)


@pytest.fixture
def prd_facts() -> dict[str, Any]:
    """Facts of the PRD example case, as a fresh copy."""
    return dict(PRD_FACTS)


@pytest.fixture
def fixture_packs() -> Path:
    return FIXTURE_PACKS


@pytest.fixture
def fixture_cases() -> Path:
    return FIXTURE_CASES


@pytest.fixture
def packs(tmp_path: Path) -> Path:
    """A writable copy of the test packs."""
    target = tmp_path / "packs"
    shutil.copytree(FIXTURE_PACKS, target)
    return target


class _NoAliasDumper(yaml.SafeDumper):
    """The strict loader rejects aliases, so shared objects are written out in full."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def _edit_yaml(path: Path, change: Callable[[Any], Any]) -> None:
    data = yamlio.load_file(path)
    result = change(data)
    text = yaml.dump(data if result is None else result, Dumper=_NoAliasDumper, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def edit_yaml() -> Callable[[Path, Callable[[Any], Any]], None]:
    """Load a YAML file, let ``change`` modify (or replace) the data and write it back."""
    return _edit_yaml
