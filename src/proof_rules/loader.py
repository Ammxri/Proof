"""Loading and checking rule packs.

A pack is a directory with ``pack.yaml``, ``catalog.yaml``, ``vocabulary.yaml``, ``sources.yaml``, a ``rules/``
directory of YAML lists, for domains optional lab profiles in ``profiles/*.json`` and, for packs with migrated rules,
``migration.yaml``. Packs live side by side in one root directory; a domain may use library packs from the same root
and activates rules from them (A-08).

Loading checks the structure of every file and the references between them:
- every field, target and source a rule names exists, and comparisons fit the field type;
- ``requires`` matches the fields of the condition exactly, and every rule has a source (in the model);
- codes and ids are unique, test vectors use valid values;
- every reference limit an active rule needs is available from the domain's lab profiles;
- every numeric fact of a domain has physiological bounds with a source;
- the migration table and the rules' ``migrated_from`` agree in both directions.
``check`` additionally runs every rule's test vectors.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ValidationError

from proof.core import canonical, yamlio
from proof_rules.logic import MissingReferenceError, Truth, evaluate
from proof_rules.model import (
    ORDERED_OPS,
    Catalog,
    Compare,
    Domain,
    DomainSettings,
    FieldDef,
    MigrationTable,
    PackConfig,
    ProfileReference,
    RefBound,
    RefRange,
    Rule,
    SourceRegister,
    Vocabulary,
    comparisons,
    fields_of,
    reference_bounds_of,
)

PACKS_ROOT = Path(__file__).resolve().parent / "packs"
PACK_FILE = "pack.yaml"
CATALOG_FILE = "catalog.yaml"
VOCABULARY_FILE = "vocabulary.yaml"
SOURCES_FILE = "sources.yaml"
RULES_DIR = "rules"
PROFILES_DIR = "profiles"
MIGRATION_FILE = "migration.yaml"


class LoadError(Exception):
    """A pack or domain is invalid; ``problems`` lists every finding."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


@dataclass(frozen=True)
class Pack:
    name: str
    path: Path
    config: PackConfig
    catalog: Catalog
    vocabulary: Vocabulary
    sources: SourceRegister
    rules: tuple[Rule, ...]
    rule_files: Mapping[str, str]
    profiles: Mapping[str, ProfileReference]
    migration: MigrationTable | None = None

    @property
    def references(self) -> Mapping[str, RefRange]:
        return MappingProxyType({code: profile.reference for code, profile in self.profiles.items()})


# --- Reading files ---------------------------------------------------------------------------------------------------


def _pydantic_problems(exc: ValidationError, where: str) -> list[str]:
    problems = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(part) for part in error["loc"])
        message = error["msg"].removeprefix("Value error, ")
        problems.append(f"{where}: {location}: {message}" if location else f"{where}: {message}")
    return problems


def _read_yaml(path: Path, problems: list[str]) -> Any:
    if not path.is_file():
        problems.append(f"{path}: file is missing")
        return None
    try:
        return yamlio.load_file(path)
    except yamlio.YamlError as exc:
        problems.append(str(exc))
        return None


def _validate[M: BaseModel](model: type[M], data: Any, where: str, problems: list[str]) -> M | None:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems.extend(_pydantic_problems(exc, where))
        return None


def _read_model[M: BaseModel](model: type[M], path: Path, problems: list[str]) -> M | None:
    before = len(problems)
    data = _read_yaml(path, problems)
    if data is None:
        if len(problems) == before:
            problems.append(f"{path}: file is empty")
        return None
    if not isinstance(data, dict):
        problems.append(f"{path}: expected a mapping at the top level")
        return None
    return _validate(model, data, str(path), problems)


