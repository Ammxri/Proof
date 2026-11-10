"""Text of a variant in one language (A-74): its facts with the base case's patient, in the variant's order.

MR4 adds the lines of its irrelevant facts, MR6 shows its notation and MR7 adds the line of its contradiction, all
from the domain's catalog in that language.
"""

from __future__ import annotations

from proof.cases.model import Case
from proof.render.case_text import ExtraLine, RenderError, Rendering, render_facts
from proof.variants.model import AddFacts, ChangeNotation, InsertContradiction, LanguagePair, Variant
from proof_rules.model import Domain


def extra_lines(variant: Variant, domain: Domain, lang: str) -> list[ExtraLine]:
    """The lines MR4 and MR7 add, in ``lang``."""
    change = variant.change
    if isinstance(change, AddFacts):
        lines = []
        for code in change.facts:
            fact = domain.catalog.irrelevant_fact(code)
            if fact is None:
                raise RenderError([f"{variant.variant_id}: {code} is no irrelevant fact of domain {domain.name}"])
            label = getattr(fact.labels, lang)
            lines.append(ExtraLine(key=fact.code, section=fact.section, name=label.name, value=label.value))
        return lines
    if isinstance(change, InsertContradiction):
        template = domain.catalog.contradiction(change.template)
        if template is None or template.field != change.field:
            raise RenderError([f"{variant.variant_id}: no contradiction {change.template} on {change.field}"])
        label = getattr(template.labels, lang)
        return [ExtraLine(key=template.id, section=template.section, name=label.name, value=label.value)]
    return []


def render_variant(variant: Variant, base: Case, domain: Domain, lang: str) -> Rendering:
    """The text a model receives for ``variant`` in ``lang``.

    MR5 has no text of its own: it compares the answers to the base case in two languages (A-37).
    """
    if variant.case_id != base.case_id:
        raise RenderError([f"{variant.variant_id} belongs to {variant.case_id}, not {base.case_id}"])
    if isinstance(variant.change, LanguagePair):
        raise RenderError([f"{variant.variant_id}: MR5 compares the base case in two languages and has no text"])
    notation = variant.change if isinstance(variant.change, ChangeNotation) else None
    return render_facts(
        domain,
        lang,
        base.patient,
        variant.facts,
        order=variant.render.order,
        units=notation.units if notation is not None else {},
        abbreviations=notation.abbreviations if notation is not None else False,
        extra=extra_lines(variant, domain, lang),
    )
