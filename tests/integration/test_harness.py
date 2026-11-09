"""Test run against the local stub (PR-F07, PR-N01, PR-N02, PR-N03, PR-N05, A-19, A-36, KONZEPT U7)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from proof.cases import collection
from proof.cli import app
from proof.harness import run as harness_run
from proof.harness.providers import PRICE_NOT_GIVEN, Provider, ProviderError, parse_provider
from proof.variants import sets

CANARY = "proof-canary-SECRET-4711"
KEY_ENV = "PROOF_TEST_API_KEY"
runner = CliRunner()


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "home"
    monkeypatch.setenv("PROOF_HOME", str(path))
    monkeypatch.setenv(KEY_ENV, CANARY)
    return path


@pytest.fixture
def demo(tmp_path, fixture_packs) -> tuple[Path, Path, Path]:
    """A demo collection of 4 cases with a variant set (seed 2), and the packs it was built from."""
    packs = tmp_path / "packs"
    shutil.copytree(fixture_packs, packs)
    directory = tmp_path / "demo-4"
    collection.write(collection.build("demo", 4, 1, name="demo-4", root=packs), directory)
    variants = sets.default_directory(directory, 2)
    sets.write(sets.build(directory, 2, root=packs), variants)
    return directory, variants, packs


def _provider(base_url: str, **changes) -> Provider:
    data = {
        "name": "stub",
        "api": "openai_chat",
        "base_url": base_url,
        "model": "stub-model",
        "api_key_env": KEY_ENV,
        "origin": "other",
        "region": "CN",
        "ollama_digest": True,
        "params": {"max_tokens": 64, "seed": 7},
        "pricing": {"input_per_mtok": 1.5, "output_per_mtok": 3, "currency": "EUR"},
        "timeout_seconds": 10,
    }
    data.update(changes)
    return Provider.model_validate(data)


def _config(provider: Provider, demo, **options) -> harness_run.RunConfig:
    directory, variants, _ = demo
    return harness_run.configure(provider, directory, variants_dir=variants, **options)


def _files_text(*roots: Path) -> str:
    texts = []
    for root in roots:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                texts.append(path.read_bytes().decode("utf-8", errors="replace"))
    return "\n".join(texts)


def test_a_run_sends_every_unit_once_with_temperature_zero(stub, home, demo):
    """PR-N05: temperature 0 in every request, no JSON mode, no streaming; MR5 has no request."""
    url, state = stub
    config = _config(_provider(url), demo)
    outcome = harness_run.execute(config, home / "runs" / "one", root=demo[2])
    manifest = outcome.manifest
    # 4 base cases, 4 MR1 and 4 MR3 variants, each in 3 languages.
    assert manifest.units.total == 36 == manifest.units.ok == manifest.units.requests
    assert manifest.status == "complete"
    chats = state.chat_requests()
    assert len(chats) == 36
    for request in chats:
        body = request["body"]
        assert body["temperature"] == 0 and body["stream"] is False
        assert body["max_tokens"] == 64 and body["seed"] == 7 and body["model"] == "stub-model"
        assert "response_format" not in body and "tools" not in body
        assert [message["role"] for message in body["messages"]] == ["system", "user"]
        assert request["headers"]["Authorization"] == f"Bearer {CANARY}"
    units = harness_run.read_units(outcome.directory)
    assert {unit["mr"] for unit in units} == {None, "MR1", "MR3"}
    assert {unit["lang"] for unit in units} == {"zh", "en", "de"}


def test_the_manifest_records_what_repeats_the_run(stub, home, demo):
    """PR-N01, PR-N02: seed, model version, parameters, time stamps, tokens and costs."""
    url, _ = stub
    outcome = harness_run.execute(_config(_provider(url), demo), home / "runs" / "m", root=demo[2])
    data = json.loads((outcome.directory / "manifest.json").read_text(encoding="utf-8"))
    assert data["kind"] == "run" and data["temperature"] == 0
    assert data["seeds"] == {"collection_seed_start": 1, "collection_n": 4, "variant_seed": 2, "model_seed": 7}
    assert data["models_reported"] == ["stub-model"]
    assert data["ollama"] == {
        "version": "0.0.0-stub",
        "digest": "d" * 64,
        "details": {"parameter_size": "1B", "quantization_level": "Q4_K_M"},
    }
    assert data["config"]["provider"]["params"] == {
        "max_tokens": 64,
        "seed": 7,
        "top_p": None,
        "think": None,
        "thinking": None,
        "reasoning_effort": None,
    }
    assert data["config"]["provider"]["api_key_env"] == KEY_ENV
    assert data["started_utc"] <= data["finished_utc"] and data["created_utc"]
    assert data["tokens"]["completion"] == 36 * 20 and data["tokens"]["prompt"] > 0
    tokens = data["tokens_billed"]
    expected = round((tokens["prompt"] * 1.5 + tokens["completion"] * 3) / 1_000_000, 6)
    assert data["cost"] == {"amount": expected, "currency": "EUR"}
    assert set(data["prompts_sha256"]) == {"zh", "en", "de"}
    assert "templates/zh/case.j2" in data["templates_sha256"] and "labels/demo/de" in data["templates_sha256"]
    assert data["config"]["provider"]["origin"] == "other" and data["config"]["provider"]["region"] == "CN"
    assert data["platform"]["python"]


def test_cached_replies_need_no_http_and_a_repeat_has_the_same_requests(stub, home, demo):
    """A-19, PR-N01: a run repeated from its manifest builds the same request hashes and is served from the cache."""
    url, state = stub
    first = harness_run.execute(_config(_provider(url), demo), home / "runs" / "a", root=demo[2])
    sent = len(state.chat_requests())
    config = harness_run.read_manifest(first.directory).config
    second = harness_run.execute(config, home / "runs" / "b", root=demo[2])
    assert len(state.chat_requests()) == sent, "no HTTP request for cached replies"
    assert second.manifest.requests_sha256 == first.manifest.requests_sha256
    assert second.manifest.units.from_cache == second.manifest.units.total
    assert second.manifest.units.requests == 0
    assert second.manifest.tokens_billed.prompt == 0 and second.manifest.cost.amount == 0
    hashes = [unit["request_hash"] for unit in harness_run.read_units(first.directory)]
    assert hashes == [unit["request_hash"] for unit in harness_run.read_units(second.directory)]


def test_no_second_attempt_after_an_invalid_answer(stub, home, demo):
    """PR-N05: an answer that is no JSON is stored as it is; the unit is not asked again."""
    url, state = stub
    state.mode = "invalid"
    outcome = harness_run.execute(_config(_provider(url), demo, max_cases=1, langs=["de"]), home / "r", root=demo[2])
    units = harness_run.read_units(outcome.directory)
    assert len(units) == 3 == len(state.chat_requests())
    assert {unit["text"] for unit in units} == {"Here is my answer: pneumonia."}
    assert outcome.manifest.status == "complete"


def test_errors_are_recorded_not_retried_and_resume_sends_only_open_units(stub, home, demo):
    """A-36: a failed unit is an error; --resume sends only units without an answer."""
    url, state = stub
    state.fail_first = 2
    config = _config(_provider(url), demo, max_cases=1)
    directory = home / "runs" / "resume"
    outcome = harness_run.execute(config, directory, root=demo[2])
    assert outcome.manifest.status == "incomplete"
    assert (outcome.manifest.units.error, outcome.manifest.units.ok) == (2, 7)
    assert len(state.chat_requests()) == 9, "no automatic retry"
    errors = [unit for unit in harness_run.read_units(directory) if unit["status"] == "error"]
    assert all(CANARY not in unit["error"] and "***" in unit["error"] for unit in errors)
    resumed = harness_run.execute(config, directory, resume=True, root=demo[2])
    assert len(state.chat_requests()) == 11, "only the two failed units are sent again"
    assert resumed.manifest.status == "complete" and resumed.manifest.units.ok == 9
    assert resumed.manifest.run_id == outcome.manifest.run_id
    assert len(harness_run.read_units(directory)) == 9
    lines = (directory / "units.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 9, "the units file holds one line per unit after the run"


def test_resume_needs_the_same_configuration_and_runs_need_an_empty_directory(stub, home, demo):
    url, _ = stub
    config = _config(_provider(url), demo, max_cases=1)
    directory = home / "runs" / "x"
    harness_run.execute(config, directory, root=demo[2])
    with pytest.raises(harness_run.RunError, match="already holds a run"):
        harness_run.execute(config, directory, root=demo[2])
    other = _config(_provider(url), demo, max_cases=2)
    with pytest.raises(harness_run.RunError, match="--resume needs the configuration"):
        harness_run.execute(other, directory, resume=True, root=demo[2])


def test_no_secret_is_stored_anywhere(stub, home, demo):
    """KONZEPT U7: the canary key reaches the server in the header and nowhere else."""
    url, state = stub
    state.fail_first = 1
    directory = home / "runs" / "secret"
    harness_run.execute(_config(_provider(url), demo, max_cases=1), directory, root=demo[2])
    assert CANARY in state.chat_requests()[0]["headers"]["Authorization"]
    assert CANARY not in _files_text(home)
    assert KEY_ENV in (directory / "manifest.json").read_text(encoding="utf-8")


def test_redirects_and_broken_replies_are_errors(stub, home, demo):
    url, state = stub
    state.mode = "redirect"
    outcome = harness_run.execute(_config(_provider(url), demo, max_cases=1, langs=["en"]), home / "a", root=demo[2])
    assert outcome.manifest.units.error == 3 and len(state.chat_requests()) == 3
    assert {unit["error"][:8] for unit in harness_run.read_units(outcome.directory)} == {"HTTP 302"}
    state.mode = "empty"
    outcome = harness_run.execute(_config(_provider(url), demo, max_cases=1, langs=["en"]), home / "b", root=demo[2])
    assert "no choices[0].message.content" in harness_run.read_units(outcome.directory)[0]["error"]


def test_unreachable_endpoints_are_errors(home, demo):
    provider = _provider("http://127.0.0.1:9/v1", timeout_seconds=2, ollama_digest=False)
    outcome = harness_run.execute(_config(provider, demo, max_cases=1, langs=["zh"]), home / "c", root=demo[2])
    assert outcome.manifest.units.error == 3
    assert outcome.manifest.ollama is None


def test_missing_prices_and_keys(stub, home, demo, monkeypatch):
    """A-20: without prices the manifest says so; without the key's variable no run starts."""
    url, _ = stub
    provider = _provider(url, pricing=None)
    outcome = harness_run.execute(_config(provider, demo, max_cases=1, langs=["zh"]), home / "p", root=demo[2])
    assert outcome.manifest.cost == PRICE_NOT_GIVEN
    monkeypatch.delenv(KEY_ENV)
    with pytest.raises(harness_run.RunError, match=f"environment variable {KEY_ENV} is not set"):
        harness_run.execute(_config(_provider(url), demo, max_cases=1), home / "q", root=demo[2])


