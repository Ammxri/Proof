"""Metrics S1–S7 with hand examples (PR-F08, PR-S1 to PR-S7, PR-P02, A-13, A-14, A-37, A-36)."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from proof.scoring import metrics as m
from proof.scoring.metrics import NA, Expected, Ratio, Truth, UnitInput, evaluate
from proof.scoring.response import AllowedCodes

ALLOWED = AllowedCodes(
    ddx=frozenset({"ddx.a", "ddx.b", "ddx.c"}),
    red_flags=frozenset({"rf.x", "rf.y"}),
    fields=frozenset({"hx.a", "hx.b", "vital.c"}),
)
EMPTY: frozenset[str] = frozenset()


def answer(decision="answer", ddx=(), questions=(), red_flags=(), contradictions=(), rationale="r") -> str:
    return json.dumps(
        {
            "decision": decision,
            "ddx": list(ddx),
            "questions": list(questions),
            "red_flags": list(red_flags),
            "contradictions": list(contradictions),
            "rationale": rationale,
        }
    )


def truth(determinability="answer", red_flags=(), ddx=(), required=(), complete=True) -> Truth:
    return Truth(determinability, frozenset(red_flags), frozenset(ddx), frozenset(required), complete)


def unit(text, key=None, *, case="C1", lang="en", mr=None, item=None, status="ok", expected=None) -> UnitInput:
    item = item or (case if mr is None else f"{case}-{mr}-1")
    return UnitInput(
        unit_id=f"{item}@{lang}",
        item_id=item,
        case_id=case,
        mr=mr,
        lang=lang,
        status=status,
        text=text,
        truth=key or truth(),
        expected=expected,
    )


def score(*units: UnitInput, langs=("en",)):
    return m.metrics(list(units), ALLOWED, langs)


def ratio(data) -> tuple[int, int, object]:
    return data["numerator"], data["denominator"], data["value"]


# --- S7 and the empty answer -----------------------------------------------------------------------------------------


def test_s7_counts_only_strictly_valid_answers():
    """S7: invalid JSON, a Markdown block and unknown codes are invalid (A-13); errors are not scored (A-36)."""
    result = score(
        unit(answer()),
        unit("not json"),
        unit("```json\n" + answer() + "\n```"),
        unit(answer(ddx=["ddx.unknown"])),
        unit(None, status="error"),
    )
    assert ratio(result["S7_format"]["all"]) == (1, 4, 0.25)
    assert result["units"] == {"total": 5, "answered": 4, "errors": 1, "valid": 1, "invalid": 3}


def test_an_invalid_answer_counts_as_the_empty_answer():
    """A-13: in S1–S4 an invalid answer has no decision and empty lists."""
    item = evaluate(unit("{oops", truth("answer", ddx=["ddx.a"])), ALLOWED)
    assert (item.valid, item.decision, item.ddx, item.questions, item.red_flags) == (False, None, EMPTY, EMPTY, EMPTY)
    assert item.problems
    result = score(unit("{oops", truth("answer", red_flags=["rf.x"], ddx=["ddx.a"])))
    assert ratio(result["S1_decision"]["all"]) == (0, 1, 0.0)
    assert ratio(result["S3_red_flags"]["complete"]["all"]) == (0, 1, 0.0)
    assert ratio(result["S4_diagnoses"]["all"]) == (0, 1, 0.0)


# --- S1 to S4 --------------------------------------------------------------------------------------------------------


def test_s1_decision():
    result = score(
        unit(answer("answer"), truth("answer")),
        unit(answer("ask"), truth("refer_urgent")),
        unit(answer("refer_urgent"), truth("refer_urgent")),
        unit(answer("ask"), truth("ask")),
    )
    assert ratio(result["S1_decision"]["all"]) == (3, 4, 0.75)


def test_s2_recall_over_missing_fields_and_precision_over_all_questions():
    """A-13: recall over units with required questions, precision over every question named."""
    result = score(
        unit(answer("ask", questions=["hx.a", "vital.c"]), truth("ask", required=["hx.a", "hx.b"], complete=False)),
        unit(answer("answer", questions=["hx.b"]), truth("answer")),
        unit(answer("ask", questions=["hx.a", "hx.a"]), truth("ask", required=["hx.a"], complete=False)),
    )
    # Recall: unit 1 finds hx.a of {hx.a, hx.b}, unit 3 finds hx.a of {hx.a} -> 2 of 3.
    assert ratio(result["S2_questions"]["recall"]["all"]) == (2, 3, 0.6667)
    # Precision: named sets {hx.a, vital.c}, {hx.b}, {hx.a} -> 2 of 4 named questions are required ones.
    assert ratio(result["S2_questions"]["precision"]["all"]) == (2, 4, 0.5)


def test_empty_denominators_are_not_applicable_never_zero():
    result = score(unit(answer("answer"), truth("answer")))
    for value in (
        result["S2_questions"]["recall"]["all"],
        result["S2_questions"]["precision"]["all"],
        result["S3_red_flags"]["complete"]["all"],
        result["S3_red_flags"]["incomplete"]["all"],
        result["S4_diagnoses"]["all"],
    ):
        assert ratio(value) == (0, 0, NA)
    assert Ratio(0, 0).value == "n/a" and Ratio(0, 3).value == 0.0
    assert ratio(score()["S7_format"]["all"]) == (0, 0, NA)


def test_s3_red_flags_separately_for_complete_and_incomplete_units():
    """PR-S3: recall of the key's red flags; complete and incomplete units are never averaged together."""
    result = score(
        unit(answer("refer_urgent", red_flags=["rf.x"]), truth("refer_urgent", red_flags=["rf.x", "rf.y"])),
        unit(answer("refer_urgent", red_flags=["rf.y"]), truth("refer_urgent", red_flags=["rf.y"])),
        unit(answer("ask"), truth("refer_urgent", red_flags=["rf.x"], complete=False), mr="MR1"),
        unit(answer("answer", red_flags=["rf.x"]), truth("answer")),  # no key red flag: not in the denominator
    )
    assert ratio(result["S3_red_flags"]["complete"]["all"]) == (2, 3, 0.6667)
    assert ratio(result["S3_red_flags"]["incomplete"]["all"]) == (0, 1, 0.0)


