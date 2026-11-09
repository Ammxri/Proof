# Proof methodology

How Proof computes the expected answer (the *key*) of a case, where the rules come from, how cases are drawn and
rendered, how they are reviewed, and how the example case of the product requirements (PRD §5) comes out under the
shipped rules. The rules themselves are listed in [regeln.md](regeln.md), which is generated from the rule packs.

> zh: Proof 是评测工具和开放数据集，不是医疗器械，不用于患者诊疗。Proof 衡量的是与公开参考标准的一致性，而非临床真实情况。
> en: Proof is an evaluation tool and open dataset, not a medical device, and not intended for patient care. Proof
> measures agreement with a disclosed reference, not clinical truth.
> de: Proof ist ein Evaluationswerkzeug und offener Datensatz, kein Medizinprodukt und nicht für die
> Patientenversorgung bestimmt. Proof misst Übereinstimmung mit einer offengelegten Referenz, nicht klinische Wahrheit.

Every rule is a **draft, not reviewed by a physician**. Rules state criteria and thresholds in our own words and cite
their source with a locator; no text or table of a source is copied.

## 1 The key

A case is a set of coded facts (`vital.resp_rate: 24`, `hx.cough: true`, ...). Its key has four parts:

| Part | Meaning |
|---|---|
| `determinability` | `refer_urgent`, `ask` or `answer` |
| `red_flags` | red-flag codes whose rule is true |
| `ddx` | differential-diagnosis codes whose rule is true |
| `critical_fields` | facts whose removal alone changes the outcome |

No language model takes part in computing a key.

### 1.1 Three-valued logic

Each rule is a condition over facts: comparisons (`=`, `≠`, `<`, `≤`, `>`, `≥`, `in`) joined by `and`, `or`, `not` and
`at least k of`. A missing fact is *unknown*, and the connectives follow Kleene's three-valued logic. For example,
`at least 2 of` three criteria is true as soon as two are true, false as soon as two can no longer be reached, and
unknown otherwise. Thresholds of lab rules may point to the lower or upper limit of the lab's reference range.

### 1.2 Outcome and determinability

Rules with the same target are joined with *or*: a target is true if one of its rules is true. The outcome of a case is
the triple (determinability, true red flags, true diagnoses):

- `refer_urgent` if a red flag is true;
- otherwise `ask` if a red flag or a diagnosis is unknown, because a missing fact would decide it;
- otherwise `answer`.

A complete base case contains every fact the active rules need, so it never yields `ask`; `ask` arises only in
variants with missing facts.

### 1.3 Critical fields and required questions

A fact is **critical** if removing it alone changes the outcome (ablation, PRD §5). The order of the facts plays no
role. When a variant lacks facts of its base case, its **required questions** are the missing facts whose return alone
would change the variant's outcome.

## 2 Fever domain

### 2.1 Facts

Vital signs (temperature, heart rate, respiratory rate, systolic blood pressure, mental status), history (days since
onset, cough, shortness of breath, flank pain, headache), examination (new focal chest signs, costovertebral angle
tenderness, neck stiffness) and labs (CRP, creatinine, bilirubin, lactate, white blood cell count). Labels exist in
Chinese, English and German. Every numeric fact has physiological bounds with a source; values outside them are
invalid.

### 2.2 Rules and their sources