def test_western_providers_need_the_eu(stub, home, demo):
    """PR-N03: refused without EU; with EU the run records origin and declared region."""
    url, _ = stub
    with pytest.raises(ValueError, match="only via EU servers"):
        _provider(url, origin="western", region="US")
    outcome = harness_run.execute(
        _config(_provider(url, origin="western", region="EU"), demo, max_cases=1, langs=["de"]),
        home / "eu",
        root=demo[2],
    )
    provider = outcome.manifest.config.provider
    assert (provider.origin, provider.region) == ("western", "EU")
    with pytest.raises(ProviderError, match="only via EU servers"):
        parse_provider({**_provider(url).model_dump(mode="json"), "origin": "western", "region": "CN"}, "x.yaml")


def test_runs_check_their_inputs(stub, home, demo, tmp_path):
    url, _ = stub
    directory, variants, packs = demo
    config = _config(_provider(url), demo)
    (variants / sets.VARIANTS_FILE).write_bytes((variants / sets.VARIANTS_FILE).read_bytes()[:-1] + b"\n\n")
    with pytest.raises(harness_run.RunError, match="variant set changed"):
        harness_run.execute(config, home / "v", root=packs)
    with pytest.raises(harness_run.RunError, match=r"variants\.jsonl: file is missing"):
        harness_run.configure(_provider(url), directory, variants_dir=tmp_path)
    with pytest.raises(harness_run.RunError, match="languages must be some of"):
        harness_run.configure(_provider(url), directory, langs=["fr"])
    with pytest.raises(harness_run.RunError, match=r"collection\.json: file is missing"):
        harness_run.configure(_provider(url), tmp_path)
    with (directory / collection.CASES_FILE).open("ab") as handle:
        handle.write(b"\n")
    with pytest.raises(harness_run.RunError, match="missing or not the cases"):
        harness_run.configure(_provider(url), directory)


