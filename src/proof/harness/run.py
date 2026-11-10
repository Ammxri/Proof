"""Test run (PR-F07, PR-N01, PR-N02, PR-N03, PR-N05, UF-02): every unit of a collection sent to one provider.

A *unit* is one item in one language: a base case, or a variant with a request of its own (MR1 to MR4, MR6, MR7;
MR5 compares base answers, A-74). Its messages are the system prompt of the language and the item's text; its
request hash keys the cache (A-19).

A run lives in ``$PROOF_HOME/runs/<run id>/``:

- ``manifest.json`` (PR-N01, PR-N02): time stamps (UTC), versions, git commit (as the run or its resumption started),
  platform; the complete provider configuration without secrets, temperature 0, the declared origin and region;
  collection and variant set with their hashes and seeds; hashes of every system prompt and template; the model
  versions the replies name and, for Ollama, the model's digest; units, tokens, costs and run time; status
  ``complete`` or ``incomplete``.
- ``units.jsonl``: one line per unit with its request hash, status, the answer text, tokens and time.

A unit that fails gets the status ``error`` and is not sent again (A-36); ``--resume`` sends only units without an
answer. A run repeated from its manifest builds the same requests; with the cache it needs no HTTP at all.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, ValidationError

import proof
from proof.cases import collection as collections
from proof.cases.model import Case
from proof.core.hashing import sha256_bytes, sha256_text
from proof.core.i18n import LANGUAGES
from proof.core.manifest import GitState, ManifestBase, git_state, new_manifest, utc_now
from proof.core.paths import proof_home
from proof.harness.cache import Cache
from proof.harness.client import Client, Message, Reply, request_hash
from proof.harness.providers import PRICE_NOT_GIVEN, TEMPERATURE, Provider, ProviderError, api_key
from proof.render.case_text import render_case
from proof.render.prompt import messages as chat_messages
from proof.render.prompt import system_prompt
from proof.render.templating import template_hashes
from proof.variants import sets as variant_sets
from proof.variants.generator import REQUESTED_MRS
from proof.variants.render import render_variant
from proof_rules import loader
from proof_rules.model import Domain

MANIFEST_FILE = "manifest.json"
UNITS_FILE = "units.jsonl"
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Language = Literal["zh", "en", "de"]
Count = Annotated[StrictInt, Field(ge=0)]


class RunError(Exception):
    """A run cannot start or continue; ``problems`` lists every finding."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Configuration and manifest --------------------------------------------------------------------------------------


class RunConfig(_Model):
    """Everything a run needs to be repeated: provider, collection, variant set, languages, selection."""

    provider: Provider
    collection: str
    collection_sha256: Sha256
    variants: str | None = None
    variants_sha256: Sha256 | None = None
    langs: Annotated[tuple[Language, ...], Field(min_length=1)] = ("zh", "en", "de")
    max_cases: Annotated[StrictInt, Field(ge=1)] | None = None


class Seeds(_Model):
    collection_seed_start: Count
    collection_n: Count
    variant_seed: Count | None
    model_seed: StrictInt | None


class UnitCounts(_Model):
    total: Count
    ok: Count
    error: Count
    open: Count
    from_cache: Count
    requests: Count


class Tokens(_Model):
    prompt: Count
    completion: Count


class Cost(_Model):
    amount: float
    currency: str


class RunManifest(ManifestBase):
    """``manifest.json`` of a run."""

    kind: Literal["run"] = "run"
    run_id: str
    status: Literal["running", "complete", "incomplete"]
    started_utc: str
    finished_utc: str | None
    seconds: float
    config: RunConfig
    temperature: Literal[0] = TEMPERATURE
    seeds: Seeds
    models_reported: tuple[str, ...]
    ollama: dict[str, Any] | None
    prompts_sha256: dict[str, Sha256]
    templates_sha256: dict[str, Sha256]
    requests_sha256: Sha256
    units: UnitCounts
    tokens: Tokens
    tokens_billed: Tokens
    cost: Cost | Literal["Preis nicht angegeben"]


