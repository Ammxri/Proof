"""SHA-256 helpers used for content hashes, cache keys and provenance."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from proof.core import canonical

_CHUNK = 1 << 20


def sha256_bytes(data: bytes) -> str:
    """Hex digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Hex digest of ``text`` encoded as UTF-8."""
    return sha256_bytes(text.encode("utf-8"))


def sha256_json(value: Any) -> str:
    """Hex digest of the canonical JSON form of ``value``."""
    return sha256_bytes(canonical.dumps_bytes(value))


def sha256_file(path: str | Path) -> str:
    """Hex digest of a file's bytes, read in chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
