"""Three-valued logic: truth tables of every operator and connective (U2 DoD)."""

from __future__ import annotations

import itertools

import pytest

from proof_rules.logic import (
    MissingReferenceError,
    Truth,
    compare_values,
    describe,
    evaluate,
    t_and,
    t_at_least,
    t_not,
    t_or,
    trace,
    trace_lines,
)
from proof_rules.model import Compare, RefRange, Rule

T, F, U = Truth.TRUE, Truth.FALSE, Truth.UNKNOWN
ALL = (T, F, U)


def _completions(values):
    """Every two-valued completion of a tuple of truth values."""
    options = [(True, False) if value is U else (value is T,) for value in values]
    return list(itertools.product(*options))


def _supervaluation(values, function):
    results = {function(completion) for completion in _completions(values)}
    if results == {True}:
        return T
    if results == {False}:
        return F
    return U


def test_not_truth_table():
    assert (t_not(T), t_not(F), t_not(U)) == (F, T, U)


@pytest.mark.parametrize("values", list(itertools.product(ALL, repeat=2)) + list(itertools.product(ALL, repeat=3)))
def test_and_or_match_kleene(values):
    assert t_and(values) is _supervaluation(values, all)
    assert t_or(values) is _supervaluation(values, any)


def test_and_or_tables_written_out():
    table_and = {(T, T): T, (T, F): F, (T, U): U, (F, F): F, (F, U): F, (U, U): U}
    table_or = {(T, T): T, (T, F): T, (T, U): T, (F, F): F, (F, U): U, (U, U): U}
    for (a, b), expected in table_and.items():
        assert t_and((a, b)) is expected and t_and((b, a)) is expected
    for (a, b), expected in table_or.items():
        assert t_or((a, b)) is expected and t_or((b, a)) is expected


@pytest.mark.parametrize("values", list(itertools.product(ALL, repeat=3)))
@pytest.mark.parametrize("count", [1, 2, 3])
def test_at_least_matches_every_completion(values, count):
    assert t_at_least(count, values) is _supervaluation(values, lambda c: sum(c) >= count)


def test_qsofa_style_at_least_examples():
    assert t_at_least(2, (T, T, U)) is T
    assert t_at_least(2, (T, U, F)) is U
    assert t_at_least(2, (U, U, F)) is U
    assert t_at_least(2, (T, F, F)) is F
    assert t_at_least(2, (U, F, F)) is F


@pytest.mark.parametrize(
    ("op", "actual", "expected", "result"),
    [
        ("eq", 5, 5, True),
        ("eq", 5, 6, False),
        ("ne", 5, 6, True),
        ("ne", 5, 5, False),
        ("lt", 4, 5, True),
        ("lt", 5, 5, False),
        ("le", 5, 5, True),
        ("le", 6, 5, False),
        ("gt", 6, 5, True),
        ("gt", 5, 5, False),
        ("ge", 5, 5, True),
        ("ge", 4.9, 5, False),
        ("in", "a", ("a", "b"), True),
        ("in", "c", ("a", "b"), False),
        ("eq", "altered", "altered", True),
        ("eq", True, True, True),
        ("eq", False, True, False),
    ],
)
def test_comparison_truth_table(op, actual, expected, result):
    assert compare_values(op, actual, expected) is result
    condition = Compare(field="vital.x", op=op, value=expected)
    assert evaluate(condition, {"vital.x": actual}, {}) is Truth.of(result)
    assert evaluate(condition, {}, {}) is U, "a missing fact makes every comparison unknown"


def test_bool_never_equals_integer():
    assert compare_values("eq", True, 1) is False
    assert compare_values("ne", True, 1) is True
    assert compare_values("in", 1, (True,)) is False
    with pytest.raises(TypeError):
        compare_values("lt", True, 2)
    with pytest.raises(ValueError, match="unknown op"):
        compare_values("between", 1, 2)


def test_reference_thresholds():
    condition = Compare(field="lab.crp_mg_l", op="gt", value={"ref": "upper"})
    references = {"lab.crp_mg_l": RefRange(lower=0, upper=5)}
    assert evaluate(condition, {"lab.crp_mg_l": 6}, references) is T
    assert evaluate(condition, {"lab.crp_mg_l": 5}, references) is F
    assert evaluate(condition, {}, references) is U
    low = Compare(field="lab.crp_mg_l", op="lt", value={"ref": "lower"})
    with pytest.raises(MissingReferenceError, match="lower reference limit"):
        evaluate(low, {"lab.crp_mg_l": 1}, {"lab.crp_mg_l": RefRange(upper=5)})
    with pytest.raises(MissingReferenceError):
        evaluate(condition, {"lab.crp_mg_l": 6}, {})


def _rule(when, requires):
    return Rule.model_validate(
        {
            "id": "TST-RF-001",
            "kind": "red_flag",
            "target": "rf.test",
            "requires": requires,
            "when": when,
            "sources": [{"ref": "SRC-0001", "locator": "x"}],
            "status": "draft_unreviewed",
            "tests": [{"facts": {}, "expect": True}, {"facts": {}, "expect": False}],
        }
    )


def test_nested_connectives_and_trace():
    rule = _rule(
        {
            "any": [
                {
                    "all": [
                        {"field": "hx.a", "op": "eq", "value": True},
                        {"not": {"field": "hx.b", "op": "eq", "value": True}},
                    ]
                },
                {"at_least": 1, "of": [{"field": "vital.c", "op": "in", "value": [1, 2]}]},
            ]
        },
        ["hx.a", "hx.b", "vital.c"],
    )
    assert evaluate(rule.when, {"hx.a": True, "hx.b": False}, {}) is T
    assert evaluate(rule.when, {"hx.a": True}, {}) is U
    assert evaluate(rule.when, {"hx.a": False, "vital.c": 3}, {}) is F
    assert evaluate(rule.when, {"hx.a": False, "vital.c": 2}, {}) is T
    node = trace(rule.when, {"hx.a": True}, {})
    assert node.truth is U
    lines = trace_lines(node)
    assert lines[0] == "any of: unknown"
    assert "  all of: unknown" in lines
    assert "      hx.b eq true (missing): unknown" in lines
    assert "    vital.c in [1, 2] (missing): unknown" in lines


def test_trace_truth_always_equals_evaluate(demo, prd_facts):
    for rule in demo.rules:
        for size in range(len(prd_facts) + 1):
            for subset in itertools.combinations(sorted(prd_facts), size):
                facts = {code: prd_facts[code] for code in subset}
                assert trace(rule.when, facts, demo.references).truth is evaluate(rule.when, facts, demo.references)


def test_describe_reference_and_connectives():
    assert describe(Compare(field="lab.x", op="ge", value={"ref": "lower"})) == "lab.x ge ref.lower"
    rule = _rule({"at_least": 1, "of": [{"field": "hx.a", "op": "eq", "value": False}]}, ["hx.a"])
    assert describe(rule.when) == "at least 1 of"
    with pytest.raises(TypeError):
        describe("not a condition")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        evaluate("not a condition", {}, {})  # type: ignore[arg-type]
