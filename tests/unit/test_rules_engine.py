"""Engine, ablation and required questions: hand examples for every outcome (PR-K04, PR-K05, PR-K06, PR-K09)."""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from proof.core.rng import Stream
from proof_rules.ablation import ablation_table, critical_fields, required_questions
from proof_rules.engine import Key, Outcome, VariantKey, infer, outcome
from proof_rules.keys import FactError, compute_key, compute_variant_key
from proof_rules.logic import Truth

# A case without red flags in which every target is decided.
ANSWER_FACTS = {
    "vital.temp_c": 37.0,
    "vital.resp_rate": 16,
    "vital.sbp": 120,
    "vital.mental_status": "normal",
    "hx.onset_days": 5,
    "hx.cough": False,
    "lab.crp_mg_l": 3,
    "lab.wbc_g_l": 7.0,
}


def test_refer_urgent_for_the_prd_example(demo, prd_facts):
    key = compute_key(demo, prd_facts)
    assert key.determinability == "refer_urgent"
    assert key.red_flags == ("rf.qsofa_ge2",)
    assert key.ddx == ("ddx.alpha", "ddx.beta", "ddx.gamma")


def test_d05_no_field_is_critical_for_the_red_flag_with_qsofa_3(demo, prd_facts):
    # D-05: with all three qSOFA criteria met, removing any one still leaves qSOFA >= 2.
    key = compute_key(demo, prd_facts)
    assert not {"vital.resp_rate", "vital.mental_status", "vital.sbp"} & set(key.critical_fields)
    assert key.critical_fields == ("hx.cough", "lab.crp_mg_l", "lab.wbc_g_l", "vital.temp_c")


def test_d05_variant_with_qsofa_2(demo, prd_facts):
    # D-05: with sRR 120 only two criteria hold; respiratory rate and mental status become critical, sRR does not.
    facts = {**prd_facts, "vital.sbp": 120}
    key = compute_key(demo, facts)
    assert key.determinability == "refer_urgent"
    assert {"vital.resp_rate", "vital.mental_status"} <= set(key.critical_fields)
    assert "vital.sbp" not in key.critical_fields


def test_answer_when_nothing_is_open(demo):
    key = compute_key(demo, ANSWER_FACTS)
    assert key == Key(determinability="answer", red_flags=(), critical_fields=key.critical_fields, ddx=("ddx.beta",))
    inference = infer(demo, ANSWER_FACTS)
    assert all(truth is not Truth.UNKNOWN for truth in inference.targets.values())


def test_ask_when_a_missing_fact_would_decide_a_red_flag(demo, prd_facts):
    facts = {**prd_facts, "vital.sbp": 120}
    del facts["vital.resp_rate"]
    assert infer(demo, facts).targets["rf.qsofa_ge2"] is Truth.UNKNOWN
    assert compute_key(demo, facts).determinability == "ask"


def test_ask_when_a_missing_fact_would_decide_a_diagnosis(demo):
    facts = dict(ANSWER_FACTS)
    del facts["lab.crp_mg_l"]
    assert infer(demo, facts).targets["ddx.gamma"] is Truth.UNKNOWN
    assert outcome(demo, facts).determinability == "ask"


def test_a_true_red_flag_wins_over_open_questions(demo, prd_facts):
    facts = {key: value for key, value in prd_facts.items() if key.startswith("vital.")}
    result = outcome(demo, facts)
    assert result.determinability == "refer_urgent"
    assert infer(demo, facts).targets["ddx.gamma"] is Truth.UNKNOWN


def test_rules_with_the_same_target_are_combined_with_or(demo):
    facts = {**ANSWER_FACTS, "hx.onset_days": 2}
    del facts["lab.wbc_g_l"]
    # DEM-DDX-002 is false and DEM-DDX-003 unknown: the target stays unknown.
    assert infer(demo, facts).targets["ddx.beta"] is Truth.UNKNOWN
    # One true rule decides the target even though the other is unknown, so the case needs no question for it.
    facts = {**ANSWER_FACTS}
    del facts["hx.onset_days"]
    facts["lab.wbc_g_l"] = 15.0
    inference = infer(demo, facts)
    assert inference.rules["DEM-DDX-002"] is Truth.UNKNOWN
    assert inference.targets["ddx.beta"] is Truth.TRUE
    assert inference.outcome.determinability == "answer"


def test_inactive_library_rules_do_not_count(demo):
    assert "LABX-DDX-002" not in {rule.id for rule in demo.rules}
    assert demo.catalog.get("lab.ldl_mmol_l") is None
    assert outcome(demo, ANSWER_FACTS).determinability == "answer"


