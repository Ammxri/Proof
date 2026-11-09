"""Text of a variant in one language (A-74): its facts with the base case's patient, in the variant's order."""

from __future__ import annotations

from proof.cases.model import Case
from proof.render.case_text import RenderError, Rendering, render_facts
from proof.variants.model import LanguagePair, Variant
from proof_rules.model import Domain


def render_variant(variant: Variant, base: Case, domain: Domain, lang: str) -> Rendering:
    """The text a model receives for ``variant`` in ``lang``.

    MR5 has no text of its own: it compares the answers to the base case in two languages (A-37).
    """
    if variant.case_id != base.case_id:
        raise RenderError([f"{variant.variant_id} belongs to {variant.case_id}, not {base.case_id}"])
    if isinstance(variant.change, LanguagePair):
        raise RenderError([f"{variant.variant_id}: MR5 compares the base case in two languages and has no text"])
    return render_facts(domain, lang, base.patient, variant.facts, order=variant.render.order)
