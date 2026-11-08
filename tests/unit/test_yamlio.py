"""Strict YAML loading."""

from __future__ import annotations

import pytest

from proof.core import yamlio
from proof.core.yamlio import YamlError


def test_loads_plain_data():
    data = yamlio.load_text("a: 1\nb: [x, 2.5, null]\nc: {d: true, e: false}\nf: 发热\n")
    assert data == {"a": 1, "b": ["x", 2.5, None], "c": {"d": True, "e": False}, "f": "发热"}


@pytest.mark.parametrize("word", ["yes", "no", "on", "off", "Yes", "NO", "y", "n"])
def test_yaml_1_1_words_stay_strings(word):
    assert yamlio.load_text(f"v: {word}\n") == {"v": word}


@pytest.mark.parametrize(("word", "value"), [("true", True), ("False", False), ("TRUE", True)])
def test_true_and_false_are_booleans(word, value):
    assert yamlio.load_text(f"v: {word}\n") == {"v": value}


def test_duplicate_keys_are_errors():
    with pytest.raises(YamlError, match=r"duplicate key 'a' \(line 3\)"):
        yamlio.load_text("a: 1\nb: 2\na: 3\n")


def test_nested_duplicate_keys_are_errors():
    with pytest.raises(YamlError, match="duplicate key 'x'"):
        yamlio.load_text("outer:\n  x: 1\n  x: 2\n")


def test_aliases_are_errors():
    with pytest.raises(YamlError, match="aliases are not allowed"):
        yamlio.load_text("a: &anchor [1, 2]\nb: *anchor\n")


def test_merge_keys_are_errors():
    with pytest.raises(YamlError):
        yamlio.load_text("base: &b {x: 1}\nchild:\n  <<: *b\n")
    with pytest.raises(YamlError, match="merge keys"):
        yamlio.load_text("child:\n  <<: {x: 1}\n")


def test_non_string_keys_are_errors():
    with pytest.raises(YamlError, match="not a string"):
        yamlio.load_text("1: one\n")


def test_python_tags_are_rejected():
    with pytest.raises(YamlError):
        yamlio.load_text("x: !!python/object/apply:os.system ['echo hi']\n")


def test_syntax_error_names_the_source():
    with pytest.raises(YamlError, match=r"rules\.yaml"):
        yamlio.load_text("a: [1, 2\n", source="rules.yaml")


def test_load_file_utf8_and_bom(tmp_path):
    path = tmp_path / "x.yaml"
    path.write_bytes("﻿name: 发热\n".encode())
    assert yamlio.load_file(path) == {"name": "发热"}


def test_load_file_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "x.yaml"
    path.write_bytes(b"name: \xff\n")
    with pytest.raises(YamlError, match="not valid UTF-8"):
        yamlio.load_file(path)


def test_load_file_size_limit(tmp_path):
    path = tmp_path / "big.yaml"
    path.write_text("a: " + "x" * 100 + "\n", encoding="utf-8")
    with pytest.raises(YamlError, match="limit is 50"):
        yamlio.load_file(path, max_bytes=50)
    assert yamlio.load_file(path, max_bytes=200) == {"a": "x" * 100}


def test_errors_in_files_name_the_path(tmp_path):
    path = tmp_path / "dup.yaml"
    path.write_text("a: 1\na: 2\n", encoding="utf-8")
    with pytest.raises(YamlError, match=r"dup\.yaml"):
        yamlio.load_file(path)
