"""Language tables and the fixed notices (A-24, PR-D03, PR-A01)."""

from __future__ import annotations

import pytest

from proof.core import disclaimer, i18n
from proof.core.i18n import TranslationError

EXPECTED_NOTICES = {
    "zh": [
        "Proof 是评测工具和开放数据集，不是医疗器械，不用于患者诊疗。",
        "Proof 衡量的是与公开参考标准的一致性，而非临床真实情况。",
    ],
    "en": [
        "Proof is an evaluation tool and open dataset, not a medical device, and not intended for patient care.",
        "Proof measures agreement with a disclosed reference, not clinical truth.",
    ],
    "de": [
        "Proof ist ein Evaluationswerkzeug und offener Datensatz, kein Medizinprodukt und nicht für die "
        "Patientenversorgung bestimmt.",
        "Proof misst Übereinstimmung mit einer offengelegten Referenz, nicht klinische Wahrheit.",
    ],
}


def test_languages_are_zh_en_de():
    assert i18n.LANGUAGES == ("zh", "en", "de")


def test_all_languages_have_the_same_keys():
    assert i18n.missing_keys() == {"zh": set(), "en": set(), "de": set()}


@pytest.mark.parametrize("lang", i18n.LANGUAGES)
def test_notices_per_language(lang):
    assert disclaimer.lines(lang) == EXPECTED_NOTICES[lang]


def test_block_has_one_line_per_language_in_order():
    rows = disclaimer.block().split("\n")
    assert [row.split(":", 1)[0] for row in rows] == ["zh", "en", "de"]
    for row, lang in zip(rows, i18n.LANGUAGES, strict=True):
        for sentence in EXPECTED_NOTICES[lang]:
            assert sentence in row


def test_missing_key_and_unknown_language_are_errors():
    with pytest.raises(TranslationError, match="missing text"):
        i18n.text("no.such.key", "en")
    with pytest.raises(TranslationError, match="unknown language"):
        i18n.text("disclaimer.category", "fr")


def test_flatten_rejects_non_string_and_non_nfc_values():
    out: dict[str, str] = {}
    with pytest.raises(TranslationError, match="must be a string"):
        i18n._flatten("", {"a": {"b": 1}}, out, "test.yaml")
    with pytest.raises(TranslationError, match="NFC"):
        i18n._flatten("", {"a": "é"}, out, "test.yaml")
    i18n._flatten("", {"a": {"b": "x"}}, out, "test.yaml")
    assert out == {"a.b": "x"}
