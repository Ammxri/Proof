"""System prompt and messages of a test run (A-12, PR-P01).

The system prompt of a domain and language names the answer format and every allowed code: differential diagnoses,
red flags and the field codes for questions and contradictions. The user message is the case text. Proof uses neither
a JSON mode nor structured output of a provider (A-38): the model is told the format in plain text.
"""

from __future__ import annotations

from proof.render.templating import PROMPT_TEMPLATE, render_template
from proof_rules.model import Domain


def system_prompt(domain: Domain, lang: str) -> str:
    """The system prompt of ``domain`` in ``lang``."""
    context = {
        "complaint": getattr(domain.complaint_labels, lang),
        "ddx": [{"code": term.code, "label": getattr(term.labels, lang)} for term in domain.vocabulary.ddx],
        "red_flags": [{"code": term.code, "label": getattr(term.labels, lang)} for term in domain.vocabulary.red_flags],
        "fields": [
            {"code": field.code, "name": getattr(field.labels, lang).name, "abbr": getattr(field.labels, lang).abbr}
            for field in domain.catalog.fields
        ],
    }
    return render_template(lang, PROMPT_TEMPLATE, context)


def messages(system: str, case_text: str) -> list[dict[str, str]]:
    """The chat messages of one unit: the system prompt, then the case text as the user message."""
    return [{"role": "system", "content": system}, {"role": "user", "content": case_text}]