def _read_rules(directory: Path, problems: list[str]) -> tuple[list[Rule], dict[str, str]]:
    rules: list[Rule] = []
    files: dict[str, str] = {}
    if not directory.is_dir():
        problems.append(f"{directory}: directory is missing")
        return rules, files
    for path in sorted(directory.iterdir()):
        if path.suffix != ".yaml" or not path.is_file():
            problems.append(f"{path}: only .yaml files belong in {RULES_DIR}/")
            continue
        data = _read_yaml(path, problems)
        if data is None:
            continue
        if not isinstance(data, list):
            problems.append(f"{path}: expected a list of rules")
            continue
        for index, item in enumerate(data):
            label = item.get("id") if isinstance(item, dict) else None
            where = f"{path}[{index}]" + (f" {label}" if isinstance(label, str) else "")
            rule = _validate(Rule, item, where, problems)
            if rule is None:
                continue
            if rule.id in files:
                problems.append(f"{where}: duplicate rule id (also in {files[rule.id]})")
                continue
            files[rule.id] = path.name
            rules.append(rule)
    return rules, files


def _read_profiles(directory: Path, problems: list[str]) -> dict[str, ProfileReference]:
    profiles: dict[str, ProfileReference] = {}
    if not directory.exists():
        return profiles
    for path in sorted(directory.glob("*.json")):
        try:
            data = canonical.loads(path.read_bytes())
        except (ValueError, UnicodeDecodeError) as exc:
            problems.append(f"{path}: {exc}")
            continue
        profile = _validate(ProfileReference, data, str(path), problems)
        if profile is None:
            continue
        if profile.fact_code in profiles:
            problems.append(f"{path}: second profile for {profile.fact_code}")
            continue
        profiles[profile.fact_code] = profile
    return profiles


def read_pack(path: Path) -> Pack:
    """Read one pack and check its files on their own (no references to other packs yet)."""
    problems: list[str] = []
    config = _read_model(PackConfig, path / PACK_FILE, problems)
    catalog = _read_model(Catalog, path / CATALOG_FILE, problems)
    vocabulary = _read_model(Vocabulary, path / VOCABULARY_FILE, problems)
    sources = _read_model(SourceRegister, path / SOURCES_FILE, problems)
    rules, files = _read_rules(path / RULES_DIR, problems)
    profiles = _read_profiles(path / PROFILES_DIR, problems)
    migration_path = path / MIGRATION_FILE
    migration = _read_model(MigrationTable, migration_path, problems) if migration_path.exists() else None
    if config is not None and config.pack != path.name:
        problems.append(f"{path / PACK_FILE}: pack name {config.pack!r} differs from the directory name")
    if config is not None and config.kind == "library" and profiles:
        problems.append(f"{path / PROFILES_DIR}: only domain packs have lab profiles")
    if problems or config is None or catalog is None or vocabulary is None or sources is None:
        raise LoadError(problems)
    return Pack(
        name=config.pack,
        path=path,
        config=config,
        catalog=catalog,
        vocabulary=vocabulary,
        sources=sources,
        rules=tuple(sorted(rules, key=lambda rule: rule.id)),
        rule_files=MappingProxyType(files),
        profiles=MappingProxyType(profiles),
        migration=migration,
    )


# --- Checks across files and packs -----------------------------------------------------------------------------------


@dataclass
class _Context:
    """Everything a pack may refer to: its own definitions plus those of the packs it uses."""

    fields: dict[str, FieldDef] = field(default_factory=dict)
    field_pack: dict[str, str] = field(default_factory=dict)
    target_pack: dict[str, str] = field(default_factory=dict)
    source_pack: dict[str, str] = field(default_factory=dict)

    @property
    def targets(self) -> set[str]:
        return set(self.target_pack)

    @property
    def sources(self) -> set[str]:
        return set(self.source_pack)


def _context(packs: Iterable[Pack], problems: list[str]) -> _Context:
    context = _Context()
    for pack in packs:
        for definition in pack.catalog.fields:
            if definition.code in context.fields:
                owner = context.field_pack[definition.code]
                problems.append(f"{pack.name}: field {definition.code} is also defined in pack {owner}")
                continue
            context.fields[definition.code] = definition
            context.field_pack[definition.code] = pack.name
        for term in (*pack.vocabulary.ddx, *pack.vocabulary.red_flags):
            if term.code in context.target_pack:
                owner = context.target_pack[term.code]
                problems.append(f"{pack.name}: code {term.code} is also defined in pack {owner}")
                continue
            context.target_pack[term.code] = pack.name
        for source in pack.sources.sources:
            if source.id in context.source_pack:
                owner = context.source_pack[source.id]
                problems.append(f"{pack.name}: source {source.id} is also defined in pack {owner}")
                continue
            context.source_pack[source.id] = pack.name
    return context


