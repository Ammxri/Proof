# Proof methodology

How Proof computes the expected answer (the *key*) of a case, where the rules come from, and how the example case of
the product requirements (PRD §5) comes out under the shipped rules. The rules themselves are listed in
[regeln.md](regeln.md), which is generated from the rule packs.

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

## 5 The PRD example, recalculated

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

## 6 Limits

- Rules are drafts until a physician per language has reviewed them; the dataset card names the review.
- Keys reflect the cited sources and the readings above, not clinical truth.
- The lab distributions are synthetic (SynthEHR) and describe no real population.
