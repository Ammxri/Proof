"""Lab profiles from the SynthEHR CSV (PR-W01, D-03, A-56): counting, reference choice, statuses, determinism."""

from __future__ import annotations

import re
import shutil
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from proof.cases import profiles
from proof.cli import app
from proof.core import canonical
from proof_rules import loader
from proof_rules.model import Catalog, FieldDef, ProfileReference

MINI_CSV = Path(__file__).resolve().parents[1] / "fixtures" / "synthehr" / "mini.csv"
PROVENANCE = profiles.Provenance(
    generator="SynthEHR 2.0.1", command="SynthEHR.exe -d Biochemistry -s 42 out 5 19", seed=42,
    generated_on=date(2026, 11, 8),
)  # fmt: skip


@pytest.fixture
def catalog(fixture_packs) -> Catalog:
    pack = loader.read_pack(fixture_packs / "labx")
    return pack.catalog


def test_parse_number():
    assert profiles.parse_number("10") == 10
    assert isinstance(profiles.parse_number("10"), int)
    assert profiles.parse_number(" 2.55 ") == 2.55
    assert profiles.parse_number("-3") == -3
    assert profiles.parse_number("1e3") == 1000.0
    for text in ("NULL", "", "abc", "1,5", "nan", "inf", "1.2.3"):
        assert profiles.parse_number(text) is None


def test_round_to_follows_the_field_decimals():
    assert profiles.round_to(5.5, 0) == 6
    assert isinstance(profiles.round_to(5.5, 0), int)
    assert profiles.round_to(5.15, 1) == 5.2
    assert str(profiles.round_to(-0.04, 1)) == "0.0"
    assert profiles.round_to(-0.4, 0) == 0


def test_quantiles_interpolate_linearly():
    assert profiles.quantiles([2, 6, 10], 0) == [2, 2, 3, 3, 4, 4, 4, 5, 5, 6, 6, 6, 7, 7, 8, 8, 8, 9, 9, 10, 10]
    single = profiles.quantiles([7.5], 1)
    assert single == [7.5] * 21
    assert profiles.quantiles([12, 36], 0)[10] == 24
    assert len(profiles.PROBABILITIES) == 21
    assert profiles.PROBABILITIES[0] == 0 and profiles.PROBABILITIES[-1] == 1


def test_status_against_the_reference():
    assert profiles.status_of(10, (0, 10)) == "normal"
    assert profiles.status_of(11, (0, 10)) == "high"
    assert profiles.status_of(0.9, (1, 4.2)) == "low"
    assert profiles.status_of(99, (None, 5)) == "high"
    assert profiles.status_of(-1, (None, 5)) == "normal"


def test_crp_profile_counts_every_discarded_row(catalog):
    built = profiles.build_profiles(MINI_CSV, catalog, PROVENANCE)
    assert sorted(built) == ["lab.crp_mg_l", "lab.ldl_mmol_l"]
    crp = built["lab.crp_mg_l"]
    assert crp["reference"] == {"lower": 0, "upper": 10}
    assert crp["counts"] == {
        "rows": 13,
        "rows_other_unit": 1,
        "rows_no_value": 1,
        "rows_censored_kept": 1,
        "rows_outside_bounds": 2,
        "rows_other_reference": 1,
        "rows_used": 8,
        "patients": 6,
        "patients_by_status": {"low": 0, "normal": 4, "high": 2},
    }
    # Means per patient: P01 (4 + 7) / 2 = 5.5 -> 6, P04 2, P08 "<5" -> 5 (censored, kept with its limit),
    # P11 10 (the upper limit is still normal); P02 35.5 -> 36, P03 12. Median of 2, 5, 6, 10 is 5.5 -> 6.
    assert crp["quantiles"]["normal"][0] == 2 and crp["quantiles"]["normal"][10] == 6
    assert crp["quantiles"]["normal"][20] == 10
    assert crp["quantiles"]["high"][0] == 12 and crp["quantiles"]["high"][20] == 36
    assert crp["quantiles"]["low"] is None
    assert crp["bounds"] == {"lower": 0, "upper": 500, "source": "SRC-9002", "locator": "fixture"}
    assert crp["synthehr"] == {"codes": ["CRP"], "unit": "mg/L"}
    assert crp["provenance"]["csv_rows"] == 19
    assert crp["provenance"]["seed"] == 42
    assert crp["provenance"]["generated_on"] == "2026-11-08"
    assert len(crp["provenance"]["csv_sha256"]) == 64


def test_alias_codes_pool_into_one_field(catalog):
    ldl = profiles.build_profiles(MINI_CSV, catalog, PROVENANCE)["lab.ldl_mmol_l"]
    assert ldl["synthehr"]["codes"] == ["LDL", "CLDL"]
    assert ldl["reference"] == {"lower": 1, "upper": 4.2}
    assert ldl["counts"]["rows"] == 5
    assert ldl["counts"]["rows_other_reference"] == 1
    assert ldl["counts"]["patients_by_status"] == {"low": 1, "normal": 1, "high": 1}
    assert ldl["quantiles"]["high"] == [5.2] * 21  # (5.0 + 5.3) / 2 = 5.15 -> 5.2


