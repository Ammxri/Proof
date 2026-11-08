"""Deterministic random stream (A-06)."""

from __future__ import annotations

import hashlib
import json
from collections import Counter

import pytest

from proof.core.rng import DOMAIN, Stream


def _golden(repo_root):
    return json.loads((repo_root / "tests/golden/rng_v1.json").read_text(encoding="utf-8"))


def test_first_block_follows_the_documented_derivation():
    key = hashlib.sha256(DOMAIN + b'["spec",42]').digest()
    block0 = hashlib.sha256(key + (0).to_bytes(8, "big")).digest()
    block1 = hashlib.sha256(key + (1).to_bytes(8, "big")).digest()
    stream = Stream("spec", 42)
    assert stream.bits(256) == int.from_bytes(block0, "big")
    assert stream.bits(256) == int.from_bytes(block1, "big")


def test_bits_are_taken_most_significant_first_across_blocks():
    whole = Stream("split").bits(512)
    parts = Stream("split")
    assert (parts.bits(200) << 312) | parts.bits(312) == whole


def test_golden_values(repo_root):
    golden = _golden(repo_root)
    stream = Stream("golden", 1)
    assert [stream.bits(64) for _ in range(3)] == golden["bits64"]
    stream = Stream("golden", 3)
    assert [stream.below(1000) for _ in range(10)] == golden["below_seq_1000"]
    assert Stream("golden", 4).shuffled(list(range(10))) == golden["shuffled_10"]
    stream = Stream("golden", 5)
    assert [stream.weighted_index([1, 2, 7]) for _ in range(10)] == golden["weighted_1_2_7"]
    assert Stream("golden", 6).child("sub", 7).bits(64) == golden["child_bits64"]


def test_same_labels_same_sequence_and_different_labels_differ():
    a, b, c = Stream("fever", "case", 1), Stream("fever", "case", 1), Stream("fever", "case", 2)
    seq_a = [a.below(10**9) for _ in range(20)]
    assert seq_a == [b.below(10**9) for _ in range(20)]
    assert seq_a != [c.below(10**9) for _ in range(20)]


def test_label_types_are_distinguished():
    assert Stream("1").bits(64) != Stream(1).bits(64)


def test_child_does_not_depend_on_consumed_bits():
    fresh = Stream("parent")
    used = Stream("parent")
    used.bits(1000)
    assert fresh.child("x").bits(128) == used.child("x").bits(128)
    assert fresh.child("x").bits(128) != fresh.child("y").bits(128)


@pytest.mark.parametrize("limit", [1, 2, 3, 7, 10, 255, 256, 257, 1000])
def test_below_stays_in_range(limit):
    stream = Stream("range", limit)
    values = [stream.below(limit) for _ in range(500)]
    assert min(values) >= 0
    assert max(values) < limit


def test_below_is_roughly_uniform():
    stream = Stream("uniform")
    counts = Counter(stream.below(6) for _ in range(60_000))
    assert set(counts) == set(range(6))
    assert all(9_400 < n < 10_600 for n in counts.values())


def test_integer_includes_both_bounds():
    stream = Stream("integer")
    values = {stream.integer(-2, 2) for _ in range(500)}
    assert values == {-2, -1, 0, 1, 2}
    assert stream.integer(5, 5) == 5


def test_chance_extremes_and_rate():
    stream = Stream("chance")
    assert not any(stream.chance(0, 7) for _ in range(100))
    assert all(stream.chance(7, 7) for _ in range(100))
    hits = sum(stream.chance(1, 4) for _ in range(40_000))
    assert 9_400 < hits < 10_600


def test_weighted_index_respects_zero_weights_and_proportions():
    stream = Stream("weights")
    counts = Counter(stream.weighted_index([0, 1, 3, 0]) for _ in range(40_000))
    assert set(counts) == {1, 2}
    assert 9_400 < counts[1] < 10_600


def test_shuffled_is_a_permutation_and_leaves_input_alone():
    items = list("abcdefgh")
    result = Stream("shuffle").shuffled(items)
    assert sorted(result) == items
    assert items == list("abcdefgh")
    assert Stream("shuffle").shuffled([]) == []


def test_choice_picks_from_sequence():
    stream = Stream("choice")
    assert {stream.choice(("a", "b", "c")) for _ in range(200)} == {"a", "b", "c"}


def test_bits_zero_and_bit_budget():
    stream = Stream("zero")
    assert stream.bits(0) == 0
    assert stream.bits(1) in (0, 1)


@pytest.mark.parametrize(
    ("call", "error"),
    [
        (lambda: Stream(), ValueError),
        (lambda: Stream(True), TypeError),
        (lambda: Stream(1.5), TypeError),
        (lambda: Stream("x").child(), ValueError),
        (lambda: Stream("x").bits(-1), ValueError),
        (lambda: Stream("x").below(0), ValueError),
        (lambda: Stream("x").integer(3, 2), ValueError),
        (lambda: Stream("x").chance(2, 1), ValueError),
        (lambda: Stream("x").chance(0, 0), ValueError),
        (lambda: Stream("x").choice([]), ValueError),
        (lambda: Stream("x").weighted_index([]), ValueError),
        (lambda: Stream("x").weighted_index([0, 0]), ValueError),
        (lambda: Stream("x").weighted_index([1, -1]), ValueError),
        (lambda: Stream("x").weighted_index([1, True]), ValueError),
        (lambda: Stream("x").weighted_index([1.0]), ValueError),
    ],
)
def test_invalid_arguments(call, error):
    with pytest.raises(error):
        call()
