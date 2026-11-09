"""Constraints from rule conditions (A-66): grid, interval sets, literals and the expansion into terms."""

from __future__ import annotations

import pytest

from proof.cases import constraints
from proof.cases.constraints import ConstraintError, Expander, Intervals, Term
from proof.cases.sampler import load_sampler
from proof.core.rng import Stream
from proof_rules.logic import Truth, evaluate
from proof_rules.model import Compare, FieldDef, RefRange, Rule

I = Intervals  # noqa: E741 - short alias for readability of the cases below


def _field(**changes) -> FieldDef:
    data = {
        "code": "vital.temp_c",
        "section": "vital",
        "type": "number",
        "unit": "°C",
        "decimals": 1,
        "labels": {"zh": {"name": "体温"}, "en": {"name": "T"}, "de": {"name": "T"}},
    }
    data.update(changes)
    return FieldDef.model_validate(data)


TEMP = _field()
LACTATE = _field(code="lab.lactate_mmol_l", section="lab", unit="mmol/L")
RATE = _field(code="vital.resp_rate", type="int", unit="/min", decimals=None)
COUGH = _field(code="hx.cough", section="hx", type="bool", unit=None, decimals=None)
MENTAL = _field(
    code="vital.mental_status",
    type="enum",
    unit=None,
    decimals=None,
    values=["normal", "altered"],
    value_labels={v: {"zh": v, "en": v, "de": v} for v in ("normal", "altered")},
)
FIELDS = {field.code: field for field in (TEMP, LACTATE, RATE, COUGH, MENTAL)}


def _compare(field: str, op: str, value) -> Compare:
    return Compare.model_validate({"field": field, "op": op, "value": value})


def _expander(references=None) -> Expander:
    return Expander(FIELDS, references or {})


def test_grid_conversion_is_exact():
    assert constraints.units_of(TEMP, 39.2) == 392
    assert constraints.value_of(TEMP, 392) == 39.2
    assert constraints.value_of(TEMP, 380) == 38.0
    assert isinstance(constraints.value_of(TEMP, 380), float)
    assert constraints.units_of(LACTATE, 0.7) == 7
    assert constraints.value_of(RATE, 22) == 22
    assert isinstance(constraints.value_of(RATE, 22), int)
    assert isinstance(constraints.value_of(_field(decimals=0), 81), int)
    with pytest.raises(ConstraintError, match="not on the grid"):
        constraints.units_of(TEMP, 39.25)
    with pytest.raises(ConstraintError, match="not a number"):
        constraints.units_of(TEMP, True)


def test_interval_sets():
    assert I.of([(5, 9), (1, 3), (4, 4), (12, None)]) == I(((1, 9), (12, None)))
    assert I.of([(None, 2), (1, 5)]) == I(((None, 5),))
    assert I.of([(3, 1)]).is_empty()
    assert I.everything().complement() == I.nothing()
    assert I.nothing().complement() == I.everything()
    assert I(((1, 3), (5, None))).complement() == I(((None, 0), (4, 4)))
    assert I(((None, 0), (4, 4))).complement() == I(((1, 3), (5, None)))
    assert I(((1, 9),)).intersect(I(((None, 2), (8, None)))) == I(((1, 2), (8, 9)))
    assert I.point(4).union(I.point(5)) == I(((4, 5),))
    members = I(((1, 2), (5, 7), (10, None)))
    assert members.count_in(0, 11) == 7
    assert [members.nth_in(0, 11, i) for i in range(7)] == [1, 2, 5, 6, 7, 10, 11]
    with pytest.raises(IndexError):
        members.nth_in(0, 11, 7)
    assert constraints.describe(members) == "[1, 2] or [5, 7] or [10, ∞]"
    assert constraints.describe(I.nothing()) == "empty"
    assert constraints.describe(frozenset({True})) == "{True}"


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        ("gt", 38.0, I(((381, None),))),
        ("ge", 38.0, I(((380, None),))),
        ("lt", 36.0, I(((None, 359),))),
        ("le", 36.0, I(((None, 360),))),
        ("gt", 38.05, I(((381, None),))),  # threshold between two grid points
        ("le", 38.05, I(((None, 380),))),
        ("ge", 37, I(((370, None),))),
        ("eq", 39.2, I.point(392)),
        ("eq", 39.25, I.nothing()),
        ("ne", 39.2, I(((None, 391), (393, None)))),
        ("in", [39.2, 39.3, 40.05], I(((392, 393),))),
    ],
)
def test_numeric_literals_follow_the_engine(op, value, expected):
    compare = _compare("vital.temp_c", op, value)
    allowed = _expander().literal(compare)
    assert allowed == expected
    for units in range(350, 420):
        member = allowed.count_in(units, units) == 1
        assert member == (evaluate(compare, {"vital.temp_c": constraints.value_of(TEMP, units)}, {}) is Truth.TRUE)


def test_values_of_another_type_never_match_a_number():
    assert _expander().literal(_compare("vital.temp_c", "eq", "high")) == I.nothing()
    assert _expander().literal(_compare("vital.temp_c", "ne", True)) == I.everything()


def test_reference_thresholds_are_resolved():
    references = {"lab.lactate_mmol_l": RefRange(lower=0.7, upper=1.8)}
    expander = _expander(references)
    assert expander.literal(_compare("lab.lactate_mmol_l", "gt", {"ref": "upper"})) == I(((19, None),))
    assert expander.literal(_compare("lab.lactate_mmol_l", "lt", {"ref": "lower"})) == I(((None, 6),))
    assert expander.literal(_compare("lab.lactate_mmol_l", "ge", 0.7)) == I(((7, None),))


