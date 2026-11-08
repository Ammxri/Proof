"""Canonical JSON: exactly one byte representation per value, identical on every platform.

Rules: UTF-8, keys sorted, no whitespace, no NaN or infinity, no negative zero, strings in Unicode NFC. Python's float
repr is the shortest round-tripping form and therefore platform independent.
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any


class CanonicalJSONError(ValueError):
    """A value cannot be represented in canonical JSON."""


def _check(value: Any, path: str) -> None:
    if value is None or isinstance(value, bool | int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CanonicalJSONError(f"{path}: non-finite number {value!r}")
        if value == 0.0 and math.copysign(1.0, value) < 0:
            raise CanonicalJSONError(f"{path}: negative zero")
        return
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value:
            raise CanonicalJSONError(f"{path}: string is not NFC-normalised")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJSONError(f"{path}: key {key!r} is not a string")
            _check(key, f"{path}.<key>")
            _check(item, f"{path}.{key}")
        return
    if isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _check(item, f"{path}[{index}]")
        return
    raise CanonicalJSONError(f"{path}: unsupported type {type(value).__name__}")


def dumps(value: Any) -> str:
    """Serialise ``value`` to its canonical JSON text."""
    _check(value, "$")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def dumps_bytes(value: Any) -> bytes:
    """Serialise ``value`` to canonical JSON encoded as UTF-8."""
    return dumps(value).encode("utf-8")


def dumps_lines(values: Iterable[Any]) -> bytes:
    """Serialise values as JSON Lines: one canonical object per line, each terminated by ``\\n``."""
    return b"".join(dumps_bytes(value) + b"\n" for value in values)


def _reject_constant(name: str) -> Any:
    raise CanonicalJSONError(f"non-finite number {name} is not allowed")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CanonicalJSONError(f"duplicate key {key!r}")
        result[key] = value
    return result


def loads(text: str | bytes) -> Any:
    """Parse JSON strictly: duplicate keys and non-finite numbers are errors."""
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def loads_lines(data: str | bytes) -> list[Any]:
    """Parse JSON Lines strictly; empty lines are errors because canonical output never contains them."""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    if not data:
        return []
    if not data.endswith("\n"):
        raise CanonicalJSONError("JSON Lines data must end with a newline")
    lines = data[:-1].split("\n")
    result = []
    for number, line in enumerate(lines, start=1):
        if not line:
            raise CanonicalJSONError(f"line {number} is empty")
        result.append(loads(line))
    return result
