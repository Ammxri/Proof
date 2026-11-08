"""Common part of every manifest Proof writes: what was produced, when, by which versions, on which platform.

Specific manifests (collections, runs, release packages) extend :class:`ManifestBase`.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

import proof
import proof_rules
from proof.core import canonical

_GIT_TIMEOUT_SECONDS = 10


class PlatformInfo(BaseModel):
    """Interpreter and operating system that produced an artefact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    python: str
    implementation: str
    system: str
    machine: str


class GitState(BaseModel):
    """Commit of the working tree and whether it had uncommitted changes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    dirty: bool


class ManifestBase(BaseModel):
    """Fields shared by all manifests."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_version: Literal[1] = 1
    kind: str = Field(min_length=1)
    created_utc: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    proof_version: str
    rules_version: str
    platform: PlatformInfo
    git: GitState | None

    def to_canonical_json(self) -> bytes:
        """The manifest as canonical JSON bytes."""
        return canonical.dumps_bytes(self.model_dump(mode="json"))


def utc_now() -> str:
    """Current UTC time in ISO 8601 with second precision, e.g. ``2026-11-08T12:00:00Z``."""
    return datetime.now(UTC).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def platform_info() -> PlatformInfo:
    """Description of the running interpreter and system."""
    return PlatformInfo(
        python=platform.python_version(),
        implementation=platform.python_implementation(),
        system=platform.system(),
        machine=platform.machine(),
    )


def _git(repo_dir: Path, *args: str) -> str | None:
    executable = shutil.which("git")
    if executable is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603 - fixed executable and arguments, no shell
            [executable, "-C", str(repo_dir), *args],
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def git_state(repo_dir: str | Path) -> GitState | None:
    """Commit and dirty flag of ``repo_dir``, or ``None`` if it is not a git work tree or git is unavailable."""
    repo_dir = Path(repo_dir)
    commit = _git(repo_dir, "rev-parse", "--verify", "HEAD")
    if commit is None:
        return None
    status = _git(repo_dir, "status", "--porcelain", "--untracked-files=no")
    return GitState(commit=commit.strip(), dirty=bool(status and status.strip()))


def new_manifest(kind: str, *, repo_dir: str | Path | None = None) -> ManifestBase:
    """A base manifest for an artefact of type ``kind`` produced now."""
    return ManifestBase(
        kind=kind,
        created_utc=utc_now(),
        proof_version=proof.__version__,
        rules_version=proof_rules.__version__,
        platform=platform_info(),
        git=git_state(repo_dir) if repo_dir is not None else None,
    )