def test_profiles_are_deterministic_and_loadable(tmp_path, catalog):
    first = profiles.write_profiles(profiles.build_profiles(MINI_CSV, catalog, PROVENANCE), tmp_path / "a")
    second = profiles.write_profiles(profiles.build_profiles(MINI_CSV, catalog, PROVENANCE), tmp_path / "b")
    assert [path.name for path in first] == ["crp_mg_l.json", "ldl_mmol_l.json"]
    for one, two in zip(first, second, strict=True):
        data = one.read_bytes()
        assert data == two.read_bytes()
        assert data.endswith(b"\n") and b"\r" not in data
        assert canonical.dumps_bytes(canonical.loads(data)) + b"\n" == data
        ProfileReference.model_validate(canonical.loads(data))


def test_most_frequent_reference_wins_and_ties_are_stable():
    assert profiles._choose_reference(profiles.Counter({(0, 5): 3, (0, 10): 3})) == (0, 5)
    assert profiles._choose_reference(profiles.Counter({(None, 5): 2, (0, 5): 2})) == (0, 5)
    assert profiles._choose_reference(profiles.Counter({(None, None): 9, (1, 2): 1})) == (1, 2)
    assert profiles._choose_reference(profiles.Counter({(None, None): 9})) is None


def _field(code: str, codes: list[str], unit: str = "mmol/L") -> FieldDef:
    return FieldDef.model_validate(
        {
            "code": code,
            "section": "lab",
            "type": "number",
            "unit": unit,
            "decimals": 1,
            "bounds": {"lower": 0.1, "upper": 50, "source": {"ref": "SRC-9002", "locator": "fixture"}},
            "labels": {"zh": {"name": "x"}, "en": {"name": "x"}, "de": {"name": "x"}},
            "synthehr": {"codes": codes, "unit": unit},
        }
    )


def test_problems_are_reported(tmp_path):
    with pytest.raises(profiles.ProfileError, match="no lab field with a SynthEHR source"):
        profiles.build_profiles(MINI_CSV, Catalog(), PROVENANCE)
    twice = Catalog(fields=(_field("lab.a_mmol_l", ["LDL"]), _field("lab.b_mmol_l", ["LDL"])))
    message = "SynthEHR code LDL belongs to lab.a_mmol_l and lab.b_mmol_l"
    with pytest.raises(profiles.ProfileError, match=re.escape(message)):
        profiles.build_profiles(MINI_CSV, twice, PROVENANCE)
    absent = Catalog(fields=(_field("lab.k_mmol_l", ["K"]),))
    with pytest.raises(profiles.ProfileError, match=re.escape("lab.k_mmol_l: no usable row with a reference range")):
        profiles.build_profiles(MINI_CSV, absent, PROVENANCE)
    broken = tmp_path / "broken.csv"
    broken.write_text("chi,TestCode,Result\nP1,CRP,4\n", encoding="utf-8")
    with pytest.raises(profiles.ProfileError, match="missing columns QuantityUnit, ArithmeticComparator"):
        profiles.build_profiles(broken, Catalog(fields=(_field("lab.k_mmol_l", ["K"]),)), PROVENANCE)


def test_only_numeric_lab_fields_have_a_synthehr_source():
    data = _field("lab.k_mmol_l", ["K"]).model_dump()
    data.update(code="vital.k", section="vital")
    with pytest.raises(ValueError, match="only numeric lab fields have a SynthEHR source"):
        FieldDef.model_validate(data)
    with pytest.raises(ValueError, match="SynthEHR codes must be unique"):
        _field("lab.k_mmol_l", ["K", "K"])
    with pytest.raises(ValueError, match="at least 1 item"):
        _field("lab.k_mmol_l", [])


def _run(*args: str):
    return CliRunner().invoke(app, list(args))