| Rule | Target | Criterion | Source |
|---|---|---|---|
| FEV-RF-001 | `rf.qsofa_ge2` | at least 2 of: respiratory rate ≥ 22/min, altered mental status, systolic pressure ≤ 100 mmHg | Sepsis-3 (Singer et al. 2016), Box 4; Seymour et al. 2016, Table 4 |
| FEV-DDX-001 | `ddx.sepsis` | temperature > 38.0 °C and qSOFA ≥ 2 | Sepsis-3, Box 1 and Box 4 |
| FEV-DDX-002 | `ddx.pneumonia` | cough and CRP > 100 mg/L | ERS/ESCMID guideline (Woodhead et al. 2011) |
| FEV-DDX-003 | `ddx.pneumonia` | cough and one of: new focal chest signs, shortness of breath, heart rate > 100/min, onset more than 4 days ago | ERS/ESCMID guideline (Woodhead et al. 2011) |
| FEV-DDX-004 | `ddx.pyelonephritis` | temperature ≥ 38.0 °C and flank pain or costovertebral angle tenderness | WHO AWaRe antibiotic book (2022), chapter 34 |
| FEV-DDX-005 | `ddx.bacterial_meningitis` | at least 2 of: headache, neck stiffness, altered mental status, temperature ≥ 38.0 °C | German meningitis guideline (Klein et al. 2023), recommendation 1; WHO AWaRe for the fever threshold |

Where a source names a criterion without a number or without saying how criteria combine, Proof fixes one reading
(decision A-60):

- **Sepsis:** Sepsis-3 applies qSOFA to patients with suspected infection. Proof reads a temperature above 38.0 °C (the
  temperature criterion in Sepsis-3, Box 1) as that suspicion.
- **Altered mental status** is the fact value `altered`; Sepsis-3 counts any Glasgow Coma Scale below 15.
- **Pneumonia:** the guideline lists "fever for more than 4 days"; in the fever domain the onset of symptoms counts as
  the onset of fever. Tachypnoea is listed without a threshold and is therefore not used.
- **Pyelonephritis:** fever of at least 38.0 °C together with flank pain or costovertebral angle tenderness.
- **Bacterial meningitis:** the guideline advises considering meningitis when the cardinal symptoms occur in
  combination; Proof reads "combination" as at least two of the four.
- There is no red flag for meningitis, because no checked source makes the combination itself an emergency criterion.
  The only red flag is qSOFA ≥ 2, as the PRD prescribes.

**Sources excluded by their terms.** As with NICE (decision D-04), sources whose terms forbid use with AI systems are
not used. Examples: the EAU guidelines and NEJM content. Sepsis-3 and the ERS/ESCMID guideline are read on PubMed
Central and cited for their criteria only (decision A-61).

**Known limit.** The Surviving Sepsis Campaign 2021 advises against qSOFA as the only screening tool. Proof keeps
qSOFA because the PRD prescribes it; the key therefore reflects qSOFA, not current screening practice.

### 2.3 Lab rules in the fever domain

The domain activates the migrated lab rules (section 3) whose facts all belong to its lab panel: CRP, creatinine,
bilirubin and lactate. Creatinine and bilirubin are the lab components of the SOFA score, and lactate is part of
the septic-shock criterion (Sepsis-3, Table 1 and Box 3) (decision A-64). The rule for rhabdomyolysis needs creatine
kinase and stays inactive.

## 3 Migrated lab rules

The fever prototype mapped lab abnormalities to German diagnosis texts (table `DDX_REGELN`, 73 keys, 70 with content).
Proof migrates them into the library pack `labs` (decision D-11):

- `_HOCH` means above the upper and `_NIEDRIG` below the lower limit of the reference range, as in the prototype.
- One rule per target. A text naming two conditions becomes two codes; the same condition from different texts
  gets the same code.
- A text becomes a rule only if a reference-work chapter supports it (StatPearls on the NCBI Bookshelf). Only the
  fact and its locator are cited. If the chapter supports a text only in part, only the supported part becomes a rule
  (decision A-62).
- The prototype's priority between keys and its limit of four texts are not taken over; every true rule counts.
- `GENERELL_HOCH` (a fallback without a lab condition) and the three empty keys are not migrated. `PSAT_HOCH` is not
  migrated either, because no checked chapter supports its only text. 68 of the 70 entries with content became 184
  rules.
- The prototype read SynthEHR's code `UR` as uric acid; in SynthEHR it is urea. Proof migrates it as urea.

