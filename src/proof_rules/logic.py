"""Three-valued (Kleene) evaluation of rule conditions.

A fact that is missing makes every comparison on it ``unknown``. Connectives follow strong Kleene logic:
- ``not``: true ↔ false, unknown stays unknown;
- ``all``: false if any part is false, true if all parts are true, otherwise unknown;
- ``any``: true if any part is true, false if all parts are false, otherwise unknown;
- ``at_least k``: true if at least k parts are true, false if fewer than k parts can still become true, otherwise
  unknown.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from proof_rules.model import AllOf, AnyOf, AtLeast, Compare, Condition, Not, RefBound, RefRange, children


class Truth(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

    @classmethod
    def of(cls, value: bool) -> Truth:
        return cls.TRUE if value else cls.FALSE


class MissingReferenceError(LookupError):
    """A condition compares against a reference limit that is not available."""


def t_not(value: Truth) -> Truth:
    if value is Truth.UNKNOWN:
        return value
    return Truth.FALSE if value is Truth.TRUE else Truth.TRUE


def t_and(values: Iterable[Truth]) -> Truth:
    values = tuple(values)
    if Truth.FALSE in values:
        return Truth.FALSE
    if all(value is Truth.TRUE for value in values):
        return Truth.TRUE
    return Truth.UNKNOWN


def t_or(values: Iterable[Truth]) -> Truth:
    values = tuple(values)
    if Truth.TRUE in values:
        return Truth.TRUE
    if all(value is Truth.FALSE for value in values):
        return Truth.FALSE
    return Truth.UNKNOWN


def t_at_least(count: int, values: Iterable[Truth]) -> Truth:
    values = tuple(values)
    true = sum(value is Truth.TRUE for value in values)
    unknown = sum(value is Truth.UNKNOWN for value in values)
    if true >= count:
        return Truth.TRUE
    if true + unknown < count:
        return Truth.FALSE
    return Truth.UNKNOWN


def threshold(compare: Compare, references: Mapping[str, RefRange]) -> Any:
    """The value a comparison compares against, with reference limits resolved."""
    if not isinstance(compare.value, RefBound):
        return compare.value
    reference = references.get(compare.field)
    limit = None if reference is None else getattr(reference, compare.value.ref)
    if limit is None:
        raise MissingReferenceError(f"no {compare.value.ref} reference limit for {compare.field}")
    return limit


def _same_kind(actual: Any, expected: Any) -> bool:
    # bool is a subclass of int in Python; never let true equal 1.
    return isinstance(actual, bool) == isinstance(expected, bool)


def compare_values(op: str, actual: Any, expected: Any) -> bool:
    """Two-valued comparison of a present fact value."""
    if op == "eq":
        return _same_kind(actual, expected) and actual == expected
    if op == "ne":
        return not (_same_kind(actual, expected) and actual == expected)
    if op == "in":
        return any(_same_kind(actual, item) and actual == item for item in expected)
    if isinstance(actual, bool) or isinstance(expected, bool):
        raise TypeError(f"op {op!r} needs numbers")
    if op == "lt":
        return actual < expected
    if op == "le":
        return actual <= expected
    if op == "gt":
        return actual > expected
    if op == "ge":
        return actual >= expected
    raise ValueError(f"unknown op {op!r}")


def evaluate(condition: Condition, facts: Mapping[str, Any], references: Mapping[str, RefRange]) -> Truth:
    """Truth value of ``condition`` for the given facts; missing facts are unknown."""
    if isinstance(condition, Compare):
        if condition.field not in facts:
            return Truth.UNKNOWN
        return Truth.of(compare_values(condition.op, facts[condition.field], threshold(condition, references)))
    if isinstance(condition, AllOf):
        return t_and(evaluate(part, facts, references) for part in condition.all)
    if isinstance(condition, AnyOf):
        return t_or(evaluate(part, facts, references) for part in condition.any)
    if isinstance(condition, Not):
        return t_not(evaluate(condition.negated, facts, references))
    if isinstance(condition, AtLeast):
        return t_at_least(condition.at_least, (evaluate(part, facts, references) for part in condition.of))
    raise TypeError(f"not a condition: {type(condition).__name__}")


@dataclass(frozen=True)
class Trace:
    """Evaluation tree of a condition for explanations: each node with its truth value."""

    condition: Condition
    truth: Truth
    children: tuple[Trace, ...]
    actual: Any = None
    present: bool = False
    threshold: Any = None


def trace(condition: Condition, facts: Mapping[str, Any], references: Mapping[str, RefRange]) -> Trace:
    """Like :func:`evaluate`, but keeps the truth value of every node. Truth values come from :func:`evaluate`."""
    truth = evaluate(condition, facts, references)
    if isinstance(condition, Compare):
        present = condition.field in facts
        return Trace(
            condition=condition,
            truth=truth,
            children=(),
            actual=facts.get(condition.field),
            present=present,
            threshold=threshold(condition, references)
            if present or not isinstance(condition.value, RefBound)
            else None,
        )
    return Trace(condition, truth, tuple(trace(part, facts, references) for part in children(condition)))


def _literal(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, tuple):
        return "[" + ", ".join(_literal(item) for item in value) + "]"
    return str(value)


def describe(condition: Condition) -> str:
    """One-line text of a node, without its sub-conditions."""
    if isinstance(condition, Compare):
        value = condition.value
        shown = f"ref.{value.ref}" if isinstance(value, RefBound) else _literal(value)
        return f"{condition.field} {condition.op} {shown}"
    if isinstance(condition, AllOf):
        return "all of"
    if isinstance(condition, AnyOf):
        return "any of"
    if isinstance(condition, Not):
        return "not"
    if isinstance(condition, AtLeast):
        return f"at least {condition.at_least} of"
    raise TypeError(f"not a condition: {type(condition).__name__}")


def trace_lines(node: Trace, indent: int = 0) -> list[str]:
    """Indented text lines of a trace, one per node."""
    text = describe(node.condition)
    if isinstance(node.condition, Compare):
        detail = f"value {_literal(node.actual)}" if node.present else "missing"
        if isinstance(node.condition.value, RefBound) and node.threshold is not None:
            detail += f", limit {_literal(node.threshold)}"
        text = f"{text} ({detail})"
    lines = [f"{'  ' * indent}{text}: {node.truth}"]
    for child in node.children:
        lines.extend(trace_lines(child, indent + 1))
    return lines