def test_cli_builds_profiles_the_domain_can_load(tmp_path, fixture_packs):
    packs = tmp_path / "packs"
    shutil.copytree(fixture_packs, packs)
    result = _run(
        "labs", "build", "--csv", str(MINI_CSV), "--domain", "demo", "--packs", str(packs),
        "--generator", "SynthEHR 2.0.1", "--command", "SynthEHR.exe -d Biochemistry", "--seed", "42",
        "--generated-on", "2026-11-08",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "lab.crp_mg_l: reference 0-10 mg/L, 8 of 13 rows, 6 patients (low 0, normal 4, high 2)" in result.output
    # Only fields of the domain's effective catalog get a profile: LDL is not used by an active demo rule.
    assert sorted(path.name for path in (packs / "demo/profiles").iterdir()) == ["crp_mg_l.json"]
    domain = loader.load_domain("demo", packs)
    assert domain.references["lab.crp_mg_l"].upper == 10


def test_cli_builds_without_profiles_and_into_another_directory(tmp_path, fixture_packs):
    packs = tmp_path / "packs"
    shutil.copytree(fixture_packs, packs)
    (packs / "demo/profiles/crp_mg_l.json").unlink()
    with pytest.raises(loader.LoadError):
        loader.load_domain("demo", packs)
    out = tmp_path / "out"
    result = _run(
        "labs", "build", "--csv", str(MINI_CSV), "--domain", "demo", "--packs", str(packs), "--out", str(out),
        "--generator", "g", "--command", "c", "--seed", "1", "--generated-on", "2026-11-08",
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert (out / "crp_mg_l.json").is_file()


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--generated-on", "08.11.2026"], "expected a date YYYY-MM-DD"),
        (["--generated-on", "2026-11-08", "--domain", "nope"], "no pack 'nope'"),
    ],
)
def test_cli_rejects_bad_input(tmp_path, fixture_packs, extra, message):
    result = _run(
        "labs", "build", "--csv", str(MINI_CSV), "--packs", str(fixture_packs), "--generator", "g",
        "--command", "c", "--seed", "1", *extra,
    )  # fmt: skip
    assert result.exit_code == 1
    assert message in result.output


def test_cli_reports_profile_errors(tmp_path, fixture_packs):
    broken = tmp_path / "broken.csv"
    broken.write_text("chi,TestCode\n", encoding="utf-8")
    result = _run(
        "labs", "build", "--csv", str(broken), "--domain", "demo", "--packs", str(fixture_packs),
        "--generator", "g", "--command", "c", "--seed", "1", "--generated-on", "2026-11-08",
    )  # fmt: skip
    assert result.exit_code == 1
    assert "missing columns" in result.output


def test_builder_never_imports_synthehr():
    source = Path(profiles.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in source and "SynthEHR.exe" not in source


def test_open_upper_bound_and_missing_bounds():
    open_upper = _field("lab.ldl_mmol_l", ["LDL", "CLDL"]).model_dump()
    open_upper["bounds"] = {"lower": 0.1, "source": {"ref": "SRC-9002", "locator": "fixture"}}
    built = profiles.build_profiles(MINI_CSV, Catalog(fields=(FieldDef.model_validate(open_upper),)), PROVENANCE)
    ldl = built["lab.ldl_mmol_l"]
    assert ldl["bounds"]["upper"] is None
    assert ldl["counts"]["rows_outside_bounds"] == 0
    without = _field("lab.ldl_mmol_l", ["LDL"]).model_dump()
    without["bounds"] = None
    with pytest.raises(profiles.ProfileError, match="no physiological bounds"):
        profiles.build_profiles(MINI_CSV, Catalog(fields=(FieldDef.model_validate(without),)), PROVENANCE)


# --- Full profile format (U4) ----------------------------------------------------------------------------------------


def test_built_and_shipped_profiles_follow_the_full_format(catalog):
    for code, data in profiles.build_profiles(MINI_CSV, catalog, PROVENANCE).items():
        assert profiles.LabProfile.model_validate(data).fact_code == code
    shipped = sorted((loader.PACKS_ROOT / "fever" / loader.PROFILES_DIR).glob("*.json"))
    assert len(shipped) == 4
    for path in shipped:
        profile = profiles.read_profile(path)
        assert profile.provenance.generator == "SynthEHR 2.0.1"
        assert profile.counts.patients == sum(profile.counts.patients_by_status.values())


def _profile_data() -> dict:
    path = loader.PACKS_ROOT / "fever" / loader.PROFILES_DIR / "lactate_mmol_l.json"
    return canonical.loads(path.read_bytes())


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["counts"].update({"patients": 1}), "does not add up to patients"),
        (lambda d: d["counts"].update({"rows_used": 1}), "do not add up to rows"),
        (lambda d: d["counts"]["patients_by_status"].pop("low"), "needs exactly low, normal, high"),
        (lambda d: d["quantiles"].update({"probabilities": [0.0] * 21}), "must be 0, 0.05, ..., 1"),
        (lambda d: d["quantiles"].update({"normal": list(reversed(d["quantiles"]["normal"]))}), "must not decrease"),
        (lambda d: d["quantiles"].update({"low": None}), "quantiles exist exactly when the status has patients"),
        (lambda d: d["quantiles"]["high"].__setitem__(0, 1.0), "outside the status range"),
        (lambda d: d["quantiles"]["high"].__setitem__(20, 60.0), "outside the physiological bounds"),
        (lambda d: d.update({"extra": 1}), "Extra inputs are not permitted"),
    ],
)
def test_inconsistent_profiles_are_rejected(tmp_path, change, message):
    data = _profile_data()
    change(data)
    path = tmp_path / "profile.json"
    path.write_bytes(canonical.dumps_bytes(data))
    with pytest.raises(profiles.ProfileError) as caught:
        profiles.read_profile(path)
    assert message in "\n".join(caught.value.problems)


def test_unreadable_profiles_are_rejected(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(profiles.ProfileError, match=r"profile\.json"):
        profiles.read_profile(path)
