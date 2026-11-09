"""Repository rules: structure (PR-N09), independence (PR-N10, D-01), licences (PR-C01), secrets, CI (PR-N07)."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

APACHE_2_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
CC_BY_4_SHA256 = "9ba9550ad48438d0836ddab3da480b3b69ffa0aac7b7878b5a0039e7ab429411"

PRD_FOLDERS = ("cases", "render", "variants", "harness", "scoring", "report")
NETWORK_MODULES = {"httpx", "requests", "urllib", "urllib3", "http", "socket", "aiohttp", "proof.harness"}


def _python_files(*roots: Path):
    for root in roots:
        yield from sorted(root.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_prd_folders_exist_as_packages(repo_root):
    for name in PRD_FOLDERS:
        assert (repo_root / "src/proof" / name / "__init__.py").is_file(), name
    assert (repo_root / "src/proof/core/__init__.py").is_file()
    assert (repo_root / "src/proof_rules/__init__.py").is_file(), "rules/ is the package proof_rules (A-31)"


def test_wheel_contains_both_import_packages(repo_root):
    config = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/proof", "src/proof_rules"]
    assert config["project"]["scripts"] == {"proof": "proof.cli:main"}
    assert config["project"]["requires-python"] == ">=3.12"


def test_no_dependency_on_other_projects(repo_root):
    config = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    declared = config["project"]["dependencies"] + config["dependency-groups"]["dev"]
    assert not [d for d in declared if "neurogrid" in d.lower()]
    assert "sources" not in config.get("tool", {}).get("uv", {}), "no path or git sources (D-01)"
    lock = tomllib.loads((repo_root / "uv.lock").read_text(encoding="utf-8"))
    for package in lock["package"]:
        assert "neurogrid" not in package["name"].lower()
        source = package.get("source", {})
        if package["name"] == "proof":
            assert source == {"editable": "."}
        else:
            assert set(source) == {"registry"}, (package["name"], source)


def test_code_never_mentions_or_imports_other_projects(repo_root):
    this_file = Path(__file__).resolve()
    for path in _python_files(repo_root / "src", repo_root / "tests", repo_root / "tools"):
        if path.resolve() == this_file:
            continue
        text = path.read_text(encoding="utf-8").lower()
        assert "neurogrid" not in text, path
        assert "diagohelp" not in text, path


@pytest.mark.parametrize("package", ["src/proof_rules", "src/proof/scoring"])
def test_rules_and_scoring_never_import_network_or_model_code(repo_root, package):
    for path in _python_files(repo_root / package):
        for name in _imports(path):
            top = {name, name.split(".")[0], ".".join(name.split(".")[:2])}
            assert not (top & NETWORK_MODULES), (path, name)


def test_licence_files_are_the_official_texts(repo_root):
    import hashlib

    assert hashlib.sha256((repo_root / "LICENSE").read_bytes()).hexdigest() == APACHE_2_SHA256
    assert hashlib.sha256((repo_root / "LICENSE-DATA").read_bytes()).hexdigest() == CC_BY_4_SHA256
    config = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["project"]["license"] == "Apache-2.0"
    assert config["project"]["license-files"] == ["LICENSE", "LICENSE-DATA", "NOTICE"]
    notice = (repo_root / "NOTICE").read_text(encoding="utf-8")
    assert "Apache License, Version 2.0" in notice
    assert "Creative Commons Attribution 4.0 International" in notice
    assert "not a medical device" in notice


def test_gitignore_keeps_secrets_and_working_data_out(repo_root):
    lines = set((repo_root / ".gitignore").read_text(encoding="utf-8").splitlines())
    assert {".proof/", ".local/", ".env", ".env.*", "!.env.example", ".venv/"} <= lines


def test_line_endings_are_fixed_to_lf(repo_root):
    assert "* text=auto eol=lf" in (repo_root / ".gitattributes").read_text(encoding="utf-8").splitlines()


def test_env_example_holds_names_but_no_values(repo_root):
    entries = [
        line
        for line in (repo_root / ".env.example").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert entries
    for line in entries:
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*=", line), line
    names = {line[:-1] for line in entries}
    assert {"PROOF_PRIVATE_SEED", "PROOF_HOME", "DEEPSEEK_API_KEY"} <= names


def test_ci_runs_on_windows_and_linux_with_pinned_actions(repo_root):
    workflow = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "os: [ubuntu-latest, windows-latest]" in workflow
    for step in ("uv sync --locked", "ruff check", "ruff format --check", "pytest --cov", "check_licenses.py"):
        assert step in workflow, step
    assert "pip-audit" in workflow
    uses = re.findall(r"uses:\s*(\S+)", workflow)
    assert uses
    for action in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), action


# Directories that are never versioned (.gitignore) or that tools create; they are not part of the repository.
UNVERSIONED = {".git", ".venv", ".local", ".proof", ".pytest_cache", ".ruff_cache", "__pycache__", "dist", "build",
               "fresh", "htmlcov", "site"}  # fmt: skip
PROGRAM_SUFFIXES = {".exe", ".dll", ".so", ".dylib", ".cs", ".csproj", ".sln", ".nupkg", ".deps.json", ".pdb"}
# The only files that may name SynthEHR in their path: the test CSV and the documentation of the run.
SYNTHEHR_PATHS = {"tests/fixtures/synthehr/mini.csv", "docs/daten/synthehr.md"}


def _repository_files(root: Path):
    for path in sorted(root.rglob("*")):
        parts = path.relative_to(root).parts
        if path.is_file() and not (set(parts[:-1]) & UNVERSIONED) and not parts[-1].startswith(".coverage"):
            yield path


def test_no_synthehr_program_or_code_in_the_repository(repo_root):
    """PR-C02: Proof reads only the CSV output of SynthEHR; no program, library or source of it is in the repository."""
    files = list(_repository_files(repo_root))
    assert files
    for path in files:
        relative = path.relative_to(repo_root).as_posix()
        assert not any(relative.lower().endswith(suffix) for suffix in PROGRAM_SUFFIXES), relative
        if "synthehr" in relative.lower():
            assert relative in SYNTHEHR_PATHS, relative


def test_proof_never_starts_another_program_except_git(repo_root):
    """PR-C02: the only subprocess in the package is git for the manifest; SynthEHR is never run by Proof."""
    for path in _python_files(repo_root / "src"):
        if "subprocess" in _imports(path):
            assert path == repo_root / "src/proof/core/manifest.py", path
        text = path.read_text(encoding="utf-8")
        assert "SynthEHR.exe" not in text and "os.system" not in text, path


def test_collections_and_schemas_are_versioned(repo_root):
    """A-46: the public collections and the JSON Schemas live in the repository."""
    assert (repo_root / "schema/case.schema.json").is_file()
    for name in ("cases.jsonl", "collection.json"):
        assert (repo_root / "data/collections/fever-100" / name).is_file()
