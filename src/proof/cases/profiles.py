"""Lab profiles from the SynthEHR biochemistry CSV (PR-W01, D-03, A-56).

The builder only reads the CSV; it never runs or imports SynthEHR (PR-C02). For every numeric lab field of a domain
that names its SynthEHR test codes it writes one profile ``profiles/<name>.json``:

- Rows count when their test code belongs to the field, their unit is the expected one (case-insensitive), the result
  is a number and lies within the field's physiological bounds. Every discarded row is counted by reason.
- A censored result (comparator ``<`` or ``>``, e.g. ``<5``) enters with the reported limit, as in the prototype
  (``apply_comparator`` in ``01_prepare_labs.py``); such rows are counted (A-59).
- Laboratories report different reference ranges for the same test. The profile uses the range that most of the
  remaining rows carry; rows with another range are counted and left out, so values and range stay consistent.
- Values are averaged per patient over all samples (PR-W01) and rounded to the field's decimals, as a fact would be.
  The status of a patient follows the reference range: ``low`` below the lower limit, ``high`` above the upper limit,
  otherwise ``normal``.
- Per status the profile stores 21 quantiles (0 %, 5 %, ..., 100 %, linear interpolation) for the sampler.

The output is canonical JSON, so the same CSV and catalog always give the same bytes on every platform.
"""

from __future__ import annotations

import csv
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from proof.core import canonical
from proof.core.hashing import sha256_file
from proof_rules.model import Catalog, FieldDef

REQUIRED_COLUMNS = (
    "chi",
    "TestCode",
    "Result",
    "QuantityUnit",
    "ArithmeticComparator",
    "RangeLowValue",
    "RangeHighValue",
)
STATUSES = ("low", "normal", "high")
QUANTILE_STEPS = 20
PROBABILITIES = tuple(step / QUANTILE_STEPS for step in range(QUANTILE_STEPS + 1))
METHOD = (
    "Rows with the expected unit, a numeric result and a value within the physiological bounds; censored results "
    "(< or >) enter with the reported limit; reference range = the one most of these rows carry, rows with another "
    "range left out; mean per patient over all samples, rounded to the field's decimals; status against the "
    "reference range; quantiles by linear interpolation."
)
_EMPTY = {"", "NULL", "null", "NA", "N/A"}
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")
_INTEGER = re.compile(r"^[+-]?\d+$")

Number = int | float
Reference = tuple[Number | None, Number | None]


