"""Case text in zh, en and de (PR-F05, PR-W02, PR-K01, PR-D01).

A case is a set of coded facts; its text is only a rendering of them (PR-K01). The text follows the prototype's long
form: a header with patient and complaint, then the four sections history, examination, vital signs and laboratory,
one line per fact. Assessment, differential diagnoses and next steps of the long form are left out, because they would
be the solution (A-11). Lab facts with a reference range from their profile show it, as a lab report does (A-70).

Every rendering records where each fact appears: ``spans`` maps a fact code to its character range in the text. A
fact without a span, a span without a fact, or any marker left in the text is an error.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Any

from proof.cases.model import Case, Patient
from proof.render.templating import CASE_TEMPLATE, SECTIONS, Strings, check_language, render_template, strings
from proof_rules.model import Domain, FieldDef, RefRange

BEGIN, SEPARATOR, END = "", "", ""
_PRIVATE_USE = re.compile("[-]")


class RenderError(ValueError):
    """Facts or options cannot be rendered; ``problems`` lists every finding."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(self.problems))


@dataclass(frozen=True)
class Rendering:
    """The text of a case in one language and where each fact appears in it (character offsets, end exclusive)."""

    lang: str
    text: str
    spans: Mapping[str, tuple[int, int]]
    order: tuple[str, ...]

    def fact_text(self, code: str) -> str:
        start, end = self.spans[code]
        return self.text[start:end]


# --- Numbers and values ----------------------------------------------------------------------------------------------