The migration table (`labs/migration.yaml`, also in [regeln.md](regeln.md)) lists every key and every text, the rules
it became or the reason it became none.

## 4 Lab profiles

Lab values come from the synthetic SynthEHR biochemistry data (PRD §9). Proof never runs SynthEHR; it reads the CSV
once and writes one profile per lab fact of a domain (`proof labs build`). The method (decision A-59):

1. **Rows that count.** Rows count if they have the fact's SynthEHR test code (synonyms such as `CRE`/`CR` form one
   fact), the expected unit, a numeric result, and a value within the physiological bounds. Every discarded row is
   counted.
2. **Censored results.** A result such as `<5` enters with the reported limit, as in the prototype.
3. **Reference range.** Laboratories report different ranges. The profile uses the range most rows carry and leaves
   out rows with another range.
4. **Status per patient.** Values are averaged per patient over all samples and rounded to the fact's decimals. Each
   patient is then `low`, `normal` or `high` against the reference range.
5. **Profile contents.** Per status, 21 quantiles describe the distribution. Provenance (generator, command, seed,
   date, SHA-256 of the CSV) is stored in every profile.

## 5 Case sampler and collections

### 5.1 What a case is

A case has exactly the fields of the PRD example: `case_id`, `seed`, `patient` (`age`, `sex`), `complaint`, `facts`
and `key` (decision A-34). It holds codes and values only, no text (PR-K01). The JSON Schema is generated from the
Pydantic model: [`schema/case.schema.json`](../schema/case.schema.json). A base case contains every fact of its domain,
so it is never `ask` (decision A-07); `ask` arises only in variants with missing facts.

### 5.2 How the sampler reaches a target

Every case has a target: a diagnosis and whether a red flag is present (PR-K03). The sampler profile of the domain
(`packs/fever/sampler.yaml`) lists the targets in a plan; seed *s* gets entry (*s* − 1) mod length, so a case depends
on its seed only (decision A-66).

The sampler reaches the target through the rules themselves and adds no clinical knowledge of its own:

1. The rules of the target diagnosis must be true. For "present" one red-flag rule must be true, for "absent" every
   red-flag rule must be false.
2. These conditions are expanded into their alternatives. For example, qSOFA ≥ 2 becomes three alternatives: two of the
   three criteria are met, the third is free. One alternative that fits the sampling ranges is chosen at random.
3. Every fact is drawn from its background distribution (5.3), restricted to the values that alternative allows.
4. The rule set computes the key. If the key missed the target, the case would be relabeled, never corrected
   (PR-K04); the collection counts such cases.

Because the alternatives come from the rules, a case drawn this way always reaches its target. In Fever-100 no case is
relabeled.

The fever plan has seven entries: sepsis with red flag; pneumonia, acute pyelonephritis and bacterial meningitis each
with and without red flag. Sepsis without red flag cannot be drawn, because the sepsis rule needs qSOFA ≥ 2.

### 5.3 Background distributions

The background fills the facts the target leaves free. Its parameters are generation parameters, not an
epidemiological statement (decision A-35): how often a finding appears in the background says nothing about how often
it occurs in patients. Where a threshold splits a range into statuses, it has a source (decision A-67).