class ProfileError(Exception):
    """The CSV or the catalog does not allow building the profiles; ``problems`` lists every finding."""

    def __init__(self, problems: Iterable[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("\n".join(self.problems))


@dataclass(frozen=True)
class Provenance:
    """How the CSV was generated; written into every profile together with the CSV's hash."""

    generator: str
    command: str
    seed: int
    generated_on: date


@dataclass(frozen=True)
class _Spec:
    """What the builder needs from a profiled field."""

    code: str
    unit: str
    codes: tuple[str, ...]
    synthehr_unit: str
    lower: Number
    upper: Number | None
    bounds_source: str
    bounds_locator: str
    decimals: int


@dataclass
class _Rows:
    rows: int = 0
    other_unit: int = 0
    no_value: int = 0
    censored: int = 0
    outside_bounds: int = 0


def parse_number(text: str) -> Number | None:
    """Parse a CSV cell as a finite number; integers stay ``int``. Empty markers and anything else give ``None``."""
    text = text.strip()
    if text in _EMPTY or not _NUMBER.match(text):
        return None
    if _INTEGER.match(text):
        return int(text)
    value = float(text)
    return value if math.isfinite(value) else None


def round_to(value: float, decimals: int) -> Number:
    """Round as a fact is stored: ``decimals`` places, an ``int`` when there are none, never negative zero."""
    rounded = round(value, decimals)
    if decimals == 0:
        return int(rounded)
    return rounded + 0.0 if rounded == 0 else rounded


def quantiles(values: list[Number], decimals: int) -> list[Number]:
    """The 21 quantiles of sorted ``values`` (0 %, 5 %, ..., 100 %), interpolated linearly and rounded.

    Positions are computed with integers, so the result does not depend on floating-point division.
    """
    count = len(values)
    result = []
    for step in range(QUANTILE_STEPS + 1):
        index, remainder = divmod((count - 1) * step, QUANTILE_STEPS)
        value = float(values[index])
        if remainder:
            value += (values[index + 1] - values[index]) * remainder / QUANTILE_STEPS
        result.append(round_to(value, decimals))
    return result


def status_of(value: Number, reference: Reference) -> str:
    lower, upper = reference
    if lower is not None and value < lower:
        return "low"
    if upper is not None and value > upper:
        return "high"
    return "normal"


def _reference_key(reference: Reference) -> tuple[Any, ...]:
    lower, upper = reference
    return (lower is None, lower if lower is not None else 0, upper is None, upper if upper is not None else 0)


def _choose_reference(counts: Counter[Reference]) -> Reference | None:
    candidates = [(reference, count) for reference, count in counts.items() if reference != (None, None)]
    if not candidates:
        return None
    return min(candidates, key=lambda item: (-item[1], _reference_key(item[0])))[0]


def profile_name(code: str) -> str:
    """File name of a field's profile: the code without its section, e.g. ``crp_mg_l.json``."""
    return code.split(".", 1)[1] + ".json"


def profiled_fields(catalog: Catalog) -> list[FieldDef]:
    """The fields of a catalog that get a profile: numeric lab fields with a SynthEHR source."""
    return [field for field in catalog.fields if field.synthehr is not None]


def _spec(field: FieldDef) -> _Spec:
    if field.synthehr is None or field.unit is None:  # pragma: no cover - profiled_fields and the model exclude it
        raise ProfileError([f"{field.code}: not a numeric lab field with a SynthEHR source"])
    if field.bounds is None:
        raise ProfileError([f"{field.code}: no physiological bounds, rows cannot be checked (A-65)"])
    return _Spec(
        code=field.code,
        unit=field.unit,
        codes=field.synthehr.codes,
        synthehr_unit=field.synthehr.unit,
        lower=field.bounds.lower,
        upper=field.bounds.upper,
        bounds_source=field.bounds.source.ref,
        bounds_locator=field.bounds.source.locator,
        decimals=field.decimals or 0,
    )


def _read_rows(csv_path: Path, by_code: Mapping[str, _Spec]) -> tuple[int, dict[str, _Rows], dict[str, list]]:
    tallies = {spec.code: _Rows() for spec in by_code.values()}
    kept: dict[str, list[tuple[str, Number, Reference]]] = {spec.code: [] for spec in by_code.values()}
    total = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in REQUIRED_COLUMNS if column not in (reader.fieldnames or ())]
        if missing:
            raise ProfileError([f"{csv_path}: missing columns {', '.join(missing)}"])
        for row in reader:
            total += 1
            spec = by_code.get(row["TestCode"] or "")
            if spec is None:
                continue
            tally = tallies[spec.code]
            tally.rows += 1
            if (row["QuantityUnit"] or "").strip().lower() != spec.synthehr_unit.lower():
                tally.other_unit += 1
                continue
            value = parse_number(row["Result"] or "")
            if value is None:
                tally.no_value += 1
                continue
            if value < spec.lower or (spec.upper is not None and value > spec.upper):
                tally.outside_bounds += 1
                continue
            if (row["ArithmeticComparator"] or "").strip() not in _EMPTY:
                tally.censored += 1  # kept with the reported limit, see the module docstring
            reference = (parse_number(row["RangeLowValue"] or ""), parse_number(row["RangeHighValue"] or ""))
            kept[spec.code].append((row["chi"] or "", value, reference))
    return total, tallies, kept


def build_profiles(csv_path: Path, catalog: Catalog, provenance: Provenance) -> dict[str, dict[str, Any]]:
    """Build the profile of every profiled field of ``catalog`` from the CSV; keys are the fact codes."""
    specs = [_spec(field) for field in profiled_fields(catalog)]
    if not specs:
        raise ProfileError(["the catalog has no lab field with a SynthEHR source"])
    by_code: dict[str, _Spec] = {}
    problems = []
    for spec in specs:
        for code in spec.codes:
            if code in by_code:
                problems.append(f"SynthEHR code {code} belongs to {by_code[code].code} and {spec.code}")
            by_code[code] = spec
    if problems:
        raise ProfileError(problems)
    total, tallies, kept = _read_rows(csv_path, by_code)
    csv_sha256 = sha256_file(csv_path)
    profiles = {}
    for spec in specs:
        rows = kept[spec.code]
        reference = _choose_reference(Counter(reference for _, _, reference in rows))
        if reference is None:
            problems.append(f"{spec.code}: no usable row with a reference range in {csv_path.name}")
            continue
        profiles[spec.code] = _profile(spec, tallies[spec.code], rows, reference, provenance, csv_sha256, total)
    if problems:
        raise ProfileError(problems)
    return profiles


def _profile(
    spec: _Spec,
    tally: _Rows,
    rows: list[tuple[str, Number, Reference]],
    reference: Reference,
    provenance: Provenance,
    csv_sha256: str,
    csv_rows: int,
) -> dict[str, Any]:
    per_patient: dict[str, list[Number]] = defaultdict(list)
    other_reference = 0
    for patient, value, row_reference in rows:
        if row_reference != reference:
            other_reference += 1
            continue
        per_patient[patient].append(value)
    by_status: dict[str, list[Number]] = {status: [] for status in STATUSES}
    for values in per_patient.values():
        mean = round_to(math.fsum(values) / len(values), spec.decimals)
        by_status[status_of(mean, reference)].append(mean)
    lower, upper = reference
    return {
        "fact_code": spec.code,
        "unit": spec.unit,
        "reference": {key: value for key, value in (("lower", lower), ("upper", upper)) if value is not None},
        "bounds": {
            "lower": spec.lower,
            "upper": spec.upper,
            "source": spec.bounds_source,
            "locator": spec.bounds_locator,
        },
        "synthehr": {"codes": list(spec.codes), "unit": spec.synthehr_unit},
        "method": METHOD,
        "counts": {
            "rows": tally.rows,
            "rows_other_unit": tally.other_unit,
            "rows_no_value": tally.no_value,
            "rows_censored_kept": tally.censored,
            "rows_outside_bounds": tally.outside_bounds,
            "rows_other_reference": other_reference,
            "rows_used": len(rows) - other_reference,
            "patients": len(per_patient),
            "patients_by_status": {status: len(by_status[status]) for status in STATUSES},
        },
        "quantiles": {
            "probabilities": list(PROBABILITIES),
            **{
                status: quantiles(sorted(values), spec.decimals) if values else None
                for status, values in by_status.items()
            },
        },
        "provenance": {
            "generator": provenance.generator,
            "command": provenance.command,
            "seed": provenance.seed,
            "generated_on": provenance.generated_on.isoformat(),
            "csv_sha256": csv_sha256,
            "csv_rows": csv_rows,
        },
    }


def write_profiles(profiles: Mapping[str, dict[str, Any]], directory: Path) -> list[Path]:
    """Write each profile as canonical JSON with a final newline; returns the written paths in code order."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for code in sorted(profiles):
        path = directory / profile_name(code)
        path.write_bytes(canonical.dumps_bytes(profiles[code]) + b"\n")
        written.append(path)
    return written