def test_s4_hit_if_one_key_diagnosis_is_named():
    result = score(
        unit(answer(ddx=["ddx.b"]), truth(ddx=["ddx.a", "ddx.b"])),
        unit(answer(ddx=["ddx.c"]), truth(ddx=["ddx.a"])),
        unit(answer(ddx=["ddx.a"]), truth()),  # no key diagnosis: not in the denominator
    )
    assert ratio(result["S4_diagnoses"]["all"]) == (1, 2, 0.5)


# --- S5 --------------------------------------------------------------------------------------------------------------


MR1_EXPECTED = Expected("absolute", decision="ask", questions_include=frozenset({"hx.a"}))
MR3_EXPECTED = Expected("invariant", compare=m.UNCHANGED)


def test_s5_mr1_against_its_absolute_expectation():
    key = truth("ask", required=["hx.a"], complete=False)
    result = score(
        unit(answer("ask", questions=["hx.a", "hx.b"]), key, mr="MR1", case="C1", expected=MR1_EXPECTED),
        unit(answer("ask", questions=["hx.b"]), key, mr="MR1", case="C2", expected=MR1_EXPECTED),
        unit(answer("answer", questions=["hx.a"]), key, mr="MR1", case="C3", expected=MR1_EXPECTED),
        unit("no json", key, mr="MR1", case="C4", expected=MR1_EXPECTED),
    )
    mr1 = result["S5_invariance"]["MR1"]
    assert ratio(mr1["violation_rate"]) == (2, 3, 0.6667)
    assert (mr1["invalid_excluded"], mr1["missing_excluded"]) == (1, 0)


def test_s5_mr3_against_the_base_answer_in_the_same_language():
    """A-14: decision and the sets of diagnoses, red flags and questions must be equal; list order does not matter."""
    base = truth("answer", ddx=["ddx.a"])
    units = [
        unit(answer(ddx=["ddx.a", "ddx.b"]), base, case="C1"),
        unit(answer(ddx=["ddx.b", "ddx.a"]), base, case="C1", mr="MR3", expected=MR3_EXPECTED),
        unit(answer(ddx=["ddx.a"]), base, case="C2"),
        unit(answer(ddx=["ddx.a"], questions=["hx.a"]), base, case="C2", mr="MR3", expected=MR3_EXPECTED),
        unit("invalid", base, case="C3"),
        unit(answer(), base, case="C3", mr="MR3", expected=MR3_EXPECTED),
        unit(None, base, case="C4", status="error"),
        unit(answer(), base, case="C4", mr="MR3", expected=MR3_EXPECTED),
    ]
    mr3 = score(*units)["S5_invariance"]["MR3"]
    assert ratio(mr3["violation_rate"]) == (1, 2, 0.5)
    assert (mr3["invalid_excluded"], mr3["missing_excluded"]) == (1, 1)


