"""Deterministic random streams derived from SHA-256 (A-06).

A stream is identified by a list of labels, for example ``Stream("fever", "case", 123)``. Its key is
``SHA-256(b"proof-rng-v1\\x00" + canonical_json(labels))``; block ``i`` of the stream is ``SHA-256(key + i as 8-byte
big-endian)``. Bits are taken from the blocks in order, most significant first. Only integer arithmetic is used, so the
same labels yield the same numbers on every platform and Python version. The ``random`` module is never used.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import TypeVar

from proof.core import canonical

T = TypeVar("T")

DOMAIN = b"proof-rng-v1\x00"
_BLOCK_BITS = 256


def _validate_labels(labels: tuple[str | int, ...]) -> list[str | int]:
    if not labels:
        raise ValueError("a stream needs at least one label")
    for label in labels:
        if isinstance(label, bool) or not isinstance(label, str | int):
            raise TypeError(f"stream labels must be str or int, not {type(label).__name__}")
    return list(labels)


class Stream:
    """A reproducible source of random integers."""

    __slots__ = ("_bits", "_counter", "_key", "_pool")

    def __init__(self, *labels: str | int) -> None:
        self._key = hashlib.sha256(DOMAIN + canonical.dumps_bytes(_validate_labels(labels))).digest()
        self._counter = 0
        self._pool = 0
        self._bits = 0

    @classmethod
    def _from_key(cls, key: bytes) -> Stream:
        stream = cls.__new__(cls)
        stream._key = key
        stream._counter = 0
        stream._pool = 0
        stream._bits = 0
        return stream

    def child(self, *labels: str | int) -> Stream:
        """An independent sub-stream; it depends only on this stream's key and ``labels``, not on consumed bits."""
        key = hashlib.sha256(self._key + canonical.dumps_bytes(_validate_labels(labels))).digest()
        return Stream._from_key(key)

    def _refill(self) -> None:
        block = hashlib.sha256(self._key + self._counter.to_bytes(8, "big")).digest()
        self._counter += 1
        self._pool = (self._pool << _BLOCK_BITS) | int.from_bytes(block, "big")
        self._bits += _BLOCK_BITS

    def bits(self, count: int) -> int:
        """The next ``count`` bits as a non-negative integer."""
        if count < 0:
            raise ValueError("count must not be negative")
        while self._bits < count:
            self._refill()
        self._bits -= count
        value = self._pool >> self._bits
        self._pool &= (1 << self._bits) - 1
        return value

    def below(self, limit: int) -> int:
        """A uniform integer in ``[0, limit)``, by rejection sampling without bias."""
        if limit <= 0:
            raise ValueError("limit must be positive")
        if limit == 1:
            return 0
        width = (limit - 1).bit_length()
        while True:
            value = self.bits(width)
            if value < limit:
                return value

    def integer(self, low: int, high: int) -> int:
        """A uniform integer in ``[low, high]``."""
        if high < low:
            raise ValueError("high must not be smaller than low")
        return low + self.below(high - low + 1)

    def chance(self, numerator: int, denominator: int) -> bool:
        """True with probability ``numerator / denominator``."""
        if denominator <= 0 or not 0 <= numerator <= denominator:
            raise ValueError("need 0 <= numerator <= denominator and denominator > 0")
        return self.below(denominator) < numerator

    def choice(self, items: Sequence[T]) -> T:
        """A uniformly chosen element of a non-empty sequence."""
        if not items:
            raise ValueError("cannot choose from an empty sequence")
        return items[self.below(len(items))]

    def weighted_index(self, weights: Sequence[int]) -> int:
        """An index chosen with probability proportional to its integer weight."""
        if not weights:
            raise ValueError("weights must not be empty")
        if any(isinstance(w, bool) or not isinstance(w, int) or w < 0 for w in weights):
            raise ValueError("weights must be non-negative integers")
        total = sum(weights)
        if total == 0:
            raise ValueError("at least one weight must be positive")
        target = self.below(total)
        for index, weight in enumerate(weights):
            if target < weight:
                return index
            target -= weight
        raise AssertionError("unreachable")  # pragma: no cover

    def shuffled(self, items: Sequence[T]) -> list[T]:
        """A new list with the elements in random order (Fisher-Yates)."""
        result = list(items)
        for i in range(len(result) - 1, 0, -1):
            j = self.below(i + 1)
            result[i], result[j] = result[j], result[i]
        return result