def manifest_text(manifest: RunManifest) -> str:
    return json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def read_manifest(path: Path) -> RunManifest:
    if path.is_dir() or path.suffix != ".json":
        path = path / MANIFEST_FILE
    if not path.is_file():
        raise RunError([f"{path}: file is missing"])
    try:
        return RunManifest.model_validate_json(path.read_bytes())
    except ValidationError as exc:
        raise RunError([f"{path}: {exc}"]) from exc


# --- Units -----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Unit:
    unit_id: str
    item_id: str
    case_id: str
    mr: str | None
    lang: str
    messages: tuple[Message, ...]
    request_hash: str


@dataclass(frozen=True)
class Plan:
    """The units of a run and what they were built from."""

    config: RunConfig
    domain: Domain
    collection: collections.CollectionManifest
    variant_set: variant_sets.VariantSetManifest | None
    prompts: dict[str, str]
    units: tuple[Unit, ...]


def _read_collection(path: Path) -> tuple[collections.CollectionManifest, list[Case]]:
    manifest_path = path / collections.MANIFEST_FILE
    if not manifest_path.is_file():
        raise RunError([f"{manifest_path}: file is missing"])
    try:
        manifest = collections.CollectionManifest.model_validate_json(manifest_path.read_bytes())
    except ValidationError as exc:
        raise RunError([f"{manifest_path}: {exc}"]) from exc
    problems: list[str] = []
    cases_path = path / collections.CASES_FILE
    if not cases_path.is_file() or sha256_bytes(cases_path.read_bytes()) != manifest.cases_sha256:
        raise RunError([f"{cases_path}: missing or not the cases collection.json names"])
    cases = [case for _, case in collections.read_cases(cases_path, problems)]
    if problems:
        raise RunError(problems)
    return manifest, cases


def plan(config: RunConfig, root: Path = loader.PACKS_ROOT) -> Plan:
    """Build every unit of a run from its configuration; checks that collection and variants are the ones named."""
    collection_dir = Path(config.collection)
    manifest, cases = _read_collection(collection_dir)
    if manifest.cases_sha256 != config.collection_sha256:
        raise RunError([f"{collection_dir}: the collection changed since the run was configured"])
    domain = loader.load_domain(manifest.domain, root)
    variant_set = None
    variants: dict[str, list[Any]] = {}
    if config.variants is not None:
        directory = Path(config.variants)
        try:
            variant_set = variant_sets.VariantSetManifest.model_validate_json(
                (directory / variant_sets.MANIFEST_FILE).read_bytes()
            )
            data = (directory / variant_sets.VARIANTS_FILE).read_bytes()
        except (OSError, ValidationError) as exc:
            raise RunError([f"{directory}: {exc}"]) from exc
        if sha256_bytes(data) != config.variants_sha256 or variant_set.variants_sha256 != config.variants_sha256:
            raise RunError([f"{directory}: the variant set changed since the run was configured"])
        if variant_set.collection_sha256 != manifest.cases_sha256:
            raise RunError([f"{directory}: the variant set belongs to another collection"])
        problems: list[str] = []
        for _, variant in variant_sets.read_variants(directory / variant_sets.VARIANTS_FILE, problems):
            if variant.mr in REQUESTED_MRS:
                variants.setdefault(variant.case_id, []).append(variant)
        if problems:
            raise RunError(problems)
    prompts = {lang: system_prompt(domain, lang) for lang in config.langs}
    chosen = cases[: config.max_cases] if config.max_cases is not None else cases
    units = []
    for case in chosen:
        items: list[tuple[str, str | None, Callable[[str], str]]] = [
            (case.case_id, None, lambda lang, case=case: render_case(case, domain, lang).text)
        ]
        for variant in variants.get(case.case_id, []):
            items.append(
                (
                    variant.variant_id,
                    variant.mr,
                    lambda lang, v=variant, c=case: render_variant(v, c, domain, lang).text,
                )
            )
        for item_id, mr, text in items:
            for lang in config.langs:
                messages = tuple(chat_messages(prompts[lang], text(lang)))
                units.append(
                    Unit(
                        unit_id=f"{item_id}@{lang}",
                        item_id=item_id,
                        case_id=case.case_id,
                        mr=mr,
                        lang=lang,
                        messages=messages,
                        request_hash=request_hash(config.provider, messages),
                    )
                )
    return Plan(
        config=config, domain=domain, collection=manifest, variant_set=variant_set, prompts=prompts, units=tuple(units)
    )