| Fact | Background | Thresholds and source | Sampling range |
|---|---|---|---|
| Yes/no findings, mental status | present (`altered`) in 1 of 10 | – | – |
| Temperature | low : normal : high = 1 : 3 : 6 | normal 36.0–38.0 °C (SIRS, Sepsis-3 Box 1) | 35.0–41.0 °C |
| Heart rate | normal : high = 2 : 1 | high above 90/min (SIRS, Sepsis-3 Box 1) | 50–140/min |
| Respiratory rate | normal : high = 3 : 1 | high above 20/min (SIRS, Sepsis-3 Box 1) | 10–36/min |
| Systolic pressure | low : normal = 1 : 4 | low at 100 mmHg or less (qSOFA, Sepsis-3 Box 4) | 70–180 mmHg |
| White cells | low : normal : high = 1 : 2 : 2 | normal 4.0–12.0 G/L (SIRS, Sepsis-3 Box 1) | 1.0–30.0 G/L |
| Days since onset | up to 4 : more = 3 : 1 | more than 4 days (ERS/ESCMID guideline) | 0–20 days |
| CRP | normal : high = 1 : 1 | reference range of the lab profile | SynthEHR quantiles |
| Creatinine | low : normal : high = 1 : 2 : 1 | reference range of the lab profile | SynthEHR quantiles |
| Bilirubin | normal : high = 2 : 1 | reference range of the lab profile | SynthEHR quantiles |
| Lactate | normal : high = 2 : 1 | reference range of the lab profile | SynthEHR quantiles |

- Within a status, vital signs and white cells are uniform on the grid of the fact.
- Lab values come from the SynthEHR profile of the status: the 21 quantiles split it into 20 parts of 5 % each, and a
  value is uniform within its part (PR-W01). A status is drawn only if it has at least 21 patients, as many as the
  profile stores quantiles; lactate "low" (9 patients) is therefore never drawn (risk RK-02).
- The SIRS criteria serve only as reference ranges for drawing values. Sepsis-3 does not use them to define sepsis, and
  Proof does not either.
- Age is uniform from 18 to 90 years, sex is female or male with equal weight (decision A-68). The fever sources address
  adults; Proof reads "adult" as 18 years and older. The upper limit is a generation parameter.
- All sampling ranges lie within the physiological bounds of the catalog.

All randomness comes from Proof's own random stream with one sub-stream per fact (decision A-06). The same seed gives
the same bytes on Windows and Linux; a test compares fixed hashes.

### 5.4 Collections

A collection is a directory with two files (decision A-69):

- `cases.jsonl`: one case per line in canonical JSON, ordered by seed;
- `collection.json`: versions, hashes of all inputs (schema, active rules, catalog, vocabulary, sources, sampler
  profile, lab profiles), seed range, plan, the hash and target of every case, the relabeled cases and the
  distribution.

```bash
uv run proof cases build --domain fever --n 100 --seed-start 1
uv run proof cases validate data/collections/fever-100
```

`validate` checks the schema, the canonical form, complete and valid facts, the key recomputed by the rule set, the
case drawn again from its seed, and the manifest against the cases and the current inputs.

**Fever-100** (`data/collections/fever-100/`, seeds 1–100):

| Measure | Value |
|---|---|
| Targets | 14 or 15 cases per plan entry, none relabeled |
| Determinability | `answer` 42, `refer_urgent` 58 |
| Red flag `rf.qsofa_ge2` | 58 cases |
| Fever diagnoses | bacterial meningitis 65, sepsis 50, acute pyelonephritis 37, pneumonia 31 |
| Diagnoses per case | 1 to 19, median 8 |
| Critical fields per case | 1 to 12, median 6; every case has at least one |
| Slowest key with ablation | about 10 ms per case (limit 1 s, PR-F04) |

Two properties of the rules shape these numbers:

- **Bacterial meningitis is frequent.** The rule needs two of four cardinal symptoms, and fever is one of them. In a
  fever case, any one of headache, neck stiffness or altered mental status is therefore enough. Altered mental status
  is also a qSOFA criterion, so many cases with a red flag have the diagnosis too.
- **Lab rules add many diagnoses.** A high CRP adds four diagnoses, a high bilirubin five, a high lactate three. Most
  cases therefore have several diagnoses.

Both follow from the draft rules (sections 2 and 3) and are open for the physician review.

### 5.5 Variants

A variant changes a base case in one defined way and carries what the answer must do (PRD §6, PR-M00). Its key is
recomputed by the rule set; its expectation is machine-readable (A-14):

