"""Plain-text explanation of a key: facts, every rule with its evaluation tree, targets, key and ablation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from proof_rules.ablation import ablation_table
from proof_rules.engine import Outcome, infer
from proof_rules.keys import compute_key
from proof_rules.logic import trace, trace_lines
from proof_rules.model import Domain

KEY_FIELDS = ("determinability", "red_flags", "critical_fields", "ddx")


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _codes(codes: Any) -> str:
    return ", ".join(codes) if codes else "-"


def _outcome(result: Outcome) -> str:
    return f"{result.determinability} | red_flags: {_codes(result.red_flags)} | ddx: {_codes(result.ddx)}"


def explain(domain: Domain, facts: Mapping[str, Any], stored_key: Mapping[str, Any] | None = None) -> list[str]:
    """Explanation lines; raises :class:`proof_rules.keys.FactError` for invalid facts."""
    key = compute_key(domain, facts)
    inference = infer(domain, facts)
    lines = [f"domain: {domain.name} (case prefix {domain.case_prefix}, complaint {domain.complaint})", "facts:"]
    lines += [f"  {code} = {_value(facts[code])}" for code in sorted(facts)] or ["  -"]
    lines.append("rules:")
    for rule in domain.rules:
        lines.append(f"  {rule.id} {rule.kind} -> {rule.target}: {inference.rules[rule.id]}")
        lines += trace_lines(trace(rule.when, facts, domain.references), indent=2)
    lines.append("targets:")
    lines += [f"  {target}: {truth}" for target, truth in inference.targets.items()] or ["  -"]
    lines += [
        "key:",
        f"  determinability: {key.determinability}",
        f"  red_flags: {_codes(key.red_flags)}",
        f"  critical_fields: {_codes(key.critical_fields)}",
        f"  ddx: {_codes(key.ddx)}",
        "ablation (outcome without each field):",
    ]
    for code, result in ablation_table(domain, facts):
        status = "changed, critical" if result != inference.outcome else "unchanged"
        lines.append(f"  {code}: {_outcome(result)} ({status})")
    if not facts:
        lines.append("  -")
    if stored_key is not None:
        computed = key.model_dump(mode="json")
        differing = [name for name in KEY_FIELDS if stored_key.get(name) != computed[name]]
        unknown = sorted(set(stored_key) - set(KEY_FIELDS))
        if unknown:
            differing.append(f"unexpected entries {', '.join(unknown)}")
        lines.append("stored key: matches" if not differing else f"stored key: differs in {', '.join(differing)}")
    return lines
