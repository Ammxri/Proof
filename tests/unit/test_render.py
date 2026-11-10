"""Case text in zh, en and de (PR-F05, PR-W02, PR-K01, PR-D01, A-11, A-70)."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest
from jinja2.exceptions import SecurityError, UndefinedError

from proof.cases.model import Case, Patient
from proof.core import canonical
from proof.core.i18n import LANGUAGES
from proof.render import case_text, templating
from proof.render.case_text import RenderError, format_number, format_plain, render_case, render_facts
from proof_rules import loader
from proof_rules.model import RefRange

FEVER_100 = Path(__file__).resolve().parents[2] / "data" / "collections" / "fever-100" / "cases.jsonl"
# Words of an assessment, differential diagnosis or recommendation; the case text must contain none of them (A-11).
ASSESSMENT_WORDS = {
    "de": ("Einschätzung", "Differenzial", "Diagnose", "Verdacht", "Warnzeichen", "Empfehl", "Nächste Schritte"),
    "en": ("assessment", "differential", "diagnos", "suspect", "red flag", "recommend", "next step"),
    "zh": ("评估", "鉴别", "诊断", "疑似", "危险信号", "建议"),
}


@pytest.fixture(scope="module")
def fever():
    return loader.load_domain("fever")


@pytest.fixture(scope="module")
def cases() -> list[Case]:
    return [Case.model_validate(line) for line in canonical.loads_lines(FEVER_100.read_bytes())]


def _digits(text: str) -> list[str]:
    """The numbers of a text with the decimal comma as point; the unit ×10⁹/L is not a number of the case."""
    return [number.replace(",", ".") for number in re.findall(r"\d+(?:[.,]\d+)?", text.replace("×10⁹", ""))]


@pytest.mark.parametrize(
    ("value", "decimals", "separator", "expected"),
    [
        (39.2, 1, ",", "39,2"),
        (4.0, 1, ".", "4.0"),
        (180, 1, ".", "180.0"),
        (81, 0, ",", "81"),
        (0.7, 2, ",", "0,70"),
        (-0.5, 1, ",", "-0,5"),
        (13260, 0, ".", "13260"),
    ],
)
def test_numbers_are_formatted_exactly(value, decimals, separator, expected):
    assert format_number(value, decimals, separator) == expected


def test_number_formatting_rejects_bad_values():
    with pytest.raises(RenderError, match="more than 1 decimal"):
        format_number(39.25, 1, ".")
    with pytest.raises(RenderError, match="not a number"):
        format_number(True, 0, ".")
    assert format_plain(0.7, ",") == "0,7"
    assert format_plain(10, ".") == "10"
    assert format_plain(1.8, ".") == "1.8"


def test_every_fact_of_every_case_appears_in_every_language(fever, cases):
    """KONZEPT U5: each fact is mapped to its place in the text, in zh, en and de."""
    for case in cases:
        for lang in LANGUAGES:
            rendering = render_case(case, fever, lang)
            assert set(rendering.spans) == set(case.facts), (case.case_id, lang)
            for code, value in case.facts.items():
                field = fever.catalog.get(code)
                piece = rendering.fact_text(code)
                assert getattr(field.labels, lang).name in piece
                assert case_text.format_value(field, value, lang) in piece
            starts = sorted(start for start, _ in rendering.spans.values())
            assert len(set(starts)) == len(starts), "spans never share a start"


def test_texts_hold_no_assessment_diagnosis_or_red_flag(fever, cases):
    """A-11, PR-K01: the text renders facts only; the key stays hidden."""
    for case in cases[:40]:
        for lang in LANGUAGES:
            text = render_case(case, fever, lang).text
            labels = templating.labels(fever, lang)
            for label in (*labels["ddx"].values(), *labels["red_flags"].values()):
                assert label not in text, (case.case_id, lang, label)
            lowered = text.lower()
            for word in ASSESSMENT_WORDS[lang]:
                assert word.lower() not in lowered, (case.case_id, lang, word)
            assert "ddx." not in text and "rf." not in text and "qSOFA" not in text
            assert unicodedata.normalize("NFC", text) == text
            assert not re.search("[-]", text)
            assert text.endswith("\n") and "\r" not in text


def test_the_same_case_has_the_same_content_in_three_languages(fever, cases):
    """PR-D01: one case, three renderings with the same facts and the same numbers."""
    for case in cases[:30]:
        renderings = [render_case(case, fever, lang) for lang in LANGUAGES]
        assert len({tuple(rendering.spans) for rendering in renderings}) == 1
        numbers = [_digits(rendering.text) for rendering in renderings]
        assert numbers[0] == numbers[1] == numbers[2], case.case_id


def test_header_and_sections_follow_the_long_form(fever, cases):
    case = cases[0]
    de = render_case(case, fever, "de").text
    assert de.startswith(f"Patientin, {case.patient.age} Jahre\nVorstellungsgrund: Fieber\n")
    assert [line for line in de.splitlines() if line.startswith("###")] == [
        "### 1. Anamnese",
        "### 2. Befund",
        "### 3. Vitalwerte",
        "### 4. Labor",
    ]
    en = render_case(case, fever, "en").text
    assert en.startswith(f"Female patient, {case.patient.age} years\nPresenting complaint: Fever\n")
    zh = render_case(case, fever, "zh").text
    assert zh.startswith(f"女性患者，{case.patient.age}岁\n主诉：发热\n")
    assert "  • 体温：40.4℃" in zh
    assert "  • Körpertemperatur (T): 40,4 °C" in de
    assert "C-reaktives Protein (CRP): 52,4 mg/l (Referenzbereich 0–10 mg/l)" in de
    assert "Leukozyten (Leuko): 9,1 G/l\n" in de  # no reference range: white cells have no lab profile (A-70)


def test_section_order_can_be_permuted(fever, cases):
    """MR3 needs any order of the four sections; numbering follows the shown order."""
    case = cases[0]
    order = ("lab", "vital", "hx", "exam")
    rendering = render_case(case, fever, "en", order=order)
    assert rendering.order == order
    headings = [line for line in rendering.text.splitlines() if line.startswith("###")]
    assert headings == ["### 1. Laboratory", "### 2. Vital signs", "### 3. History", "### 4. Examination"]
    assert set(rendering.spans) == set(case.facts)
    for bad in (("lab", "vital", "hx"), ("lab", "lab", "hx", "exam"), ("lab", "vital", "hx", "other")):
        with pytest.raises(RenderError, match="permutation"):
            render_case(case, fever, "en", order=bad)


def test_variants_with_missing_facts_render_what_is_left(fever, cases):
    case = cases[0]
    facts = {code: value for code, value in case.facts.items() if not code.startswith("exam.")}
    facts.pop("vital.sbp")
    rendering = render_facts(fever, "de", case.patient, facts)
    assert set(rendering.spans) == set(facts)
    assert "Systolischer Blutdruck" not in rendering.text
    assert "### 2. Befund\n  • keine Angaben\n" in rendering.text


def test_invalid_input_is_refused(fever, cases):
    case = cases[0]
    patient = Patient(age=40, sex="m")
    with pytest.raises(RenderError, match="unknown fact code"):
        render_facts(fever, "de", patient, {"hx.unknown": True})
    with pytest.raises(RenderError, match="outside the physiological bounds"):
        render_facts(fever, "de", patient, {"vital.temp_c": 99.0})
    other = case.model_copy(update={"complaint": "cough"})
    with pytest.raises(RenderError, match="does not belong to domain fever"):
        render_case(other, fever, "de")
    with pytest.raises(templating.TemplateError, match="unknown language"):
        render_case(case, fever, "fr")


def test_every_unit_of_every_domain_has_a_display(fever, fixture_packs):
    domains = [fever, loader.load_domain("demo", fixture_packs)]
    for lang in LANGUAGES:
        table = templating.strings(lang)
        for domain in domains:
            for field in domain.catalog.fields:
                if field.unit is not None:
                    assert field.unit in table.units, (lang, field.unit)
                for alt in field.alt_units:
                    assert alt.unit in table.units, (lang, alt.unit)
    field = fever.catalog.get("vital.temp_c").model_copy(update={"unit": "K"})
    with pytest.raises(RenderError, match="no display for unit 'K'"):
        case_text.format_value(field, 300.0, "de")


def test_markers_must_be_well_formed():
    begin, sep, end = case_text.BEGIN, case_text.SEPARATOR, case_text.END
    text, spans = case_text._extract(f"a {begin}x.a{sep}bc{end} d")
    assert (text, spans) == ("a bc d", {"x.a": (2, 4)})
    for raw in (
        f"{begin}x{sep}{begin}y{sep}{end}{end}",
        f"{end}",
        f"{begin}x{sep}a",
        f"{begin}x",
        f"{begin}x{sep}{end}{end}",
    ):
        with pytest.raises(RenderError):
            case_text._extract(raw)


def test_templates_run_in_a_strict_sandbox():
    environment = templating.environment("de")
    with pytest.raises(SecurityError):
        environment.from_string("{{ ''.__class__.__mro__ }}").render()
    with pytest.raises(UndefinedError):
        templating.render_template("de", templating.CASE_TEMPLATE, {})


def test_template_files_and_tables(fever):
    with pytest.raises(templating.TemplateError, match="unknown template"):
        templating.template_bytes("de", "other.j2")
    for lang in LANGUAGES:
        for name in templating.TEMPLATE_FILES:
            assert templating.template_bytes(lang, name)
        assert templating.strings(lang).decimal_separator == ("," if lang == "de" else ".")
    hashes = templating.template_hashes("zh", [fever])
    assert list(hashes) == [
        "labels/fever/zh",
        "templates/zh/case.j2",
        "templates/zh/strings.yaml",
        "templates/zh/system_prompt.j2",
    ]
    assert hashes == templating.template_hashes("zh", [fever])
    assert hashes["labels/fever/zh"] != templating.template_hashes("de", [fever])["labels/fever/de"]
    labels = templating.labels(fever, "zh")
    assert labels["complaint"] == "发热"
    assert labels["fields"]["vital.mental_status"]["values"] == {"normal": "正常", "altered": "改变"}
    assert canonical.loads(templating.canonical_labels(fever, "zh")) == labels


def test_open_reference_ranges(fever):
    field = fever.catalog.get("lab.crp_mg_l")
    assert case_text.format_reference(field, RefRange(upper=10), "de") == "≤ 10 mg/l"
    assert case_text.format_reference(field, RefRange(lower=0.5), "en") == "≥ 0.5 mg/L"
    assert case_text.format_reference(field, RefRange(lower=0, upper=10), "zh") == "0–10 mg/L"


def test_reference_ranges_in_an_alternative_unit(fever):
    """MR6: the reference range is converted with the value, in the decimals of the alternative unit."""
    field = fever.catalog.get("lab.crp_mg_l")
    alt = field.alt_units[0]
    assert case_text.format_reference(field, RefRange(upper=10), "de", alt) == "≤ 1,00 mg/dl"
    assert case_text.format_reference(field, RefRange(lower=0.5), "en", alt) == "≥ 0.05 mg/dL"
    assert case_text.format_reference(field, RefRange(lower=0, upper=10), "zh", alt) == "0.00–1.00 mg/dL"
    assert case_text.format_value(field, 52.4, "de", alt) == "5,24 mg/dl"
    assert case_text.format_value(fever.catalog.get("hx.cough"), True, "en", alt) == "yes", "only numbers convert"


def test_notation_and_added_lines(fever, cases):
    """MR6 and MR4/MR7 options of render_facts: abbreviations, alternative units, added lines with their spans."""
    case = cases[0]
    extra = [
        case_text.ExtraLine(key="hx.visual_aid", section="hx", name="Sehhilfe", value="Brille"),
        case_text.ExtraLine(key="FEV-MR7-001", section="exam", name="Anmerkung", value="afebril"),
    ]
    rendering = render_facts(
        fever, "de", case.patient, case.facts, units={"vital.temp_c": "°F"}, abbreviations=True, extra=extra
    )
    assert set(rendering.spans) == set(case.facts)
    assert rendering.extra_text("hx.visual_aid") == "Sehhilfe: Brille"
    assert rendering.extra_text("FEV-MR7-001") == "Anmerkung: afebril"
    assert rendering.fact_text("vital.temp_c").startswith("T: ") and rendering.fact_text("vital.temp_c").endswith("°F")
    assert rendering.fact_text("hx.cough").startswith("Husten: "), "no abbreviation, the name stays"
    plain = render_facts(fever, "de", case.patient, case.facts)
    assert plain.extras == {} and render_case(case, fever, "de").text == plain.text


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"units": {"lab.unknown": "mg/dL"}}, "an alternative unit needs a fact of the case"),
        ({"units": {"vital.temp_c": "K"}}, "no alternative unit 'K'"),
        ({"units": {"vital.sbp": "kPa"}}, r"no alternative unit 'kPa' \(available: none\)"),
        ({"extra": [case_text.ExtraLine("hx.x", "history", "a", "b")]}, "unknown section 'history'"),
        ({"extra": [case_text.ExtraLine("hx.x", "hx", "a", "b")] * 2}, "added lines need distinct keys"),
        ({"extra": [case_text.ExtraLine("hx.cough", "hx", "a", "b")]}, "needs a key of its own"),
        ({"extra": [case_text.ExtraLine("", "hx", "a", "b")]}, "needs a key of its own"),
        ({"extra": [case_text.ExtraLine(f"a{case_text.END}", "hx", "a", "b")]}, "needs a key of its own"),
    ],
)
def test_bad_notation_or_lines_are_refused(fever, cases, options, message):
    case = cases[0]
    with pytest.raises(RenderError, match=message):
        render_facts(fever, "en", case.patient, case.facts, **options)