def compare_problem(compare: Compare, definition: FieldDef) -> str | None:
    """Why a comparison does not fit the type of its field, or ``None``."""
    kind = definition.type
    value = compare.value
    if isinstance(value, RefBound):
        return (
            None
            if kind in ("number", "int")
            else f"reference thresholds need a numeric field, {compare.field} is {kind}"
        )
    if compare.op == "in":
        if kind not in ("int", "enum"):
            return f"op 'in' needs an int or enum field, {compare.field} is {kind}"
        problems = [definition.check_value(item) for item in value]  # type: ignore[union-attr]
        problems = [problem for problem in problems if problem]
        if kind == "enum" and problems:
            return f"{compare.field}: {problems[0]}"
        if kind == "int" and any(isinstance(item, bool) or not isinstance(item, int) for item in value):  # type: ignore[union-attr]
            return f"{compare.field}: op 'in' needs integers"
        return None
    if compare.op in ORDERED_OPS:
        if kind not in ("number", "int"):
            return f"op {compare.op!r} needs a numeric field, {compare.field} is {kind}"
        if isinstance(value, bool) or not isinstance(value, int | float):
            return f"{compare.field}: op {compare.op!r} needs a number"
        if kind == "int" and not isinstance(value, int):
            return f"{compare.field} is an int field, the threshold must be an integer"
        return None
    if kind == "bool" and not isinstance(value, bool):
        return f"{compare.field} is a bool field, compare with true or false"
    if kind == "enum":
        problem = definition.check_value(value)
        return f"{compare.field}: {problem}" if problem else None
    if kind in ("number", "int") and (isinstance(value, bool) or not isinstance(value, int | float)):
        return f"{compare.field}: expected a number"
    if kind == "int" and not isinstance(value, int):
        return f"{compare.field} is an int field, compare with an integer"
    return None


def _check_definitions(pack: Pack, context: _Context, problems: list[str]) -> None:
    for definition in pack.catalog.fields:
        if definition.bounds is not None and definition.bounds.source.ref not in context.sources:
            problems.append(
                f"{pack.name}: bounds of {definition.code} cite unknown source {definition.bounds.source.ref}"
            )
    _check_variant_lists(pack, context, problems)


def _check_variant_lists(pack: Pack, context: _Context, problems: list[str]) -> None:
    """Irrelevant facts (MR4) and contradiction templates (MR7) of a domain pack (KONZEPT 4.1)."""
    catalog = pack.catalog
    if pack.config.kind == "library" and (catalog.irrelevant or catalog.contradictions):
        problems.append(f"{pack.name}: only domain packs list irrelevant facts and contradictions")
    for fact in catalog.irrelevant:
        if fact.code in context.fields:
            owner = context.field_pack[fact.code]
            problems.append(f"{pack.name}: irrelevant fact {fact.code} is a field of pack {owner}; rules could use it")
    for template in catalog.contradictions:
        where = f"{pack.name}/{CATALOG_FILE} {template.id}"
        definition = context.fields.get(template.field)
        if definition is None:
            problems.append(f"{where}: unknown field {template.field}")
        else:
            for compare in comparisons(template.when):
                problem = compare_problem(compare, definition)
                if problem:
                    problems.append(f"{where}: {problem}")
        for source in template.sources:
            if source.ref not in context.sources:
                problems.append(f"{where}: source {source.ref} is not in the source register")