def test_discrete_literals():
    expander = _expander()
    assert expander.literal(_compare("hx.cough", "eq", True)) == frozenset({True})
    assert expander.literal(_compare("hx.cough", "ne", True)) == frozenset({False})
    assert expander.literal(_compare("vital.mental_status", "in", ["altered"])) == frozenset({"altered"})
    assert expander.domain_of("vital.mental_status") == frozenset({"normal", "altered"})
    with pytest.raises(ConstraintError, match="not a field"):
        expander.literal(_compare("hx.headache", "eq", True))


QSOFA = {
    "at_least": 2,
    "of": [
        {"field": "vital.resp_rate", "op": "ge", "value": 22},
        {"field": "vital.mental_status", "op": "eq", "value": "altered"},
        {"field": "vital.temp_c", "op": "le", "value": 36.0},
    ],
}


def _condition(data):
    rule = Rule.model_validate(
        {
            "id": "T-1",
            "kind": "ddx",
            "target": "ddx.x",
            "requires": sorted(_fields(data)),
            "when": data,
            "sources": [{"ref": "SRC-0001", "locator": "x"}],
            "status": "draft_unreviewed",
            "tests": [{"facts": {}, "expect": True}, {"facts": {}, "expect": False}],
        }
    )
    return rule.when


def _fields(data) -> set[str]:
    if "field" in data:
        return {data["field"]}
    parts = data.get("all") or data.get("any") or data.get("of") or [data["not"]]
    return set().union(*(_fields(part) for part in parts))


def test_at_least_expands_into_combinations():
    when = _condition(QSOFA)
    true_terms = _expander().expand(when, True)
    assert [term.fields() for term in true_terms] == [
        ("vital.mental_status", "vital.resp_rate"),
        ("vital.resp_rate", "vital.temp_c"),
        ("vital.mental_status", "vital.temp_c"),
    ]
    false_terms = _expander().expand(when, False)
    assert len(false_terms) == 3
    assert false_terms[0].get("vital.resp_rate") == I(((None, 21),))
    assert false_terms[0].get("vital.mental_status") == frozenset({"normal"})


def test_connectives_and_negation():
    expander = _expander()
    both = _condition({"all": [{"field": "hx.cough", "op": "eq", "value": True}, {"not": QSOFA["of"][0]}]})
    assert [term.constraints for term in expander.expand(both, True)] == [
        (("hx.cough", frozenset({True})), ("vital.resp_rate", I(((None, 21),))))
    ]
    assert len(expander.expand(both, False)) == 2
    either = _condition({"any": [QSOFA["of"][0], QSOFA["of"][2]]})
    assert len(expander.expand(either, True)) == 2
    assert len(expander.expand(either, False)) == 1
    impossible = _condition({"all": [{"field": "vital.temp_c", "op": "gt", "value": 39}, QSOFA["of"][2]]})
    assert expander.expand(impossible, True) == []


def test_terms_conjoin_or_conflict():
    first = Term((("hx.cough", frozenset({True})), ("vital.temp_c", I(((380, None),)))))
    second = Term((("vital.temp_c", I(((None, 390),))),))
    assert first.conjoin(second) == Term((("hx.cough", frozenset({True})), ("vital.temp_c", I(((380, 390),)))))
    assert first.conjoin(Term((("hx.cough", frozenset({False})),))) is None
    assert constraints.product([first], [second, Term((("vital.temp_c", I(((None, 300),))),))]) == [
        first.conjoin(second)
    ]
    assert first.get("hx.headache") is None


def test_the_support_callback_prunes_literals():
    expander = Expander(FIELDS, {}, support=lambda code, allowed: code != "vital.temp_c")
    assert expander.expand(_condition(QSOFA), True) == [
        Term((("vital.mental_status", frozenset({"altered"})), ("vital.resp_rate", I(((22, None),)))))
    ]


def test_too_many_alternatives_are_refused(monkeypatch):
    monkeypatch.setattr(constraints, "MAX_TERMS", 2)
    with pytest.raises(ConstraintError, match="more than 2 alternatives"):
        _expander().expand(_condition(QSOFA), True)


@pytest.mark.parametrize("domain", ["fever", "demo"])
def test_every_term_of_every_rule_decides_the_rule(domain, fixture_packs):
    """Soundness: complete facts that satisfy a term give the rule exactly the wanted truth value."""
    sampler = load_sampler(domain) if domain == "fever" else load_sampler(domain, fixture_packs)
    fields = {field.code: field for field in sampler.domain.catalog.fields}
    expander = Expander(fields, sampler.domain.references)
    distributions = sampler._distributions
    checked = 0
    for rule in sampler.domain.rules:
        for want in (True, False):
            for index, term in enumerate(expander.expand(rule.when, want)):
                if not all(distributions[code].has_mass(term.get(code)) for code in term.fields()):
                    continue
                for repeat in range(5):
                    stream = Stream("test", rule.id, int(want), index, repeat)
                    facts = {
                        code: distributions[code].draw(stream.child(code), term.get(code)) for code in sorted(fields)
                    }
                    assert evaluate(rule.when, facts, sampler.domain.references) is Truth.of(want), (rule.id, term)
                    checked += 1
    assert checked > 0
