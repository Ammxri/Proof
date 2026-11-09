"""Case sampler (PR-F03, PR-K03, PR-K04): facts for a target diagnosis and red-flag status, reproducible from a seed.

The sampler profile of a domain (``packs/<domain>/sampler.yaml``) holds generation parameters, not epidemiological
statements (A-35):

- ``patient``: age range and sex weights;
- ``plan``: the target plan, a list of (target diagnosis, red-flag status); seed ``s`` gets entry
  ``(s - 1) mod length``, so a case depends on its seed only, never on the size of the collection (A-66);
- ``facts``: the background distribution of every fact of the domain (A-67).

How a case is drawn (A-66):

1. The target is reached through the rules. The rules of the target diagnosis must be true; for ``present`` one red-flag
   rule must be true, for ``absent`` every red-flag rule must be false. These conditions are expanded into terms
   (:mod:`proof.cases.constraints`), and one consistent term is chosen uniformly. The sampler adds no clinical knowledge
   of its own: whatever links facts to a diagnosis comes from a rule with a source.
2. Every fact is drawn from its background distribution, restricted to the values the chosen term allows.
3. The key is computed by the rule set. If it misses the target, the case is relabeled, never corrected (PR-K04): the
   key stays as computed and the collection counts the case.

All randomness comes from :class:`proof.core.rng.Stream`, with one sub-stream per fact, so the same seed gives the same
case on every platform (A-06).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, model_validator

from proof.cases import constraints, profiles
from proof.cases.constraints import Allowed, ConstraintError, Expander, Intervals, Term, units_of, value_of
from proof.cases.model import Case, Patient, Sex, case_id
from proof.core import yamlio
from proof.core.rng import Stream
from proof_rules import loader
from proof_rules.engine import Key
from proof_rules.keys import compute_key
from proof_rules.model import Domain, FieldCode, FieldDef, Number, SourceRef, TermCode, ValueCode

SAMPLER_FILE = "sampler.yaml"
STATUSES = profiles.STATUSES
# A status of a lab profile is drawn only if it has at least as many patients as the profile stores quantiles; with
# fewer patients neighbouring quantiles repeat values instead of describing the distribution (RK-02, A-67).
MIN_BUCKET_PATIENTS = len(profiles.PROBABILITIES)

Status = Literal["low", "normal", "high"]
RedFlagStatus = Literal["present", "absent"]
Weight = Annotated[StrictInt, Field(ge=0)]


class SamplerError(Exception):
    """The sampler profile is invalid or a target cannot be reached; ``problems`` lists every finding."""

    def __init__(self, problems: list[str] | tuple[str, ...]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


# --- Sampler profile -------------------------------------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _positive_total(weights: Mapping[Any, int], what: str) -> None:
    if sum(weights.values()) <= 0:
        raise ValueError(f"{what} need at least one positive weight")


class AgeSpec(_Model):
    """Age range in years, both ends inclusive; ``sources`` support the range's clinical limit (A-68)."""

    lower: Annotated[StrictInt, Field(ge=0)]
    upper: Annotated[StrictInt, Field(ge=0)]
    sources: Annotated[tuple[SourceRef, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _order(self) -> AgeSpec:
        if self.lower > self.upper:
            raise ValueError("lower must not exceed upper")
        return self


class PatientSpec(_Model):
    age: AgeSpec
    sex: dict[Sex, Weight]

    @model_validator(mode="after")
    def _weights(self) -> PatientSpec:
        _positive_total(self.sex, "sex weights")
        return self


class PlanEntry(_Model):
    """One target of the plan: a diagnosis code and whether a red flag is present."""

    ddx: TermCode
    red_flag: RedFlagStatus

    @model_validator(mode="after")
    def _ddx(self) -> PlanEntry:
        if not self.ddx.startswith("ddx."):
            raise ValueError("the target must be a ddx code")
        return self


class BoolBackground(_Model):
    """A yes/no fact is true with probability ``p_true[0] / p_true[1]``."""

    kind: Literal["bool"]
    p_true: tuple[Weight, Annotated[StrictInt, Field(ge=1)]]

    @model_validator(mode="after")
    def _fraction(self) -> BoolBackground:
        if self.p_true[0] > self.p_true[1]:
            raise ValueError("p_true must not exceed 1")
        return self


class EnumBackground(_Model):
    """An enum fact takes each value with probability proportional to its weight; unlisted values have weight 0."""

    kind: Literal["enum"]
    weights: dict[ValueCode, Weight]

    @model_validator(mode="after")
    def _weights(self) -> EnumBackground:
        _positive_total(self.weights, "enum weights")
        return self


class SampleRange(_Model):
    """Sampling limits of a numeric fact without lab profile, both inclusive (generation parameter, A-67)."""

    lower: Number
    upper: Number

    @model_validator(mode="after")
    def _order(self) -> SampleRange:
        if not self.lower < self.upper:
            raise ValueError("lower must be below upper")
        return self


class ReferenceSpec(_Model):
    """Own reference range of a fact without lab profile, with its source (D-03); one side may be open."""

    lower: Number | None = None
    upper: Number | None = None
    source: SourceRef

    @model_validator(mode="after")
    def _limits(self) -> ReferenceSpec:
        if self.lower is None and self.upper is None:
            raise ValueError("a reference range needs a lower or an upper limit")
        if self.lower is not None and self.upper is not None and not self.lower <= self.upper:
            raise ValueError("lower must not exceed upper")
        return self


class RangeBackground(_Model):
    """A numeric fact drawn uniformly within the band of a status; statuses follow the own reference range."""

    kind: Literal["range"]
    sample: SampleRange
    reference: ReferenceSpec | None = None
    status_weights: dict[Status, Weight] | None = None

    @model_validator(mode="after")
    def _weights(self) -> RangeBackground:
        if self.reference is not None and self.status_weights is None:
            raise ValueError("a fact with a reference range needs status_weights")
        if self.status_weights is not None:
            _positive_total(self.status_weights, "status weights")
        return self


class ProfileBackground(_Model):
    """A lab fact: the status is drawn by weight, the value from the SynthEHR quantiles of that status (PR-W01)."""

    kind: Literal["profile"]
    status_weights: dict[Status, Weight]

    @model_validator(mode="after")
    def _weights(self) -> ProfileBackground:
        _positive_total(self.status_weights, "status weights")
        return self


Background = Annotated[
    BoolBackground | EnumBackground | RangeBackground | ProfileBackground, Field(discriminator="kind")
]


class SamplerSpec(_Model):
    """``sampler.yaml`` of a domain pack."""

    patient: PatientSpec
    plan: Annotated[tuple[PlanEntry, ...], Field(min_length=1)]
    facts: dict[FieldCode, Background]


# --- Background distributions ----------------------------------------------------------------------------------------


class Discrete:
    """Weighted choice among the values of a bool or enum fact."""

    def __init__(self, values: tuple[Any, ...], weights: tuple[int, ...]) -> None:
        self.values = values
        self.weights = weights

    def has_mass(self, allowed: Allowed | None) -> bool:
        return any(w > 0 and (allowed is None or v in allowed) for v, w in zip(self.values, self.weights, strict=True))

    def draw(self, stream: Stream, allowed: Allowed | None) -> Any:
        weights = [w if allowed is None or v in allowed else 0 for v, w in zip(self.values, self.weights, strict=True)]
        return self.values[stream.weighted_index(weights)]


@dataclass(frozen=True)
class Segment:
    """Grid points ``low..high`` (inclusive) of one status that share ``weight`` uniformly."""

    status: str
    low: int
    high: int
    weight: int

    @property
    def size(self) -> int:
        return self.high - self.low + 1


class Numeric:
    """Piecewise uniform distribution over grid points: a segment is chosen by weight, then a point within it."""

    def __init__(self, field: FieldDef, segments: tuple[Segment, ...]) -> None:
        self.field = field
        self.segments = tuple(segment for segment in segments if segment.weight > 0)

    def _pieces(self, allowed: Allowed | None) -> list[tuple[Segment, int]]:
        if allowed is not None and not isinstance(allowed, Intervals):
            raise SamplerError([f"{self.field.code}: numeric fact with a non-numeric constraint"])  # pragma: no cover
        pieces = []
        for segment in self.segments:
            members = segment.size if allowed is None else allowed.count_in(segment.low, segment.high)
            if members:
                pieces.append((segment, members))
        return pieces

    def has_mass(self, allowed: Allowed | None) -> bool:
        return bool(self._pieces(allowed))

    def draw(self, stream: Stream, allowed: Allowed | None) -> int | float:
        pieces = self._pieces(allowed)
        if not pieces:
            raise SamplerError([f"{self.field.code}: no value of the background distribution is allowed"])
        common = math.lcm(*(segment.size for segment, _ in pieces))
        weights = [segment.weight * members * (common // segment.size) for segment, members in pieces]
        segment, members = pieces[stream.weighted_index(weights)]
        offset = stream.below(members)
        if allowed is None:
            units = segment.low + offset
        else:
            assert isinstance(allowed, Intervals)  # noqa: S101 - checked in _pieces
            units = allowed.nth_in(segment.low, segment.high, offset)
        return value_of(self.field, units)


Distribution = Discrete | Numeric


def _range_segments(field: FieldDef, background: RangeBackground) -> tuple[Segment, ...]:
    low = units_of(field, background.sample.lower)
    high = units_of(field, background.sample.upper)
    reference = background.reference
    weights = background.status_weights or {"normal": 1}
    if reference is None:
        return (Segment("normal", low, high, weights.get("normal", 0)),)
    ref_low = None if reference.lower is None else units_of(field, reference.lower)
    ref_high = None if reference.upper is None else units_of(field, reference.upper)
    bands = []
    if ref_low is not None:
        bands.append(("low", low, ref_low - 1))
    bands.append(("normal", low if ref_low is None else ref_low, high if ref_high is None else ref_high))
    if ref_high is not None:
        bands.append(("high", ref_high + 1, high))
    return tuple(Segment(status, first, last, weights.get(status, 0)) for status, first, last in bands)


def _profile_segments(field: FieldDef, profile: profiles.LabProfile, weights: Mapping[str, int]) -> tuple[Segment, ...]:
    segments = []
    for status in STATUSES:
        weight = weights.get(status, 0)
        values = profile.status_quantiles(status)
        if weight == 0 or values is None:
            continue
        points = [units_of(field, value) for value in values]
        last = len(points) - 2
        for index in range(len(points) - 1):
            first, following = points[index], points[index + 1]
            if index == last:
                segments.append(Segment(status, first, following, weight))
            elif following > first:
                segments.append(Segment(status, first, following - 1, weight))
            else:
                segments.append(Segment(status, first, first, weight))
    return tuple(segments)


# --- Loading and checking the profile --------------------------------------------------------------------------------


def _source_problem(ref: SourceRef, domain: Domain, where: str) -> str | None:
    if ref.ref not in domain.sources.ids():
        return f"{where}: source {ref.ref} is not in the source register of domain {domain.name}"
    return None


def _on_grid(field: FieldDef, value: Any, where: str, problems: list[str]) -> int | None:
    try:
        return units_of(field, value)
    except ConstraintError as exc:
        problems.append(f"{where}: {exc}")
        return None


def _check_range(field: FieldDef, background: RangeBackground, domain: Domain, where: str, problems: list[str]) -> None:
    before = len(problems)
    sample = background.sample
    for side in ("lower", "upper"):
        _on_grid(field, getattr(sample, side), f"{where}.sample.{side}", problems)
    bounds = field.bounds
    if bounds is not None and not (bounds.contains(sample.lower) and bounds.contains(sample.upper)):
        problems.append(f"{where}: sampling range lies outside the physiological bounds of {field.code}")
    reference = background.reference
    if reference is None:
        if background.status_weights is not None and set(background.status_weights) - {"normal"}:
            problems.append(f"{where}: without a reference range the only status is normal")
        return
    problem = _source_problem(reference.source, domain, f"{where}.reference")
    if problem:
        problems.append(problem)
    for side in ("lower", "upper"):
        value = getattr(reference, side)
        if value is not None:
            _on_grid(field, value, f"{where}.reference.{side}", problems)
    if len(problems) > before:
        return
    if reference.lower is not None and not sample.lower < reference.lower <= sample.upper:
        problems.append(f"{where}: the lower reference limit must lie above the lower sampling limit")
    if reference.upper is not None and not sample.lower <= reference.upper < sample.upper:
        problems.append(f"{where}: the upper reference limit must lie below the upper sampling limit")
    statuses = {"normal"}
    if reference.lower is not None:
        statuses.add("low")
    if reference.upper is not None:
        statuses.add("high")
    unknown = set(background.status_weights or {}) - statuses
    if unknown:
        problems.append(f"{where}: status_weights name statuses the reference range does not have: {sorted(unknown)}")


def _check_profile(
    field: FieldDef,
    background: ProfileBackground,
    profile: profiles.LabProfile,
    where: str,
    problems: list[str],
) -> None:
    # Fact code and unit of the profile are checked by the rule loader (A-56); the bounds are checked here.
    bounds = field.bounds
    if bounds is None or (
        profile.bounds.lower,
        profile.bounds.upper,
        profile.bounds.source,
        profile.bounds.locator,
    ) != (
        bounds.lower,
        bounds.upper,
        bounds.source.ref,
        bounds.source.locator,
    ):
        problems.append(f"{where}: the profile was built with other physiological bounds; rebuild the profiles")
    for status, weight in sorted(background.status_weights.items()):
        patients = profile.counts.patients_by_status[status]
        if weight > 0 and patients < MIN_BUCKET_PATIENTS:
            problems.append(
                f"{where}: status {status} has {patients} patients, fewer than {MIN_BUCKET_PATIENTS}; give it weight 0"
            )


def _check_spec(spec: SamplerSpec, domain: Domain, lab_profiles: Mapping[str, profiles.LabProfile]) -> list[str]:
    problems: list[str] = []
    for ref in spec.patient.age.sources:
        problem = _source_problem(ref, domain, "patient.age")
        if problem:
            problems.append(problem)
    codes = set(domain.catalog.codes())
    for code in sorted(codes - set(spec.facts)):
        problems.append(f"facts: {code} has no background distribution (base cases are complete, A-07)")
    for code in sorted(set(spec.facts) - codes):
        problems.append(f"facts: {code} is not a field of domain {domain.name}")
    for code in sorted(codes & set(spec.facts)):
        field = domain.catalog.get(code)
        assert field is not None  # noqa: S101 - code comes from the catalog
        background = spec.facts[code]
        where = f"facts.{code}"
        numeric = field.type in ("number", "int")
        expected = "profile" if field.synthehr is not None else ("range" if numeric else field.type)
        if background.kind != expected:
            problems.append(f"{where}: a {field.type} fact needs kind {expected!r}, not {background.kind!r}")
            continue
        if isinstance(background, ProfileBackground) and code not in lab_profiles:
            problems.append(f"{where}: no lab profile for {code}; build it with 'proof labs build'")
            continue
        if isinstance(background, EnumBackground):
            unknown = sorted(set(background.weights) - set(field.values))
            if unknown:
                problems.append(f"{where}: weights name values the field does not have: {unknown}")
        elif isinstance(background, RangeBackground):
            _check_range(field, background, domain, where, problems)
        elif isinstance(background, ProfileBackground):
            _check_profile(field, background, lab_profiles[code], where, problems)
    ddx_targets = {rule.target for rule in domain.rules if rule.kind == "ddx"}
    has_red_flags = any(rule.kind == "red_flag" for rule in domain.rules)
    for index, entry in enumerate(spec.plan):
        if entry.ddx not in ddx_targets:
            problems.append(f"plan[{index}]: {entry.ddx} is not the target of an active rule of domain {domain.name}")
        if entry.red_flag == "present" and not has_red_flags:
            problems.append(f"plan[{index}]: red flag present, but the domain has no red-flag rule")
    return problems


def read_spec(path: Path) -> SamplerSpec:
    """Read ``sampler.yaml``; YAML and model errors become :class:`SamplerError`."""
    if not path.is_file():
        raise SamplerError([f"{path}: file is missing"])
    try:
        data = yamlio.load_file(path)
    except yamlio.YamlError as exc:
        raise SamplerError([str(exc)]) from exc
    try:
        return SamplerSpec.model_validate(data)
    except ValidationError as exc:
        problems = []
        for error in exc.errors(include_url=False):
            location = ".".join(str(part) for part in error["loc"])
            message = error["msg"].removeprefix("Value error, ")
            problems.append(f"{path}: {location}: {message}" if location else f"{path}: {message}")
        raise SamplerError(problems) from exc


def read_lab_profiles(directory: Path) -> dict[str, profiles.LabProfile]:
    """All profiles of a domain pack, by fact code."""
    result: dict[str, profiles.LabProfile] = {}
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else ():
        try:
            profile = profiles.read_profile(path)
        except profiles.ProfileError as exc:
            raise SamplerError(exc.problems) from exc
        result[profile.fact_code] = profile
    return result


# --- Sampler ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """What the sampler aims at: a diagnosis and whether a red flag is present."""

    ddx: str
    red_flag: RedFlagStatus

    @property
    def label(self) -> str:
        return f"{self.ddx}/{self.red_flag}"

    def met_by(self, key: Key) -> bool:
        """True if the key contains the diagnosis and has a red flag exactly when one is targeted."""
        return self.ddx in key.ddx and bool(key.red_flags) == (self.red_flag == "present")


@dataclass(frozen=True)
class Sample:
    """A sampled case, the target it was drawn for and whether its key misses that target (relabeled, PR-K04)."""

    case: Case
    target: Target

    @property
    def relabeled(self) -> bool:
        return not self.target.met_by(self.case.key)


class Sampler:
    """Draws the base cases of one domain."""

    def __init__(self, domain: Domain, spec: SamplerSpec, lab_profiles: Mapping[str, profiles.LabProfile]) -> None:
        problems = _check_spec(spec, domain, lab_profiles)
        if problems:
            raise SamplerError(problems)
        self.domain = domain
        self.spec = spec
        self.lab_profiles = dict(lab_profiles)
        self._fields = {field.code: field for field in domain.catalog.fields}
        self._distributions = {code: self._distribution(code) for code in sorted(self._fields)}
        expander = Expander(self._fields, domain.references, support=self._supported)
        self._plan = tuple(Target(entry.ddx, entry.red_flag) for entry in spec.plan)
        self._terms: dict[Target, tuple[Term, ...]] = {}
        for index, target in enumerate(self._plan):
            if target in self._terms:
                continue
            try:
                terms = self._target_terms(target, expander)
            except ConstraintError as exc:
                raise SamplerError([f"plan[{index}] {target.label}: {exc}"]) from exc
            if not terms:
                problems.append(f"plan[{index}] {target.label}: no facts within the sampling ranges reach this target")
            self._terms[target] = terms
        if problems:
            raise SamplerError(problems)

    @property
    def plan(self) -> tuple[Target, ...]:
        return self._plan

    def _distribution(self, code: str) -> Distribution:
        field = self._fields[code]
        background = self.spec.facts[code]
        if isinstance(background, BoolBackground):
            numerator, denominator = background.p_true
            return Discrete((False, True), (denominator - numerator, numerator))
        if isinstance(background, EnumBackground):
            return Discrete(field.values, tuple(background.weights.get(value, 0) for value in field.values))
        if isinstance(background, RangeBackground):
            return Numeric(field, _range_segments(field, background))
        return Numeric(field, _profile_segments(field, self.lab_profiles[code], background.status_weights))

    def _supported(self, code: str, allowed: Allowed) -> bool:
        return self._distributions[code].has_mass(allowed)

    def _target_terms(self, target: Target, expander: Expander) -> tuple[Term, ...]:
        diagnosis: list[Term] = []
        for rule in self.domain.rules:
            if rule.kind == "ddx" and rule.target == target.ddx:
                diagnosis.extend(expander.expand(rule.when, True))
        red_flag_rules = [rule for rule in self.domain.rules if rule.kind == "red_flag"]
        if target.red_flag == "present":
            flags: list[Term] = []
            for rule in red_flag_rules:
                flags.extend(expander.expand(rule.when, True))
        else:
            flags = [constraints.EMPTY_TERM]
            for rule in red_flag_rules:
                flags = constraints.product(flags, expander.expand(rule.when, False))
        combined = constraints.product(diagnosis, flags)
        return tuple(term for term in combined if all(self._supported(code, term.get(code)) for code in term.fields()))

    def target(self, seed: int) -> Target:
        """The plan entry of a seed: ``(seed - 1) mod length``, so seeds 1..n walk through the plan in order."""
        return self._plan[(seed - 1) % len(self._plan)]

    def facts(self, seed: int) -> tuple[Target, dict[str, Any], Patient]:
        target = self.target(seed)
        stream = Stream("case", self.domain.name, seed)
        term = stream.child("term").choice(self._terms[target])
        facts = {
            code: self._distributions[code].draw(stream.child("fact", code), term.get(code)) for code in self._fields
        }
        age = self.spec.patient.age
        sexes = ("f", "m")
        sex_weights = [self.spec.patient.sex.get(sex, 0) for sex in sexes]
        patient = Patient(
            age=stream.child("patient", "age").integer(age.lower, age.upper),
            sex=sexes[stream.child("patient", "sex").weighted_index(sex_weights)],
        )
        return target, dict(sorted(facts.items())), patient

    def sample(self, seed: int) -> Sample:
        """The case of ``seed`` with its key computed by the rule set."""
        target, facts, patient = self.facts(seed)
        case = Case(
            case_id=case_id(self.domain.case_prefix, seed),
            seed=seed,
            patient=patient,
            complaint=self.domain.complaint,
            facts=facts,
            key=compute_key(self.domain, facts),
        )
        return Sample(case=case, target=target)


def load_sampler(name: str, root: Path = loader.PACKS_ROOT) -> Sampler:
    """The sampler of a domain pack: its domain, ``sampler.yaml`` and full lab profiles."""
    domain = loader.load_domain(name, root)
    directory = root / name
    spec = read_spec(directory / SAMPLER_FILE)
    return Sampler(domain, spec, read_lab_profiles(directory / loader.PROFILES_DIR))