def _check_rule(pack: Pack, rule: Rule, context: _Context, problems: list[str]) -> None:
    where = f"{pack.name}/{RULES_DIR}/{pack.rule_files[rule.id]} {rule.id}"
    # The kind of a target follows from its prefix (rf. / ddx.), which the model enforces for rules and vocabulary.
    if rule.target not in context.targets:
        problems.append(f"{where}: target {rule.target} is not in the vocabulary")
    for compare in comparisons(rule.when):
        definition = context.fields.get(compare.field)
        if definition is None:
            problems.append(f"{where}: unknown field {compare.field}")
            continue
        problem = compare_problem(compare, definition)
        if problem:
            problems.append(f"{where}: {problem}")
    for source in rule.sources:
        if source.ref not in context.sources:
            problems.append(f"{where}: source {source.ref} is not in the source register")
    for index, test in enumerate(rule.tests):
        for code in sorted(test.facts):
            definition = context.fields.get(code)
            if definition is None:
                continue  # reported above, every test field is a condition field
            problem = definition.check_value(test.facts[code])
            if problem:
                problems.append(f"{where}: tests[{index}] {code}: {problem}")


def _check_migration(pack: Pack, problems: list[str]) -> None:
    where = f"{pack.name}/{MIGRATION_FILE}"
    rules = {rule.id: rule for rule in pack.rules}
    listed: dict[str, str] = {}
    for entry in pack.migration.entries if pack.migration else ():
        for rule_id in entry.rules:
            rule = rules.get(rule_id)
            if rule is None:
                problems.append(f"{where}: {entry.key} names rule {rule_id}, which is not in the pack")
            elif rule.migrated_from != entry.key:
                problems.append(f"{where}: {entry.key} names rule {rule_id}, migrated from {rule.migrated_from}")
            if rule_id in listed and listed[rule_id] != entry.key:
                problems.append(f"{where}: rule {rule_id} is listed under {listed[rule_id]} and {entry.key}")
            listed.setdefault(rule_id, entry.key)
    for rule in pack.rules:
        if rule.migrated_from is None:
            continue
        if pack.migration is None:
            problems.append(f"{pack.name}: rule {rule.id} is migrated from {rule.migrated_from}, no {MIGRATION_FILE}")
        elif rule.id not in listed:
            problems.append(f"{where}: rule {rule.id} (from {rule.migrated_from}) is missing in the table")


def _check_pack(pack: Pack, used: Iterable[Pack], problems: list[str]) -> _Context:
    context = _context((pack, *used), problems)
    _check_definitions(pack, context, problems)
    for rule in pack.rules:
        _check_rule(pack, rule, context, problems)
    _check_migration(pack, problems)
    return context


def run_rule_tests(pack: Pack) -> tuple[int, list[str]]:
    """Run every test vector of every rule of the pack; returns the number of vectors and the failures."""
    failures = []
    count = 0
    for rule in pack.rules:
        for index, test in enumerate(rule.tests):
            count += 1
            expected = Truth(test.expect if isinstance(test.expect, str) else str(test.expect).lower())
            try:
                actual = evaluate(rule.when, test.facts, test.refs)
            except (MissingReferenceError, TypeError) as exc:  # pragma: no cover - excluded by the model checks
                failures.append(f"{pack.name} {rule.id} tests[{index}]: {exc}")
                continue
            if actual is not expected:
                failures.append(f"{pack.name} {rule.id} tests[{index}]: expected {expected}, got {actual}")
    return count, failures


# --- Domains ---------------------------------------------------------------------------------------------------------


def _pack_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [path for path in sorted(root.iterdir()) if path.is_dir() and not path.name.startswith((".", "_"))]


def _used_packs(pack: Pack, root: Path, problems: list[str]) -> list[Pack]:
    used = []
    settings = pack.config.domain
    for name in settings.uses if settings else ():
        directory = root / name
        if not (directory / PACK_FILE).is_file():
            problems.append(f"{pack.name}: used pack {name!r} does not exist in {root}")
            continue
        try:
            other = read_pack(directory)
        except LoadError as exc:
            problems.extend(exc.problems)
            continue
        if other.config.kind != "library":
            problems.append(f"{pack.name}: used pack {name!r} is not a library pack")
            continue
        used.append(other)
    return used