def test_command_line_runs(stub, home, demo, tmp_path):
    url, state = stub
    directory, variants, packs = demo
    provider_file = tmp_path / "stub.yaml"
    provider_file.write_text(json.dumps(_provider(url).model_dump(mode="json")), encoding="utf-8")
    out = tmp_path / "run1"
    args = ["run", "--provider", str(provider_file), "--set", str(directory), "--variants", str(variants)]
    result = runner.invoke(app, [*args, "--max-cases", "1", "--lang", "zh", "--out", str(out), "--packs", str(packs)])
    assert result.exit_code == 0, result.output
    assert "complete" in result.output and "units: 3 ok, 0 error, 0 open of 3; 3 requests" in result.output
    assert "1/3 DEM-000001@zh: ok (request)" in result.output and "ollama: " in result.output
    result = runner.invoke(app, ["run", "--from-manifest", str(out / "manifest.json"), "--packs", str(packs)])
    assert result.exit_code == 0, result.output
    assert "(cache)" in result.output and "0 requests" in result.output
    state.fail_first = len(state.chat_requests()) + 1
    out2 = tmp_path / "run2"
    result = runner.invoke(app, [*args, "--lang", "en", "--max-cases", "1", "--out", str(out2), "--packs", str(packs)])
    assert result.exit_code == 1 and "incomplete" in result.output
    result = runner.invoke(app, ["run", "--resume", str(out2), "--packs", str(packs)])
    assert result.exit_code == 0, result.output
    assert "units: 3 ok" in result.output
    assert CANARY not in result.output


