"""The shipped rule packs: fever domain, migrated lab library, migration table and source rule (U3)."""

from __future__ import annotations

import pytest

from proof_rules import loader
from proof_rules.engine import infer
from proof_rules.keys import compute_key
from proof_rules.model import fields_of

# Every key of DDX_REGELN in the prototype (03_generate_vignettes.py, SHA-256 6a82aa96...c4b), in file order.
PROTOTYPE_KEYS = (
    "CRP_HOCH", "CRP_NIEDRIG", "CRP_HOCH_ALT_HOCH", "CRP_HOCH_UREA_HOCH", "CRP_HOCH_CRE_HOCH", "CRP_HOCH_ALB_NIEDRIG",
    "ALT_HOCH_BIL_HOCH", "ALT_HOCH_AP_HOCH", "UREA_HOCH_CRE_HOCH", "CA_HOCH_ALB_HOCH", "UREA_HOCH", "UREA_NIEDRIG",
    "CRE_HOCH", "CR_HOCH", "CRE_NIEDRIG", "eGFR_NIEDRIG", "HIC_EGFR_NIEDRIG", "MA_HOCH",
    "UAC_HOCH", "ALT_HOCH", "ALT_NIEDRIG", "AP_HOCH", "AP_NIEDRIG", "BIL_HOCH",
    "BIL_NIEDRIG", "BI_HOCH", "GT_HOCH", "ALB_HOCH", "ALB_NIEDRIG", "AL_HOCH",
    "AL_NIEDRIG", "TP_HOCH", "K_NIEDRIG", "KA_NIEDRIG", "K_HOCH", "KA_HOCH",
    "CA_HOCH", "CA_NIEDRIG", "CCA_HOCH", "PHO_HOCH", "PHO_NIEDRIG", "MG_HOCH",
    "CO2_HOCH", "CO2_NIEDRIG", "TSH_HOCH", "TS_HOCH", "TSH_NIEDRIG", "TS_NIEDRIG",
    "FT4_HOCH", "FT4_NIEDRIG", "SHBG_HOCH", "CHOL_HOCH", "HDL_NIEDRIG", "HDL_HOCH",
    "TRIG_HOCH", "LDL_HOCH", "CLDL_HOCH", "CH_HOCH", "TG_HOCH", "GL_HOCH",
    "GLP_HOCH", "HBAC_HOCH", "URIC_HOCH", "UR_HOCH", "CK_HOCH", "LACT_HOCH",
    "PSA_HOCH", "PSAT_HOCH", "IRON_HOCH", "IRON_NIEDRIG", "FER_HOCH", "BIC_HOCH",
    "GENERELL_HOCH",
)  # fmt: skip
EMPTY_KEYS = {"CRP_NIEDRIG", "ALT_NIEDRIG", "BIL_NIEDRIG"}
# Not migrated besides the empty keys: the fallback without a lab condition, and PSAT_HOCH, whose only text ("more
# likely BPH than carcinoma") no checked chapter supports (D-11).
UNSUPPORTED_KEYS = {"GENERELL_HOCH", "PSAT_HOCH"}
FEVER_LAB_FIELDS = {"lab.crp_mg_l", "lab.creatinine_umol_l", "lab.bilirubin_umol_l", "lab.lactate_mmol_l"}


@pytest.fixture(scope="module")
def packs():
    root = loader.PACKS_ROOT
    return {path.name: loader.read_pack(path) for path in sorted(root.iterdir()) if (path / loader.PACK_FILE).is_file()}


@pytest.fixture(scope="module")
def fever():
    return loader.load_domain("fever")


def test_all_packs_pass_the_full_check():
    result = loader.check()
    assert result.ok, "\n".join(result.problems)
    assert {pack.name for pack in result.packs} == {"fever", "labs"}
    assert [domain.name for domain in result.domains] == ["fever"]


def test_every_rule_is_an_unreviewed_draft_with_sources_and_tests(packs):
    for pack in packs.values():
        for rule in pack.rules:
            assert rule.status == "draft_unreviewed"
            assert rule.sources
            expectations = {test.expect for test in rule.tests}
            assert True in expectations and False in expectations


def test_fever_rules_cite_only_publications_and_guidelines(packs):
    """D-04: criteria of the fever domain come from original publications or guidelines, never NICE."""
    fever = packs["fever"]
    kinds = {source.id: source.kind for source in fever.sources.sources}
    for rule in fever.rules:
        for source in rule.sources:
            assert kinds[source.ref] in ("original_publication", "guideline"), (rule.id, source.ref)
    for pack in packs.values():
        for source in pack.sources.sources:
            assert "nice.org.uk" not in source.url
            assert source.terms and source.permitted_use and source.terms_checked_on