def configure(
    provider: Provider,
    collection_dir: Path,
    *,
    variants_dir: Path | None = None,
    langs: Sequence[str] = LANGUAGES,
    max_cases: int | None = None,
) -> RunConfig:
    """A run configuration for a collection (and variant set) as they are on disk now."""
    unknown = sorted(set(langs) - set(LANGUAGES))
    if unknown or not langs:
        raise RunError([f"languages must be some of {', '.join(LANGUAGES)}, got {', '.join(langs) or 'none'}"])
    manifest, _ = _read_collection(collection_dir)
    variants_sha = None
    if variants_dir is not None:
        path = variants_dir / variant_sets.VARIANTS_FILE
        if not path.is_file():
            raise RunError([f"{path}: file is missing"])
        variants_sha = sha256_bytes(path.read_bytes())
    try:
        return RunConfig(
            provider=provider,
            collection=collection_dir.as_posix(),
            collection_sha256=manifest.cases_sha256,
            variants=None if variants_dir is None else variants_dir.as_posix(),
            variants_sha256=variants_sha,
            langs=tuple(lang for lang in LANGUAGES if lang in langs),
            max_cases=max_cases,
        )
    except ValidationError as exc:
        raise RunError([str(exc)]) from exc


# --- Running ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    directory: Path
    manifest: RunManifest


def new_run_id(provider: Provider) -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{provider.name}"


def _read_units(path: Path) -> dict[str, dict[str, Any]]:
    """The latest record of each unit in a units file (records are appended while a run is going)."""
    latest: dict[str, dict[str, Any]] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                latest[record["unit_id"]] = record
    return latest


def _record(unit: Unit, reply: Reply, cached: bool, seconds: float) -> dict[str, Any]:
    return {
        "unit_id": unit.unit_id,
        "item_id": unit.item_id,
        "case_id": unit.case_id,
        "mr": unit.mr,
        "lang": unit.lang,
        "request_hash": unit.request_hash,
        "cached": cached,
        "seconds": round(seconds, 3),
        **reply.to_json(),
    }


