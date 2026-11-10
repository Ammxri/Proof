"""MR6 round trip (A-39): numbers shown in an alternative unit, read back, must keep the value of every rule.

A reader of an MR6 text sees rounded numbers in another unit, and for lab facts a reference range rounded in the same
way. :func:`read_back` turns both into canonical units exactly as shown; :func:`flipped_rules` evaluates every active
rule on them and names the rules whose truth value differs from the one on the base case's facts. A variant with any
such rule is discarded and counted, because its "unchanged" expectation would be wrong (RK-11).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from proof.render.case_text import shown_reference
from proof.render.units import alt_unit, back, shown
from proof_rules.engine import infer, infer_rules
from proof_rules.model import Domain, RefRange


def read_back(
    domain: Domain, facts: Mapping[str, Any], units: Mapping[str, str]
) -> tuple[dict[str, Any], dict[str, RefRange]]:
    """Facts and reference ranges in canonical units as a text with ``units`` shows them."""
    read_facts = dict(facts)
    references = dict(domain.references)
    for code, unit in sorted(units.items()):
        field = domain.catalog.get(code)
        if field is None:
            raise ValueError(f"{code}: not a field of domain {domain.name}")
        alt = alt_unit(field, unit)
        read_facts[code] = float(back(shown(facts[code], alt), alt))
        reference = domain.references.get(code)
        if reference is not None:
            lower, upper = shown_reference(reference, alt)
            # Rounded limits are read as shown, even where rounding brings them together; the rules decide.
            references[code] = RefRange.model_construct(
                lower=None if lower is None else float(back(lower, alt)),
                upper=None if upper is None else float(back(upper, alt)),
            )
    return read_facts, references


def flipped_rules(domain: Domain, facts: Mapping[str, Any], units: Mapping[str, str]) -> tuple[str, ...]:
    """Ids of the rules whose truth value the converted text changes; empty if every rule keeps its value."""
    original = infer(domain, facts).rules
    read_facts, references = read_back(domain, facts, units)
    read = infer_rules(domain.rules, references, read_facts).rules
    return tuple(rule for rule, truth in original.items() if read[rule] is not truth)