def test_migrated_rules_cite_reference_works(packs):
    """D-11: the migrated lab rules cite reference-work chapters (StatPearls on the NCBI Bookshelf)."""
    labs = packs["labs"]
    kinds = {source.id: source.kind for source in labs.sources.sources}
    for rule in labs.rules:
        assert rule.migrated_from in PROTOTYPE_KEYS
        for source in rule.sources:
            assert kinds[source.ref] == "reference_work", (rule.id, source.ref)


def test_migration_table_covers_every_prototype_key(packs):
    table = packs["labs"].migration
    assert table is not None
    assert tuple(entry.key for entry in table.entries) == PROTOTYPE_KEYS
    by_key = {entry.key: entry for entry in table.entries}
    for key in EMPTY_KEYS:
        assert not by_key[key].migrated and "A-09" in by_key[key].reason
    assert not by_key["GENERELL_HOCH"].migrated
    migrated = [entry.key for entry in table.entries if entry.migrated]
    assert len(migrated) >= 60  # PRD: "60+ DDx-Regeln"
    not_migrated = set(PROTOTYPE_KEYS) - set(migrated)
    assert not_migrated == EMPTY_KEYS | UNSUPPORTED_KEYS
    for key in UNSUPPORTED_KEYS:
        assert by_key[key].reason


def test_ur_is_migrated_as_urea(packs):
    """D-11: SynthEHR's UR is urea; the uric-acid texts of UR_HOCH do not become rules."""
    entry = next(entry for entry in packs["labs"].migration.entries if entry.key == "UR_HOCH")
    rules = {rule.id: rule for rule in packs["labs"].rules}
    targets = {rules[rule_id].target for rule_id in entry.rules}
    assert targets == {"ddx.kidney_failure"}
    for rule_id in entry.rules:
        assert fields_of(rules[rule_id].when) == {"lab.urea_mmol_l"}


def test_fever_activates_only_lab_rules_of_its_lab_panel(fever, packs):
    """A-64: active lab rules use only CRP, creatinine, bilirubin and lactate."""
    lab_rules = [rule for rule in fever.rules if rule.migrated_from]
    assert lab_rules
    for rule in lab_rules:
        assert fields_of(rule.when) <= FEVER_LAB_FIELDS, rule.id
    eligible = [rule.id for rule in packs["labs"].rules if fields_of(rule.when) <= FEVER_LAB_FIELDS]
    assert sorted(rule.id for rule in lab_rules) == sorted(eligible)


def test_fever_domain_has_profiles_for_its_lab_fields(fever):
    assert set(fever.references) == FEVER_LAB_FIELDS
    for code in FEVER_LAB_FIELDS:
        assert fever.catalog.get(code).synthehr is not None


@pytest.mark.parametrize(
    ("resp_rate", "mental_status", "sbp", "expected"),
    [
        (22, "normal", 100, ["rf.qsofa_ge2"]),
        (21, "normal", 100, []),
        (22, "normal", 101, []),
        (21, "altered", 100, ["rf.qsofa_ge2"]),
        (22, "altered", 101, ["rf.qsofa_ge2"]),
        (21, "altered", 101, []),
    ],
)
def test_qsofa_boundaries(fever, resp_rate, mental_status, sbp, expected):
    """PR-K07: respiratory rate 21/22 per minute, systolic pressure 100/101 mmHg, mental status."""
    facts = {"vital.resp_rate": resp_rate, "vital.mental_status": mental_status, "vital.sbp": sbp}
    assert list(infer(fever, facts).outcome.red_flags) == expected


def test_prd_example_key_is_recalculated(fever, prd_facts):
    """D-05: the PRD example under the fever rules; docs/methodik.md explains every difference to PRD §5."""
    key = compute_key(fever, prd_facts)
    assert key.determinability == "refer_urgent"
    assert key.red_flags == ("rf.qsofa_ge2",)
    assert key.ddx == (
        "ddx.active_inflammatory_disease",
        "ddx.bacterial_infection",
        "ddx.bacterial_meningitis",
        "ddx.pneumonia",
        "ddx.sepsis",
        "ddx.systemic_inflammation",
        "ddx.tissue_injury",
    )
    # qSOFA 3: without any one criterion qSOFA stays >= 2, so respiratory rate and blood pressure are not critical
    # (D-05); mental status is critical through the meningitis rule.
    assert key.critical_fields == ("hx.cough", "lab.crp_mg_l", "vital.mental_status", "vital.temp_c")
    variant = {**prd_facts, "vital.sbp": 120}
    assert {"vital.resp_rate", "vital.mental_status"} <= set(compute_key(fever, variant).critical_fields)
    assert "vital.sbp" not in compute_key(fever, variant).critical_fields