def _line(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def _cost(provider: Provider, billed: Tokens) -> Cost | str:
    if provider.pricing is None:
        return PRICE_NOT_GIVEN
    pricing = provider.pricing
    amount = (billed.prompt * pricing.input_per_mtok + billed.completion * pricing.output_per_mtok) / 1_000_000
    return Cost(amount=round(float(amount), 6), currency=pricing.currency)


def _manifest(
    run_plan: Plan,
    run_id: str,
    records: dict[str, dict[str, Any]],
    started: str,
    seconds: float,
    ollama: dict[str, Any] | None,
    git: GitState | None,
    finished: bool,
) -> RunManifest:
    config = run_plan.config
    units = run_plan.units
    states = [records.get(unit.unit_id) for unit in units]
    ok = [record for record in states if record and record["status"] == "ok"]
    errors = sum(1 for record in states if record and record["status"] == "error")
    fresh = [record for record in ok if not record["cached"]]
    sent = sum(1 for record in states if record and not record["cached"])

    def tokens(items: list[dict[str, Any]]) -> Tokens:
        return Tokens(
            prompt=sum(item["prompt_tokens"] or 0 for item in items),
            completion=sum(item["completion_tokens"] or 0 for item in items),
        )

    billed = tokens(fresh)
    templates: dict[str, str] = {}
    for lang in config.langs:
        templates.update(template_hashes(lang, [run_plan.domain]))
    base = new_manifest("run")
    status = "running" if not finished else ("complete" if len(ok) == len(units) else "incomplete")
    return RunManifest(
        **{**base.model_dump(), "kind": "run", "git": git},
        run_id=run_id,
        status=status,
        started_utc=started,
        finished_utc=utc_now() if finished else None,
        seconds=round(seconds, 3),
        config=config,
        seeds=Seeds(
            collection_seed_start=run_plan.collection.seed_start,
            collection_n=run_plan.collection.n,
            variant_seed=None if run_plan.variant_set is None else run_plan.variant_set.variant_seed,
            model_seed=config.provider.params.seed,
        ),
        models_reported=tuple(sorted({record["model"] for record in ok if record["model"]})),
        ollama=ollama,
        prompts_sha256={lang: sha256_text(text) for lang, text in run_plan.prompts.items()},
        templates_sha256=dict(sorted(templates.items())),
        requests_sha256=sha256_text("\n".join(unit.request_hash for unit in units)),
        units=UnitCounts(
            total=len(units),
            ok=len(ok),
            error=errors,
            open=len(units) - len(ok) - errors,
            from_cache=sum(1 for record in ok if record["cached"]),
            requests=sent,
        ),
        tokens=tokens(ok),
        tokens_billed=billed,
        cost=_cost(config.provider, billed),
    )


def _write_manifest(directory: Path, manifest: RunManifest) -> None:
    temporary = directory / (MANIFEST_FILE + ".tmp")
    temporary.write_bytes(manifest_text(manifest).encode("utf-8"))
    os.replace(temporary, directory / MANIFEST_FILE)


def execute(
    config: RunConfig,
    directory: Path | None = None,
    *,
    resume: bool = False,
    root: Path = loader.PACKS_ROOT,
    environ: dict[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    progress: Callable[[int, int, Unit, Reply, bool], None] | None = None,
) -> Outcome:
    """Run (or resume) a test run; returns the run directory and its final manifest."""
    provider = config.provider
    # The code that answers the units is the code at the start; a commit made while the run goes on is not it.
    git = git_state(Path(proof.__file__).resolve().parent)
    run_plan = plan(config, root)
    try:
        key = api_key(provider, environ)
    except ProviderError as exc:
        raise RunError(exc.problems) from exc
    if directory is None:
        directory = proof_home() / "runs" / new_run_id(provider)
    units_path = directory / UNITS_FILE
    records: dict[str, dict[str, Any]] = {}
    started = utc_now()
    if resume:
        previous = read_manifest(directory)
        if previous.config != config:
            raise RunError([f"{directory}: --resume needs the configuration the run started with"])
        records = _read_units(units_path)
        started = previous.started_utc
        run_id = previous.run_id
    else:
        if directory.exists() and any(directory.iterdir()):
            raise RunError([f"{directory}: already holds a run; use --resume or another directory"])
        run_id = directory.name
    directory.mkdir(parents=True, exist_ok=True)
    cache = Cache(proof_home() / "cache")
    clock = time.perf_counter()
    with Client(provider, key, transport=transport) as client:
        ollama = client.ollama_info() if provider.ollama_digest else None
        _write_manifest(directory, _manifest(run_plan, run_id, records, started, 0.0, ollama, git, finished=False))
        with units_path.open("a", encoding="utf-8", newline="\n") as log:
            todo = [unit for unit in run_plan.units if records.get(unit.unit_id, {}).get("status") != "ok"]
            for number, unit in enumerate(todo, start=1):
                began = time.perf_counter()
                reply = cache.get(unit.request_hash)
                cached = reply is not None
                if reply is None:
                    reply = client.chat(unit.messages)
                    cache.put(unit.request_hash, reply)
                record = _record(unit, reply, cached, time.perf_counter() - began)
                records[unit.unit_id] = record
                log.write(_line(record))
                log.flush()
                if progress is not None:
                    progress(number, len(todo), unit, reply, cached)
    final = _manifest(run_plan, run_id, records, started, time.perf_counter() - clock, ollama, git, finished=True)
    ordered = [records[unit.unit_id] for unit in run_plan.units if unit.unit_id in records]
    temporary = directory / (UNITS_FILE + ".tmp")
    temporary.write_text("".join(_line(record) for record in ordered), encoding="utf-8", newline="\n")
    os.replace(temporary, units_path)
    _write_manifest(directory, final)
    return Outcome(directory=directory, manifest=final)


def read_units(directory: Path) -> list[dict[str, Any]]:
    """The unit records of a run, in unit order."""
    return list(_read_units(directory / UNITS_FILE).values())