def test_ablation_for_red_flag_rules(demo, prd_facts):
    facts = {**prd_facts, "vital.sbp": 120}
    table = dict(ablation_table(demo, facts))
    assert table["vital.resp_rate"] == Outcome("ask", (), ("ddx.alpha", "ddx.beta", "ddx.gamma"))
    assert table["vital.sbp"] == outcome(demo, facts)


def test_ablation_for_ddx_rules(demo):
    # ddx.alpha needs cough AND temp >= 38: with temp 37.0 it stays false without cough, so cough is not critical.
    # ddx.beta is true only through "onset > 3" (DEM-DDX-002); without onset it becomes unknown. ddx.gamma needs crp.
    assert critical_fields(demo, ANSWER_FACTS) == ("hx.onset_days", "lab.crp_mg_l")
    # With cough true, the temperature decides ddx.alpha and becomes critical.
    assert critical_fields(demo, {**ANSWER_FACTS, "hx.cough": True}) == (
        "hx.onset_days",
        "lab.crp_mg_l",
        "vital.temp_c",
    )
    # Unused facts are never critical.
    assert "exam.rash" not in critical_fields(demo, {**ANSWER_FACTS, "exam.rash": True})


def test_ablation_does_not_depend_on_fact_order(demo, prd_facts):
    reference = compute_key(demo, prd_facts)
    stream = Stream("test", "ablation-order")
    codes = list(prd_facts)
    orders = set()
    for _ in range(25):
        shuffled = {code: prd_facts[code] for code in stream.shuffled(codes)}
        orders.add(tuple(shuffled))
        assert compute_key(demo, shuffled) == reference
    assert len(orders) > 20, "the test must really see different orders"
    assert compute_key(demo, dict(reversed(list(prd_facts.items())))) == reference


def test_required_questions_for_one_missing_critical_field(demo, prd_facts):
    base = {**prd_facts, "vital.sbp": 120}
    variant = {code: value for code, value in base.items() if code != "vital.resp_rate"}
    assert required_questions(demo, variant, base) == ("vital.resp_rate",)
    key = compute_variant_key(demo, variant, base)
    assert isinstance(key, VariantKey)
    assert key.determinability == "ask"
    assert key.required_questions == ("vital.resp_rate",)


def test_required_questions_for_several_missing_fields(demo, prd_facts):
    # Neither field is critical alone in the base case (qSOFA 3); missing together, both are needed.
    variant = {code: value for code, value in prd_facts.items() if code not in ("vital.resp_rate", "vital.sbp")}
    assert "vital.resp_rate" not in critical_fields(demo, prd_facts)
    assert outcome(demo, variant).determinability == "ask"
    assert required_questions(demo, variant, prd_facts) == ("vital.resp_rate", "vital.sbp")


def test_no_required_questions_for_a_non_critical_gap(demo, prd_facts):
    variant = {code: value for code, value in prd_facts.items() if code != "hx.onset_days"}
    assert required_questions(demo, variant, prd_facts) == ()
    assert required_questions(demo, prd_facts, prd_facts) == ()


def test_invalid_facts_are_rejected(demo, prd_facts):
    with pytest.raises(FactError, match="unknown fact code"):
        compute_key(demo, {**prd_facts, "lab.unknown": 1})
    with pytest.raises(FactError, match="outside the physiological bounds"):
        compute_key(demo, {**prd_facts, "vital.resp_rate": 200})
    with pytest.raises(FactError, match="expected one of normal, altered"):
        compute_key(demo, {**prd_facts, "vital.mental_status": "confused"})
    with pytest.raises(FactError, match="decimal places"):
        compute_key(demo, {**prd_facts, "vital.temp_c": 39.25})
    with pytest.raises(FactError):
        compute_variant_key(demo, prd_facts, {**prd_facts, "hx.cough": "yes"})


def test_key_lists_must_be_sorted_and_unique():
    with pytest.raises(ValidationError, match="sorted"):
        Key(determinability="answer", red_flags=(), critical_fields=("vital.sbp", "hx.cough"), ddx=())
    with pytest.raises(ValidationError, match="sorted"):
        VariantKey(
            determinability="ask", red_flags=(), critical_fields=(), ddx=(), required_questions=("vital.sbp", "hx.a")
        )


def test_key_with_ablation_takes_less_than_one_second(demo, prd_facts):
    start = time.perf_counter()
    for _ in range(20):
        compute_key(demo, prd_facts)
    assert (time.perf_counter() - start) / 20 < 1.0
