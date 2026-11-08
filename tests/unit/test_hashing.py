"""SHA-256 helpers."""

from __future__ import annotations

import hashlib

from proof.core import hashing


def test_known_digests():
    assert hashing.sha256_bytes(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    assert hashing.sha256_text("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_json_hash_is_hash_of_canonical_bytes():
    value = {"b": [1, 2], "a": "发热"}
    expected = hashlib.sha256('{"a":"发热","b":[1,2]}'.encode()).hexdigest()
    assert hashing.sha256_json(value) == expected
    assert hashing.sha256_json({"a": "发热", "b": [1, 2]}) == expected


def test_file_hash_matches_bytes_hash(tmp_path):
    data = bytes(range(256)) * 9000
    path = tmp_path / "data.bin"
    path.write_bytes(data)
    assert hashing.sha256_file(path) == hashlib.sha256(data).hexdigest()
    empty = tmp_path / "empty"
    empty.write_bytes(b"")
    assert hashing.sha256_file(empty) == hashing.sha256_bytes(b"")