| Relation | Change | Expectation |
|---|---|---|
| MR1 | one critical field of the base case is left out | absolute: the decision the rules give on the variant (`ask`, or `refer_urgent` if another red flag stays visible) and the removed field among the questions |
| MR3 | the four sections appear in another order | invariant: decision, diagnoses, red flags and questions as in the answer to the base case |
| MR5 | the base case in two languages (zh–en, zh–de, en–de) | invariant: the two answers to the base case agree |

- A variant does not depend on the language: it is rendered in zh, en and de with the same facts and order, so the
  three languages see identical items (decision A-74). MR5 needs no request of its own; it compares the answers to the
  base case (A-37).
- Which field MR1 removes and which order MR3 shows is drawn from a stream of the case's seed and the *variant seed*.
  The same variant seed gives the same variants; a new seed gives new ones, "new variants at the push of a button"
  (PR-D02, decision A-75). Several variants per relation and case draw without repetition.
- MR1 only removes fields that are critical in the base case; every case of Fever-100 has at least one.

A variant set lies in `<collection>/variants/<variant seed>/` with `variants.jsonl` and `variants.json` (decision
A-75). For Fever-100 and variant seed 1: 100 MR1, 100 MR3 and 300 MR5 variants; MR1 expects `ask` 57 times and
`refer_urgent` 43 times. Per language a model answers 300 units: 100 base cases, 100 MR1 and 100 MR3 variants.

```bash
uv run proof variants build --collection data/collections/fever-100 --variant-seed 1
uv run proof variants validate data/collections/fever-100/variants/1
uv run proof render data/collections/fever-100 --variants data/collections/fever-100/variants/1 \
  --variant-id FEV-000001-MR3-1 --lang de
```

`validate` checks every variant against its base case (change, facts, recomputed key, expectation) and rebuilds the
whole set from its seed.

## 6 Case text, system prompt and answer

### 6.1 Case text

A case is rendered in Chinese (simplified), English and German from one template per language (A-11, A-43). The
structure follows the long form of the fever prototype: a header with patient and complaint, then four numbered
sections, one line per fact:

```
Patientin, 48 Jahre
Vorstellungsgrund: Fieber

### 1. Anamnese
  • Tage seit Beginn: 0
  • Husten: nein
...
### 4. Labor
  • C-reaktives Protein (CRP): 52,4 mg/l (Referenzbereich 0–10 mg/l)
```

- The assessment, differential diagnoses and next steps of the prototype's long form are left out; they would be the
  solution. A test checks that no diagnosis, red-flag label or assessment word appears in any text.
- Numbers keep the decimals of the fact, with the decimal separator of the language. Units are shown in the usual form
  of each language, e.g. `次/分` and `×10⁹/L` in Chinese, `G/l` in German.
- Lab facts with a lab profile show its reference range, as a lab report does; the text gives no flag such as
  "elevated" (decision A-70). White cells have no lab profile and therefore no range.
- A section without facts says so ("keine Angaben"); this happens only in variants with missing facts.
- The order of the four sections is a parameter; the variants of MR3 (U6) permute it.
- Every rendering records where each fact appears. A test checks for all cases of Fever-100 in all three languages
  that each fact appears with its label and value, and that the three texts hold the same facts and numbers (PR-D01).

```bash
uv run proof render data/collections/fever-100 --case-id FEV-000001 --lang zh --system-prompt
```

### 6.2 System prompt

One fixed system prompt per language and domain (A-12). It states that the case is synthetic, asks for exactly one
JSON object with six keys, defines the three decisions with the words of PRD §5, and lists every allowed code with its
label: the diagnoses and red flags of the domain and the field codes for questions and contradictions. It names no
criterion or threshold of the rules. The case text is the user message. Proof uses no JSON mode of a provider (A-38).

### 6.3 Answer

