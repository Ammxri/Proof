# Physician review records

One record per language: [`zh.yaml`](zh.yaml), [`en.yaml`](en.yaml), [`de.yaml`](de.yaml) (PRD §10, PR-A02, decision
A-23). Each lists who reviewed the templates and a sample of cases of that language, in which role and with which
result. Until a review is delivered, names, practice, country, date and scope are marked placeholders
(`<PLATZHALTER: …>`); `proof review verify` rejects such a record, and no release is possible without a valid one.

```bash
uv run proof review packet --lang zh --collection data/collections/fever-100
uv run proof review verify --lang zh --collection data/collections/fever-100
```

- The packet holds the system prompt, the sample cases with their keys, the template files, all labels and a record
  template with the current hashes and the sample.
- A physician must review each language; for zh with clinical practice in China. A pre-review by a medical student is
  entered with the role `pre_reviewer`; it is recorded but does not replace the physician review.
- A record covers exactly the templates and labels with the hashes it names. After any change to them, the language
  needs a new review (PR-A06).