def _active_rules(pack: Pack, settings: DomainSettings, used: list[Pack], problems: list[str]) -> list[Rule]:
    active = list(pack.rules)
    for other in used:
        choice = settings.activate[other.name]
        available = {rule.id: rule for rule in other.rules}
        if choice == "all":
            active.extend(other.rules)
            continue
        for rule_id in choice:
            if rule_id not in available:
                problems.append(f"{pack.name}: activated rule {rule_id} does not exist in pack {other.name}")
            else:
                active.append(available[rule_id])
    return sorted(active, key=lambda rule: rule.id)


def _build_domain(
    pack: Pack,
    settings: DomainSettings,
    used: list[Pack],
    context: _Context,
    problems: list[str],
    *,
    require_references: bool = True,
) -> Domain:
    active = _active_rules(pack, settings, used, problems)
    needed = set().union(*(fields_of(rule.when) for rule in active)) if active else set()
    own = set(pack.catalog.codes())
    fields = [*pack.catalog.fields, *(context.fields[code] for code in sorted(needed - own) if code in context.fields)]
    targets = {rule.target for rule in active}
    # Codes and ids defined twice were reported by _context; the first definition wins so the domain stays buildable.
    seen = {term.code for term in (*pack.vocabulary.ddx, *pack.vocabulary.red_flags)}
    ddx = [*pack.vocabulary.ddx]
    red_flags = [*pack.vocabulary.red_flags]
    for other in used:
        for terms, collected in ((other.vocabulary.ddx, ddx), (other.vocabulary.red_flags, red_flags)):
            for term in terms:
                if term.code in targets and term.code not in seen:
                    collected.append(term)
                    seen.add(term.code)
    sources = []
    source_ids: set[str] = set()
    for source in (*pack.sources.sources, *(source for other in used for source in other.sources.sources)):
        if source.id not in source_ids:
            sources.append(source)
            source_ids.add(source.id)
    catalog = Catalog(
        fields=tuple(fields), irrelevant=pack.catalog.irrelevant, contradictions=pack.catalog.contradictions
    )
    for template in catalog.contradictions:
        if template.field in context.fields and catalog.get(template.field) is None:
            problems.append(f"{pack.name}/{CATALOG_FILE} {template.id}: {template.field} is not a field of the domain")
        for code, side in sorted(reference_bounds_of(template.when)) if require_references else ():
            reference = pack.references.get(code)
            if reference is None or getattr(reference, side) is None:
                problems.append(
                    f"{pack.name}/{CATALOG_FILE} {template.id}: needs the {side} reference limit of {code}, "
                    "no profile has it"
                )
    for definition in catalog.fields:
        if definition.type in ("number", "int") and definition.bounds is None:
            problems.append(f"{pack.name}: numeric field {definition.code} has no physiological bounds (A-65)")
    for code, profile in sorted(pack.profiles.items()):
        definition = catalog.get(code)
        if definition is None:
            problems.append(f"{pack.name}/{PROFILES_DIR}: profile for {code}, which is not a field of the domain")
        elif definition.type not in ("number", "int"):
            problems.append(f"{pack.name}/{PROFILES_DIR}: profile for non-numeric field {code}")
        elif definition.unit != profile.unit:
            problems.append(
                f"{pack.name}/{PROFILES_DIR}: profile unit {profile.unit!r} of {code} differs from the catalog unit "
                f"{definition.unit!r}"
            )
    for rule in active if require_references else ():
        for code, side in sorted(reference_bounds_of(rule.when)):
            reference = pack.references.get(code)
            if reference is None or getattr(reference, side) is None:
                problems.append(
                    f"{pack.name}: rule {rule.id} needs the {side} reference limit of {code}, no profile has it"
                )
    return Domain(
        name=pack.name,
        case_prefix=settings.case_prefix,
        complaint=settings.complaint,
        complaint_labels=settings.complaint_labels,
        catalog=catalog,
        vocabulary=Vocabulary(ddx=tuple(ddx), red_flags=tuple(red_flags)),
        sources=SourceRegister(sources=tuple(sources)),
        rules=tuple(active),
        references=pack.references,
    )


