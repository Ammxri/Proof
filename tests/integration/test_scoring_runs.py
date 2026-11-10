"""Scoring of real run directories and comparison of two stub runs (PR-F08, PR-D02, UF-02, UF-05, KONZEPT U8)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from proof.cases import collection
from proof.cli import app
from proof.harness import run as harness_run
from proof.harness.providers import Provider
from proof.scoring import runs
from proof.variants import sets

runner = CliRunner()


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    monkeypatch.setenv("PROOF_HOME", str(path))
    return path


@pytest.fixture
def demo(tmp_path, fixture_packs) -> tuple[Path, Path, Path]:
    packs = tmp_path / "packs"
    shutil.copytree(fixture_packs, packs)
    directory = tmp_path / "demo-3"
    collection.write(collection.build("demo", 3, 1, name="demo-3", root=packs), directory)
    variants = sets.default_directory(directory, 1)
    sets.write(sets.build(directory, 1, root=packs), variants)
    return directory, variants, packs


def _run(url: str, demo, home: Path, name: str, model: str) -> Path:
    directory, variants, packs = demo
    provider = Provider.model_validate(
        {
            "name": "stub",
            "api": "openai_chat",
            "base_url": url,
            "model": model,
            "origin": "other",
            "region": "CN",
            "params": {"max_tokens": 64},
            "pricing": {"input_per_mtok": 0, "output_per_mtok": 0, "currency": "EUR"},
        }
    )
    config = harness_run.configure(provider, directory, variants_dir=variants, langs=["zh", "en"])
    return harness_run.execute(config, home / "runs" / name, root=packs).directory


def test_score_and_compare_two_stub_runs(stub, home, demo):
    """KONZEPT U8: the comparison shows the change of every metric and of every unit."""
    url, state = stub
    packs = demo[2]
    first = _run(url, demo, home, "a", "stub-model-a")
    state.mode = "invalid"
    second = _run(url, demo, home, "b", "stub-model-b")
    run_a, run_b = runs.load_run(first, packs), runs.load_run(second, packs)
    assert len(run_a.inputs) == 42  # 3 cases and their MR1-MR4, MR6 and MR7 variants, in 2 languages
    profile_a, profile_b = runs.profile(run_a), runs.profile(run_b)
    assert profile_a["metrics"]["S7_format"]["all"]["value"] == 1.0
    assert profile_b["metrics"]["S7_format"]["all"]["value"] == 0.0
    assert profile_a["deterministic"] is True and profile_a["langs"] == ["zh", "en"]
    assert set(profile_a["metrics"]["S5_invariance"]) == {"MR1", "MR2", "MR3", "MR4", "MR5", "MR6", "MR7"}
    # The stub always answers "answer" with ddx.alpha; run a's metrics follow from the keys.
    keys = [unit.truth for unit in run_a.inputs]
    expected_s1 = sum(truth.determinability == "answer" for truth in keys)
    assert profile_a["metrics"]["S1_decision"]["all"]["numerator"] == expected_s1
    result = runs.compare(run_a, run_b)
    changed = {change["metric"]: change for change in result["metrics"]}
    assert changed["S7_format.all"] == {"metric": "S7_format.all", "a": 1.0, "b": 0.0, "delta": -1.0}
    assert len(result["units_changed"]) == 42
    assert all(item["a"]["valid"] and not item["b"]["valid"] for item in result["units_changed"])
    assert result["units_only_in_a"] == result["units_only_in_b"] == []
    same = runs.compare(run_a, runs.load_run(first, packs))
    assert same["metrics"] == [] and same["units_changed"] == []


def test_score_and_compare_from_the_command_line(stub, home, demo, tmp_path):
    url, state = stub
    packs = demo[2]
    first = _run(url, demo, home, "a", "stub-model-a")
    state.fail_first = len(state.chat_requests()) + 2
    second = _run(url, demo, home, "b", "stub-model-b")
    result = runner.invoke(app, ["score", str(first), "--packs", str(packs)])
    assert result.exit_code == 0, result.output
    assert "S1 decision: " in result.output and "S7 format: 1.0000 (42/42)" in result.output
    assert "S5 invariance MR5: violations" in result.output and "S6 spread of S1_decision" in result.output
    data = json.loads((first / "profile.json").read_text(encoding="utf-8"))
    assert data["kind"] == "profile" and data["run_status"] == "complete"
    result = runner.invoke(app, ["score", str(second), "--packs", str(packs)])
    assert result.exit_code == 0 and "40 answered" in result.output and "2 without answer" in result.output
    out = tmp_path / "comparison.json"
    result = runner.invoke(app, ["compare", str(first), str(second), "--out", str(out), "--packs", str(packs)])
    assert result.exit_code == 0, result.output
    assert "units changed: 2" in result.output
    comparison = json.loads(out.read_text(encoding="utf-8"))
    assert {item["b"] for item in comparison["units_changed"]} == {None}


def test_runs_that_cannot_be_scored(stub, home, demo, tmp_path):
    url, _ = stub
    packs = demo[2]
    first = _run(url, demo, home, "a", "stub-model-a")
    with pytest.raises(runs.ScoringError, match=r"manifest\.json: file is missing"):
        runs.load_run(tmp_path, packs)
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "manifest.json").write_text(json.dumps({**manifest, "kind": "collection"}), encoding="utf-8")
    with pytest.raises(runs.ScoringError, match="not a run manifest"):
        runs.load_run(broken, packs)
    (broken / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(runs.ScoringError, match=r"units\.jsonl: file is missing"):
        runs.load_run(broken, packs)
    (broken / "units.jsonl").write_text('{"unit_id": "X@zh", "item_id": "DEM-000099", "case_id": "x", "lang": "zh"}\n')
    with pytest.raises(runs.ScoringError, match="no key for DEM-000099"):
        runs.load_run(broken, packs)
    (broken / "units.jsonl").write_text("{oops\n", encoding="utf-8")
    with pytest.raises(runs.ScoringError, match=r"units\.jsonl:1"):
        runs.load_run(broken, packs)
    (broken / "manifest.json").write_text("{", encoding="utf-8")
    with pytest.raises(runs.ScoringError, match=r"manifest\.json"):
        runs.load_run(broken, packs)
    directory, variants, _ = demo
    (variants / sets.VARIANTS_FILE).write_bytes(b"")
    with pytest.raises(runs.ScoringError, match="not the variant set the run used"):
        runs.load_run(first, packs)
    (directory / collection.CASES_FILE).write_bytes(b"")
    with pytest.raises(runs.ScoringError, match="not the cases the run used"):
        runs.load_run(first, packs)
    result = runner.invoke(app, ["score", str(first), "--packs", str(packs)])
    assert result.exit_code == 1 and "not the cases the run used" in result.output
    result = runner.invoke(app, ["compare", str(first), str(first), "--packs", str(packs)])
    assert result.exit_code == 1