def format_number(value: int | float, decimals: int, separator: str) -> str:
    """``value`` with exactly ``decimals`` places and the language's decimal separator, computed exactly."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RenderError([f"{value!r} is not a number"])
    scaled = Fraction(str(value)) * 10**decimals
    if scaled.denominator != 1:
        raise RenderError([f"{value} has more than {decimals} decimal places"])
    units = scaled.numerator
    sign = "-" if units < 0 else ""
    whole, fraction = divmod(abs(units), 10**decimals)
    if decimals == 0:
        return f"{sign}{whole}"
    return f"{sign}{whole}{separator}{fraction:0{decimals}d}"


def format_plain(value: int | float, separator: str) -> str:
    """A number with as many decimal places as its shortest form has, e.g. a reference limit ``0.7`` or ``10``."""
    exponent = Decimal(str(value)).as_tuple().exponent
    decimals = -exponent if isinstance(exponent, int) and exponent < 0 else 0
    return format_number(value, decimals, separator)


def unit_display(unit: str, table: Strings, lang: str) -> str:
    if unit not in table.units:
        raise RenderError([f"no display for unit {unit!r} in templates/{lang}/strings.yaml"])
    return table.units[unit]


def format_value(field: FieldDef, value: Any, lang: str) -> str:
    """The text of a fact value: yes/no, the label of an enum value, or the number with its unit."""
    table = strings(lang)
    if field.type == "bool":
        return table.bool_true if value else table.bool_false
    if field.type == "enum":
        return getattr(field.value_labels[value], lang)
    assert field.unit is not None  # noqa: S101 - numeric fields always have a unit (catalog model)
    number = format_number(value, field.decimals or 0, table.decimal_separator)
    return number + unit_display(field.unit, table, lang)


def format_reference(field: FieldDef, reference: RefRange, lang: str) -> str:
    """A reference range such as ``0–10 mg/L``; an open side becomes ``≤ upper`` or ``≥ lower``."""
    table = strings(lang)
    assert field.unit is not None  # noqa: S101 - only numeric lab fields have reference ranges
    unit = unit_display(field.unit, table, lang)
    separator = table.decimal_separator
    if reference.lower is not None and reference.upper is not None:
        return f"{format_plain(reference.lower, separator)}–{format_plain(reference.upper, separator)}{unit}"
    if reference.upper is not None:
        return f"≤ {format_plain(reference.upper, separator)}{unit}"
    assert reference.lower is not None  # noqa: S101 - a reference range has at least one side (model)
    return f"≥ {format_plain(reference.lower, separator)}{unit}"


# --- Rendering -------------------------------------------------------------------------------------------------------


def _begin(code: str) -> str:
    return f"{BEGIN}{code}{SEPARATOR}"


def _end() -> str:
    return END


def _extract(raw: str) -> tuple[str, dict[str, tuple[int, int]]]:
    out: list[str] = []
    spans: dict[str, tuple[int, int]] = {}
    open_code: str | None = None
    start = 0
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == BEGIN:
            stop = raw.find(SEPARATOR, index)
            if stop < 0 or open_code is not None:
                raise RenderError(["the template nests or breaks a fact marker"])
            open_code, start = raw[index + 1 : stop], len(out)
            index = stop + 1
            continue
        if char == END:
            if open_code is None or open_code in spans:
                raise RenderError([f"the template closes a fact marker it did not open ({open_code})"])
            spans[open_code] = (start, len(out))
            open_code = None
            index += 1
            continue
        out.append(char)
        index += 1
    if open_code is not None:
        raise RenderError([f"the template leaves the marker of {open_code} open"])
    return "".join(out), spans


def check_order(order: Sequence[str]) -> tuple[str, ...]:
    """The section order as a tuple; it must be a permutation of the four sections (MR3)."""
    if sorted(order) != sorted(SECTIONS) or len(order) != len(SECTIONS):
        raise RenderError([f"section order must be a permutation of {', '.join(SECTIONS)}, got {', '.join(order)}"])
    return tuple(order)


def render_facts(
    domain: Domain,
    lang: str,
    patient: Patient,
    facts: Mapping[str, Any],
    *,
    order: Sequence[str] = SECTIONS,
) -> Rendering:
    """The text of the given facts in ``lang``; facts may be a subset of the catalog (variants with gaps)."""
    check_language(lang)
    sections_order = check_order(order)
    problems = domain.fact_problems(facts)
    if problems:
        raise RenderError(problems)
    table = strings(lang)
    sections = []
    for section in sections_order:
        lines = []
        for field in domain.catalog.fields:
            if field.section != section or field.code not in facts:
                continue
            label = getattr(field.labels, lang)
            reference = domain.references.get(field.code)
            lines.append(
                {
                    "code": field.code,
                    "name": label.name,
                    "abbr": label.abbr,
                    "value": format_value(field, facts[field.code], lang),
                    "reference": None if reference is None else format_reference(field, reference, lang),
                }
            )
        sections.append({"key": section, "heading": getattr(table.sections, section), "facts": lines})
    context = {
        "t": table.model_dump(),
        "patient": {"age": patient.age, "sex": patient.sex},
        "complaint": getattr(domain.complaint_labels, lang),
        "sections": sections,
        "begin": _begin,
        "end": _end,
    }
    text, spans = _extract(render_template(lang, CASE_TEMPLATE, context))
    problems = []
    if set(spans) != set(facts):
        problems.append(f"facts and marked text differ: {sorted(set(spans) ^ set(facts))}")
    if _PRIVATE_USE.search(text):
        problems.append("the text contains private-use characters")
    if unicodedata.normalize("NFC", text) != text:
        problems.append("the text is not NFC-normalised")
    if problems:
        raise RenderError(problems)
    return Rendering(lang=lang, text=text, spans=MappingProxyType(dict(sorted(spans.items()))), order=sections_order)


def render_case(case: Case, domain: Domain, lang: str, *, order: Sequence[str] = SECTIONS) -> Rendering:
    """The text of a case in ``lang``."""
    if case.complaint != domain.complaint:
        raise RenderError([f"{case.case_id}: complaint {case.complaint!r} does not belong to domain {domain.name}"])
    return render_facts(domain, lang, case.patient, case.facts, order=order)
