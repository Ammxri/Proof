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

## Licences

- Code: Apache License 2.0 ([`LICENSE`](LICENSE))
- Synthetic case collections and renderings: CC BY 4.0 ([`LICENSE-DATA`](LICENSE-DATA))

See [`NOTICE`](NOTICE).