An answer is valid only if the whole text, without whitespace at its edges, is one JSON object with exactly
`decision`, `ddx`, `questions`, `red_flags`, `contradictions` and `rationale`, and every list holds only codes the
domain allows (A-13). A Markdown code block, text around the object, a duplicate key or an unknown code make it
invalid; nothing is repaired. A code named twice is still an allowed code (decision A-73). The JSON Schema is in
[`schema/response.schema.json`](../schema/response.schema.json).

## 7 Physician review

Each language needs a physician review of its templates and of a sample of at least 10 % of the cases; for Chinese,
by a physician with clinical practice in China (PRD §10). A medical student may pre-review; that does not replace the
physician review.

- **Sample** (decision A-71): at least 10 % of a collection, rounded up, with at least one case per target of the plan.
  It is drawn from the collection's content hash and the language, so it is fixed for a collection and differs between
  languages.
- **Packet:** `proof review packet` writes a document in the reviewer's language with the system prompt, the hashes of
  the reviewed files and every sample case with its text and key, plus the template files, all labels and a record
  template.
- **Record** (`review/<lang>.yaml`, decision A-72): reviewer, role, practice and its country, date, scope, the hashes of
  the templates and labels reviewed, and the reviewed case ids. Missing details stay marked placeholders.
- **Check:** `proof review verify` accepts a record only if it has no placeholder, a physician (for zh with practice
  in China) reviewed exactly the current templates and labels, no date lies in the future and, for a collection,
  every sample case was reviewed. Any change to a template or label needs a new review (PR-A06).

The shipped records are placeholders until the reviews are delivered; `proof review verify` rejects them.

## 8 The PRD example, recalculated

PRD §5 shows case `FEV-000123` with facts temperature 39.2 °C, respiratory rate 24/min, systolic pressure 96 mmHg,
altered mental status, onset 2 days ago, cough, CRP 180 mg/L and white cells 15.2 G/L. Under the shipped rules
(`proof rules explain tests/fixtures/cases/prd_example.json`):

| Part | PRD §5 | Proof | Why |
|---|---|---|---|
| determinability | refer_urgent | refer_urgent | qSOFA is 3, so the red flag is true |
| red_flags | rf.qsofa_ge2 | rf.qsofa_ge2 | |
| critical_fields | sbp, resp_rate, mental_status | cough, CRP, mental status, temperature | see below |
| ddx | pneumonia, sepsis | pneumonia, sepsis, bacterial meningitis, bacterial infection, systemic inflammation, active inflammatory or autoimmune disease, tissue injury or trauma | see below |

**Critical fields.** With all three qSOFA criteria met, removing any one of them leaves qSOFA at 2, and sepsis stays
true. Respiratory rate and blood pressure are therefore not critical, exactly as PRD §5 defines ablation (decision
D-05). The PRD example lies at this edge. The variant with systolic pressure 120 mmHg (qSOFA 2) makes respiratory rate
and mental status critical. In Proof's example the critical facts are the ones that decide a diagnosis:

- cough decides pneumonia;
- CRP decides pneumonia and the CRP-based lab diagnoses;
- temperature decides sepsis and meningitis;
- mental status decides meningitis.

**Diagnoses.** Bacterial meningitis follows from fever plus altered mental status (two cardinal symptoms). The four
further diagnoses come from the migrated rule `CRP_HOCH`, whose supported texts all apply to a CRP above the reference
range. Facts the example does not contain (heart rate, creatinine, bilirubin, lactate and others) leave their rules
unknown. Because a red flag is true, the example still is `refer_urgent`.

A test (`tests/unit/test_packs.py`) recomputes this key on every run.

## 9 Limits

- Rules are drafts until a physician per language has reviewed them; the dataset card names the review.
- Keys reflect the cited sources and the readings above, not clinical truth.
- The lab distributions are synthetic (SynthEHR) and describe no real population.
- The sampler's background frequencies and sampling ranges are generation parameters, not epidemiological statements.
