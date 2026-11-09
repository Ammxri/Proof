"""``proof cases build`` and ``proof cases validate`` (UF-01, first steps)."""

from __future__ import annotations

from typer.testing import CliRunner

from proof.cli import app

runner = CliRunner()


def test_build_and_validate(tmp_path, fixture_packs):
    out = tmp_path / "demo-9"
    result = runner.invoke(
        app, ["cases", "build", "--domain", "demo", "--n", "9", "--seed-start", "1", "--packs", str(fixture_packs),
              "--out", str(out)],
    )  # fmt: skip
    assert result.exit_code == 0, result.output
    assert "demo-9: 9 cases, seeds 1-9" in result.output
    assert "relabeled: 0 of 9" in result.output
    assert "determinability: answer" in result.output
    assert "slowest case (sampling, key with ablation):" in result.output
    assert (out / "cases.jsonl").is_file() and (out / "collection.json").is_file()
    result = runner.invoke(app, ["cases", "validate", str(out), "--packs", str(fixture_packs)])
    assert result.exit_code == 0, result.output
    assert "9 cases valid, 0 relabeled" in result.output


def test_build_writes_to_the_default_directory(tmp_path, fixture_packs, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = ["cases", "build", "--domain", "demo", "--n", "3", "--seed-start", "5", "--packs", str(fixture_packs)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert (tmp_path / "data/collections/demo-3/cases.jsonl").is_file()


def test_errors_exit_with_status_1(tmp_path, fixture_packs):
    result = runner.invoke(app, ["cases", "build", "--domain", "demo", "--n", "0", "--seed-start", "1",
                                 "--packs", str(fixture_packs), "--out", str(tmp_path / "x")])  # fmt: skip
    assert result.exit_code == 1
    assert "n must be at least 1" in result.output
    broken = tmp_path / "broken.jsonl"
    broken.write_text('{"case_id": "DEM-000001"}\n', encoding="utf-8")
    result = runner.invoke(app, ["cases", "validate", str(broken), "--packs", str(fixture_packs)])
    assert result.exit_code == 1
    assert "problem(s)" in result.output
    assert "Field required" in result.output