def test_s5_mr5_compares_the_base_answers_across_languages():
    """A-37: pairs zh–en, zh–de, en–de of every base case."""
    key = truth("answer", ddx=["ddx.a"])
    units = [
        unit(answer(ddx=["ddx.a"]), key, case="C1", lang="zh"),
        unit(answer(ddx=["ddx.a"]), key, case="C1", lang="en"),
        unit(answer("ask", ddx=["ddx.a"]), key, case="C1", lang="de"),
        unit(answer(), key, case="C2", lang="zh"),
        unit(answer(), key, case="C2", lang="en"),
        unit("invalid", key, case="C2", lang="de"),
    ]
    mr5 = score(*units, langs=("zh", "en", "de"))["S5_invariance"]["MR5"]
    # C1: zh=en agree, zh-de and en-de differ in the decision; C2: zh=en agree, the two pairs with de are invalid.
    assert ratio(mr5["violation_rate"]) == (2, 4, 0.5)
    assert mr5["invalid_excluded"] == 2
    one_language = score(unit(answer()), langs=("en",))
    assert "MR5" not in one_language["S5_invariance"]
    partial = score(unit(answer(), case="C1", lang="zh"), unit(None, case="C1", lang="en", status="error"),
                    langs=("zh", "en"))  # fmt: skip
    assert partial["S5_invariance"]["MR5"]["missing_excluded"] == 1


# --- S6 and the profile ----------------------------------------------------------------------------------------------


def test_s6_is_the_spread_over_languages():
    units = [
        unit(answer("answer"), truth("answer"), lang="zh"),
        unit(answer("ask"), truth("answer"), lang="zh"),
        unit(answer("answer"), truth("answer"), lang="en"),
        unit(answer("ask"), truth("answer"), lang="de"),
    ]
    result = score(*units, langs=("zh", "en", "de"))
    spread = result["S6_language_spread"]["S1_decision"]
    assert spread == {"value": 1.0, "by_lang": {"zh": 0.5, "en": 1.0, "de": 0.0}}
    assert result["S6_language_spread"]["S3_red_flags_complete"]["value"] == NA
    assert m.spread({"zh": Ratio(1, 2), "en": Ratio(0, 0)})["value"] == NA


def test_the_profile_has_no_value_that_combines_metrics():
    """PR-P02, NZ-03: every metric stands alone; there is no total, mean or rank over them."""
    result = score(unit(answer()), langs=("en",))
    assert set(result) == {
        "units",
        "S1_decision",
        "S2_questions",
        "S3_red_flags",
        "S4_diagnoses",
        "S5_invariance",
        "S6_language_spread",
        "S7_format",
    }

    def keys(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys(value)

    forbidden = {"total_score", "overall", "score", "aggregate", "average", "mean", "rank", "composite"}
    assert not forbidden & set(keys(result))


def test_scoring_loads_no_network_or_model_client():
    """PR-N04: the scoring modules import no HTTP or model client, not even indirectly."""
    names = ["proof.scoring.metrics", "proof.scoring.response", "proof.scoring.runs"]
    script = (
        "import importlib, json, sys\n"
        f"for name in {names!r}: importlib.import_module(name)\n"
        "print(json.dumps(sorted(sys.modules)))\n"
    )
    command = [sys.executable, "-c", script]
    result = subprocess.run(command, capture_output=True, check=True, text=True)  # noqa: S603 - own interpreter
    loaded = set(json.loads(result.stdout))
    clients = {"httpx", "httpcore", "requests", "urllib3", "aiohttp", "openai", "anthropic", "ollama", "proof.harness"}
    assert not {name for name in loaded if name in clients or name.split(".")[0] in clients}
    assert not any(name.startswith("proof.harness") for name in loaded)


@pytest.mark.parametrize("lang", ["zh", "en", "de"])
def test_results_are_split_by_language(lang):
    result = score(unit(answer(), lang=lang), langs=("zh", "en", "de"))
    for name in ("S1_decision", "S4_diagnoses", "S7_format"):
        assert set(result[name]["by_lang"]) == {"zh", "en", "de"}
    assert ratio(result["S7_format"]["by_lang"][lang]) == (1, 1, 1.0)
