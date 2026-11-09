# Proof

Deterministic robustness test for clinical language models. Proof checks with synthetic cases in Chinese, English and
German whether a model notices missing information, recognises red flags and stays stable when order, noise or language
change. A rule set fixes the expected answers deterministically; no language model judges the answers.

> **zh:** Proof 是评测工具和开放数据集，不是医疗器械，不用于患者诊疗。Proof 衡量的是与公开参考标准的一致性，而非临床真实情况。
>
> **en:** Proof is an evaluation tool and open dataset, not a medical device, and not intended for patient care. Proof
> measures agreement with a disclosed reference, not clinical truth.
>
> **de:** Proof ist ein Evaluationswerkzeug und offener Datensatz, kein Medizinprodukt und nicht für die
> Patientenversorgung bestimmt. Proof misst Übereinstimmung mit einer offengelegten Referenz, nicht klinische Wahrheit.

## Status

Under development (version 0.1.0.dev0). The implementation plan and its progress are documented in German in
[`docs/umsetzung/`](docs/umsetzung/).

## Installation

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync --locked
uv run proof --help
```

## Configuration

Proof reads secrets only from environment variables. [`.env.example`](.env.example) lists them; Proof never writes them
to caches, manifests, logs or reports.

## Rules and method

- [`docs/methodik.md`](docs/methodik.md): how keys are computed, where the rules come from, the PRD example recalculated.
- [`docs/regeln.md`](docs/regeln.md): every rule with its source and locator, generated from the rule packs.

Every rule is a draft, not yet reviewed by a physician.

```bash
uv run proof rules check
uv run proof rules explain tests/fixtures/cases/prd_example.json
```

## Cases

Cases are sets of coded facts with a key computed by the rule set; the sampler draws them from a seed. The open
collection Fever-100 lies in [`data/collections/fever-100/`](data/collections/fever-100/), its JSON Schema in
[`schema/case.schema.json`](schema/case.schema.json). How cases are drawn: [`docs/methodik.md`](docs/methodik.md),
section 5; where the lab distributions come from: [`docs/daten/synthehr.md`](docs/daten/synthehr.md).

```bash
uv run proof cases build --domain fever --n 100 --seed-start 1
uv run proof cases validate data/collections/fever-100
```

Each case is rendered in Chinese, English and German; the system prompt names the answer format and every allowed
code ([`docs/methodik.md`](docs/methodik.md), section 6; answer schema in
[`schema/response.schema.json`](schema/response.schema.json)).

```bash
uv run proof render data/collections/fever-100 --case-id FEV-000001 --lang zh --system-prompt
```

Variants change a case in one defined way and carry their expectation (MR1, MR3, MR5 so far). A new variant seed gives
new variants ([`docs/methodik.md`](docs/methodik.md), section 5.5; schema in
[`schema/variant.schema.json`](schema/variant.schema.json)).

```bash
uv run proof variants build --collection data/collections/fever-100 --variant-seed 1
uv run proof variants validate data/collections/fever-100/variants/1
```

## Physician review

Each language needs a physician review of its templates and a sample of the cases (PRD §10). The records are in
[`review/`](review/); until a review is delivered they hold placeholders.

```bash
uv run proof review packet --lang zh --collection data/collections/fever-100
uv run proof review verify --lang zh --collection data/collections/fever-100
```

## Licences

- Code: Apache License 2.0 ([`LICENSE`](LICENSE))
- Synthetic case collections and renderings: CC BY 4.0 ([`LICENSE-DATA`](LICENSE-DATA))

See [`NOTICE`](NOTICE).
