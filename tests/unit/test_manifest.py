"""Manifest base model and helpers."""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest
from pydantic import ValidationError

import proof
import proof_rules
from proof.core import canonical, manifest, paths


def test_utc_now_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", manifest.utc_now())


def test_new_manifest_without_repo():
    item = manifest.new_manifest("test")
    assert item.kind == "test"
    assert item.manifest_version == 1
    assert item.proof_version == proof.__version__
    assert item.rules_version == proof_rules.__version__
    assert item.git is None
    assert item.platform.python.startswith("3.")
    data = canonical.loads(item.to_canonical_json())
    assert data["kind"] == "test"
    assert set(data) == {
        "manifest_version",
        "kind",
        "created_utc",
        "proof_version",
        "rules_version",
        "platform",
        "git",
    }


def test_manifest_rejects_unknown_fields_and_bad_values():
    base = manifest.new_manifest("test").model_dump()
    with pytest.raises(ValidationError):
        manifest.ManifestBase(**{**base, "extra": 1})
    with pytest.raises(ValidationError):
        manifest.ManifestBase(**{**base, "created_utc": "2026-11-08 12:00"})
    with pytest.raises(ValidationError):
        manifest.ManifestBase(**{**base, "kind": ""})


def test_git_state_outside_a_repository(tmp_path):
    assert manifest.git_state(tmp_path) is None


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_git_state_reports_commit_and_dirty_flag(tmp_path):
    def git(*args):
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)  # noqa: S603, S607

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    git("config", "commit.gpgsign", "false")
    (tmp_path / "f.txt").write_text("a", encoding="utf-8")
    git("add", "f.txt")
    git("commit", "-q", "-m", "init")
    clean = manifest.git_state(tmp_path)
    assert clean is not None
    assert re.fullmatch(r"[0-9a-f]{40}", clean.commit)
    assert clean.dirty is False
    (tmp_path / "f.txt").write_text("b", encoding="utf-8")
    assert manifest.git_state(tmp_path).dirty is True


def test_git_state_without_git_executable(monkeypatch, tmp_path):
    monkeypatch.setattr(manifest.shutil, "which", lambda name: None)
    assert manifest.git_state(tmp_path) is None


def test_git_state_when_git_cannot_start(monkeypatch, tmp_path):
    def broken(*args, **kwargs):
        raise OSError("cannot start")

    monkeypatch.setattr(manifest.subprocess, "run", broken)
    assert manifest.git_state(tmp_path) is None


def test_proof_home(monkeypatch, tmp_path):
    monkeypatch.delenv(paths.ENV_HOME, raising=False)
    monkeypatch.chdir(tmp_path)
    assert paths.proof_home() == (tmp_path / ".proof").resolve()
    monkeypatch.setenv(paths.ENV_HOME, "  ")
    assert paths.proof_home() == (tmp_path / ".proof").resolve()
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "work"))
    assert paths.proof_home() == (tmp_path / "work").resolve()