@pytest.mark.parametrize(
    ("args", "message"),
    [
        ([], "choose exactly one of --provider"),
        (["--provider", "providers/qwen-local.yaml", "--resume", "x"], "choose exactly one"),
        (["--provider", "providers/qwen-local.yaml"], "--provider needs --set"),
        (["--provider", "providers/western-eu.yaml", "--set", "data/collections/fever-100"], "placeholder not filled"),
        (["--resume", "nowhere"], "manifest.json: file is missing"),
    ],
)
def test_command_line_errors(args, message, repo_root, monkeypatch):
    monkeypatch.chdir(repo_root)
    result = runner.invoke(app, ["run", *args])
    assert result.exit_code == 1
    assert message in result.output


def test_ollama_api_runs_without_thinking(stub, home, demo):
    """D-12: Ollama's own API with thinking off; temperature 0 under options; the answer excludes any thinking."""
    url, state = stub
    params = {"max_tokens": 64, "seed": 7, "think": False}
    provider = _provider(url.removesuffix("/v1"), api="ollama_chat", api_key_env=None, params=params)
    outcome = harness_run.execute(_config(provider, demo, max_cases=1, langs=["zh"]), home / "o", root=demo[2])
    assert outcome.manifest.status == "complete" and outcome.manifest.units.ok == 3
    for request in state.chat_requests():
        assert request["path"] == "/api/chat"
        body = request["body"]
        assert body["think"] is False and body["stream"] is False and "temperature" not in body
        assert body["options"] == {"temperature": 0, "num_predict": 64, "seed": 7}
    units = harness_run.read_units(outcome.directory)
    assert all(json.loads(unit["text"])["rationale"] == "stub" for unit in units)
    assert units[0]["completion_tokens"] == 20 and units[0]["finish_reason"] == "stop"
    assert outcome.manifest.ollama["digest"] == "d" * 64
    state.mode = "empty"
    empty = harness_run.execute(_config(provider, demo, max_cases=1, langs=["de"]), home / "o2", root=demo[2])
    assert "no message.content" in harness_run.read_units(empty.directory)[0]["error"]