def load_domain(name: str, root: Path = PACKS_ROOT, *, require_references: bool = True) -> Domain:
    """Load a domain pack with the library packs it uses and check everything it refers to.

    With ``require_references=False`` a missing reference limit is not an error. The profile builder needs this: it
    reads the catalog of a domain whose profiles it is about to write. Inference needs every reference limit.
    """
    directory = root / name
    if not (directory / PACK_FILE).is_file():
        available = ", ".join(path.name for path in _pack_dirs(root) if (path / PACK_FILE).is_file()) or "none"
        raise LoadError([f"no pack {name!r} in {root} (available: {available})"])
    pack = read_pack(directory)
    settings = pack.config.domain
    if settings is None:
        raise LoadError([f"pack {name!r} is a library pack, not a domain"])
    problems: list[str] = []
    used = _used_packs(pack, root, problems)
    if problems:
        raise LoadError(problems)
    for other in used:
        _check_pack(other, (), problems)
    context = _check_pack(pack, used, problems)
    domain = _build_domain(pack, settings, used, context, problems, require_references=require_references)
    if problems:
        raise LoadError(problems)
    return domain


def domains(root: Path = PACKS_ROOT) -> list[str]:
    """Names of all domain packs in ``root``."""
    names = []
    for directory in _pack_dirs(root):
        if not (directory / PACK_FILE).is_file():
            continue
        config = _read_model(PackConfig, directory / PACK_FILE, [])
        if config is not None and config.kind == "domain":
            names.append(directory.name)
    return names


def domain_for_complaint(complaint: str, root: Path = PACKS_ROOT) -> str | None:
    for name in domains(root):
        config = _read_model(PackConfig, root / name / PACK_FILE, [])
        if config is not None and config.domain is not None and config.domain.complaint == complaint:
            return name
    return None


# --- Full check ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PackSummary:
    name: str
    kind: str
    rules: int
    tests: int


@dataclass(frozen=True)
class DomainSummary:
    name: str
    active_rules: int
    fields: int
    references: int


@dataclass(frozen=True)
class CheckResult:
    root: Path
    packs: tuple[PackSummary, ...]
    domains: tuple[DomainSummary, ...]
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems and bool(self.packs)


def check(root: Path = PACKS_ROOT) -> CheckResult:
    """Check every pack in ``root``: files, references, unique ids, rule tests and every domain."""
    problems: list[str] = []
    packs: list[Pack] = []
    directories = _pack_dirs(root)
    if not directories:
        problems.append(f"no rule packs in {root}")
    for directory in directories:
        if not (directory / PACK_FILE).is_file():
            problems.append(f"{directory}: not a pack ({PACK_FILE} is missing)")
            continue
        try:
            packs.append(read_pack(directory))
        except LoadError as exc:
            problems.extend(exc.problems)
    rule_owner: dict[str, str] = {}
    source_owner: dict[str, str] = {}
    for pack in packs:
        for rule in pack.rules:
            if rule.id in rule_owner:
                problems.append(f"rule id {rule.id} is used in packs {rule_owner[rule.id]} and {pack.name}")
            rule_owner.setdefault(rule.id, pack.name)
        for source in pack.sources.sources:
            if source.id in source_owner:
                problems.append(f"source id {source.id} is used in packs {source_owner[source.id]} and {pack.name}")
            source_owner.setdefault(source.id, pack.name)
    summaries = []
    for pack in packs:
        if pack.config.kind == "library":
            _check_pack(pack, (), problems)
        count, failures = run_rule_tests(pack)
        problems.extend(failures)
        summaries.append(PackSummary(pack.name, pack.config.kind, len(pack.rules), count))
    domain_summaries = []
    for pack in packs:
        if pack.config.kind != "domain":
            continue
        try:
            domain = load_domain(pack.name, root)
        except LoadError as exc:
            problems.extend(exc.problems)
            continue
        domain_summaries.append(
            DomainSummary(domain.name, len(domain.rules), len(domain.catalog.fields), len(domain.references))
        )
    return CheckResult(root, tuple(summaries), tuple(domain_summaries), tuple(dict.fromkeys(problems)))
