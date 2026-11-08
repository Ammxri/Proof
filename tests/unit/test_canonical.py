"""Canonical JSON and strict JSON parsing."""

from __future__ import annotations

import pytest

from proof.core import canonical
from proof.core.canonical import CanonicalJSONError


def test_keys_sorted_no_whitespace_utf8():
    value = {"b": 1, "a": [True, None, 1.5], "ä": "发热"}
    assert canonical.dumps(value) == '{"a":[true,null,1.5],"b":1,"ä":"发热"}'
    assert canonical.dumps_bytes(value) == canonical.dumps(value).encode("utf-8")


def test_same_content_same_bytes_regardless_of_insertion_order():
    assert canonical.dumps({"x": 1, "y": {"b": 2, "a": 1}}) == canonical.dumps({"y": {"a": 1, "b": 2}, "x": 1})


def test_floats_use_shortest_round_trip_form():
    assert canonical.dumps([39.2, 0.1, 1e-7, 180.0, 15.2]) == "[39.2,0.1,1e-07,180.0,15.2]"


def test_tuples_serialise_like_lists():
    assert canonical.dumps((1, 2)) == "[1,2]"


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
        -0.0,
        {1: "x"},
        "é",
        {"é": 1},
        {1.5},
        b"bytes",
        object(),
    ],
)
def test_rejects_values_without_canonical_form(value):
    with pytest.raises(CanonicalJSONError):
        canonical.dumps(value)


def test_error_names_the_path():
    with pytest.raises(CanonicalJSONError, match=r"\$\.facts\.temp\[1\]"):
        canonical.dumps({"facts": {"temp": [1.0, float("nan")]}})


def test_json_lines_round_trip():
    values = [{"b": 2, "a": 1}, {"c": "三"}]
    data = canonical.dumps_lines(values)
    assert data == b'{"a":1,"b":2}\n{"c":"\xe4\xb8\x89"}\n'
    assert canonical.loads_lines(data) == [{"a": 1, "b": 2}, {"c": "三"}]
    assert canonical.loads_lines(b"") == []
    assert canonical.dumps_lines([]) == b""


@pytest.mark.parametrize("data", [b'{"a":1}', b'{"a":1}\n\n', b'\n{"a":1}\n'])
def test_json_lines_rejects_missing_newline_and_empty_lines(data):
    with pytest.raises(CanonicalJSONError):
        canonical.loads_lines(data)


def test_loads_rejects_duplicate_keys_and_non_finite_numbers():
    with pytest.raises(CanonicalJSONError, match="duplicate key"):
        canonical.loads('{"a": 1, "a": 2}')
    for text in ("NaN", "[Infinity]", "-Infinity"):
        with pytest.raises(CanonicalJSONError):
            canonical.loads(text)


def test_loads_accepts_bytes():
    assert canonical.loads('{"k":"值"}'.encode()) == {"k": "值"}
