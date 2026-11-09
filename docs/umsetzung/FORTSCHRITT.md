# Fortschritt – Proof

## Stand

**09.11.2026 – Phase 3, U6 abgeschlossen.**
- U1 bis U6 sind auf dem Zweig `dev` committet: Grundgerüst, Regelmotor, Fieber-Regelpaket mit Migration, Fallschema
  mit Sampler und Fever-100, Darstellung mit Prompt, Antwortschema und Prüfvermerken, Varianten MR1, MR3 und MR5.
- Das Repository ist `github.com/Ammxri/Proof` (D-07). Gepusht wird nur `dev`.
- Die CI ist für U5 unter Windows und Linux grün (Lauf 42574043812 auf `3407f79`); der Beleg für U6 folgt nach dem
  Push.

- **Grundregel D-01:** Proof ist ein eigenständiges Projekt. Kein anderes Projekt wird geändert, und es gibt keine
  Abhängigkeit zu NeuroGrid.
- **Plan:** U1–U14 aus [KONZEPT.md](KONZEPT.md); v0.1 = U1–U9, v0.5 = U10–U12, v1.0 = U13–U14; GO-1 vor U13.

**Nächster Schritt:** U7 (Testlauf: Anbieter-YAML, Client, Zwischenspeicher, EU-Sperre, Manifest, Qwen-Probelauf). Vor
dem Probelauf prüfe ich, dass kein NeuroGrid-Lauf rechnet (A-30).

## Verlauf

### 09.11.2026 – U6 Varianten MR1, MR3, MR5
**Neue Auslegungen:** A-74 bis A-76 (sprachunabhängige Varianten, Variantensätze und Varianten-Seed, MR1).

**Umgesetzt:**
- **Variantenmodell** (`src/proof/variants/model.py`): genau die Felder aus KONZEPT 4.7, Erwartung `absolute` oder
  `invariant` (A-14); JSON Schema `schema/variant.schema.json`.
- **Relationen** (`src/proof/variants/generator.py`):
  - MR1 entfernt ein kritisches Feld; der Schlüssel wird neu berechnet. Die Erwartung ist die Entscheidung des Motors
    auf den Variantenfakten und das Feld unter den Fragen (A-76).
  - MR3 zeigt die vier Abschnitte in einer der 23 anderen Reihenfolgen; Fakten und Schlüssel bleiben.
  - MR5 legt je Basisfall die drei Sprachpaare an; verglichen werden die Antworten auf den Basisfall (A-37, A-74).
  - Feld und Reihenfolge kommen aus dem Varianten-Seed; mehrere Varianten je Fall ziehen ohne Wiederholung (A-75).
- **Variantensätze** (`src/proof/variants/sets.py`): `<sammlung>/variants/<seed>/` mit `variants.jsonl` und
  `variants.json`. Die Prüfung vergleicht jede Variante mit ihrem Basisfall und baut den Satz aus dem Seed neu.
- **Befehle:** `proof variants build --collection … --variant-seed …` und `proof variants validate …`;
  `proof render … --variants … --variant-id …` zeigt eine Variante.
- **Satz zu Fever-100**, Varianten-Seed 1 (`data/collections/fever-100/variants/1/`), gebaut aus Commit `19af369`
  (sauberer Arbeitsbaum):

  | Merkmal | Wert |
  |---|---|
  | Varianten | MR1 100, MR3 100, MR5 300 |
  | MR1, erwartete Entscheidung | `ask` 57, `refer_urgent` 43 |
  | MR1, häufigste entfernte Felder | Bewusstsein 20, Temperatur 16, Kreatinin 12 |
  | Einheiten je Sprache | 300 (100 Basisfälle, 100 MR1, 100 MR3) |

- **Doku:** `docs/methodik.md` Abschnitt 5.5, README, Matrix.

**Geprüft** (lokal, Windows 11, Python 3.12.15):
- `uv run pytest --cov`: 710 Tests grün, Abdeckung 99,18 % (5:20 min).
- `ruff check` und `ruff format --check`: sauber; Schemata aktuell.
- `proof variants validate data/collections/fever-100/variants/1`: 500 Varianten gültig.
- Wheel frisch installiert: `proof variants build` (Seed 4) und `validate` laufen damit.

**Nicht lokal ausgeführt:** `pip-audit`; die Prüfung läuft in der CI. Keine neue Abhängigkeit.

**Abnahme U6 (DoD aus KONZEPT.md):** erfüllt, der CI-Beleg folgt.
- Jede Variante besteht das Schema und trägt ihre Erwartung
  (`test_every_variant_passes_the_schema_and_carries_its_expectation`, `test_variant_model.py`).
- MR1-Erwartung gleich dem Motor auf den Variantenfakten (`ask`, außer bei anderem sichtbarem Warnzeichen), das Feld
  steht in den Fragen (`test_mr1_expects_what_the_engine_gives_on_the_variant`).
- MR3 ändert nur die Reihenfolge (`test_mr3_changes_only_the_order`).
- Gleicher Varianten-Seed, gleiche Varianten; neuer Seed, neue Varianten
  (`test_same_seed_same_variants_new_seed_new_variants`).

### 09.11.2026 – U5 Darstellung, Prompt, Antwortschema, Prüfvermerke
**Neue Auslegungen:** A-70 bis A-73 (Falltext, Stichprobe, Prüfvermerk, Antwortprüfung).

**Umgesetzt:**
- **Vorlagen** (`src/proof/render/templates/{zh,en,de}/`): je Sprache Falltext, Systemprompt und Sprachtabelle,
  gerendert in der Jinja2-Sandbox mit `StrictUndefined` (KONZEPT §7).
- **Falltext** (`src/proof/render/case_text.py`, A-70):
  - Aufbau der Langform des Prototyps: Kopfzeile mit Patient und Vorstellungsgrund, dann Anamnese, Befund,
    Vitalwerte, Labor; Einschätzung, DDx und nächste Schritte entfallen.
  - Zahlen mit den Nachkommastellen des Fakts und dem Dezimaltrennzeichen der Sprache, Einheiten in der üblichen Form
    der Sprache; Laborfakten mit Laborprofil zeigen ihren Referenzbereich, aber kein Statuszeichen.
  - Jede Darstellung hält fest, wo jeder Fakt steht. Die Reihenfolge der Abschnitte ist ein Parameter für MR3.
  - Die Beschwerde hat Bezeichnungen je Sprache im Domänenpaket (`complaint_labels`).
- **Systemprompt** (`src/proof/render/prompt.py`, A-12): synthetischer Fall, genau ein JSON-Objekt mit sechs
  Schlüsseln, die drei Entscheidungen mit den Worten aus PRD §5, alle erlaubten Codes mit Bezeichnung; keine Schwelle
  einer Regel.
- **Antwortschema** (`src/proof/scoring/response.py`): Modell `Response`, JSON Schema `schema/response.schema.json`,
  strenge Prüfung ohne Reparatur (A-13, A-73).
- **Ärztliche Prüfung** (`src/proof/cases/review.py`):
  - Stichprobe: mindestens 10 %, ein Fall je Ziel, deterministisch je Sammlung und Sprache (A-71). Für Fever-100 sind
    es je Sprache 10 Fälle, die alle sieben Ziele abdecken.
  - Prüfpaket in der Sprache des Prüfers: Systemprompt, Hashes, Stichprobe mit Text und Schlüssel, Vorlagendateien,
    Bezeichnungen und eine Vermerkvorlage.
  - Prüfvermerk `review/<sprache>.yaml` (A-72) und Prüfung `proof review verify`.
  - `review/zh.yaml`, `en.yaml`, `de.yaml` liegen als Platzhalter mit den aktuellen Hashes und der Stichprobe bereit.
- **Befehle:** `proof render <fall> --lang …` (mit `--system-prompt`), `proof review sample | packet | verify`.
- **Doku:** `docs/methodik.md` Abschnitte 6 und 7, `review/README.md`, README.
- **Abhängigkeit:** Jinja2 3.1.6 (BSD-3, KONZEPT §2) mit MarkupSafe 3.0.4 (BSD-3).

**Beispiel** (`FEV-000001`, Auszug):
- de: `Körpertemperatur (T): 40,4 °C`, `C-reaktives Protein (CRP): 52,4 mg/l (Referenzbereich 0–10 mg/l)`
- en: `Body temperature (T): 40.4 °C`, `White blood cell count (WBC): 9.1 ×10⁹/L`
- zh: `体温：40.4℃`, `心率（HR）：101次/分`, `C反应蛋白（CRP）：52.4 mg/L（参考范围：0–10 mg/L）`

**Geprüft** (lokal, Windows 11, Python 3.12.15):
- `uv run pytest --cov`: 662 Tests grün, Abdeckung 99,30 % (5:11 min). Danach kam ein Test für einseitige
  Referenzbereiche hinzu, einzeln grün; die ganze Suite mit 663 Tests läuft in der CI.
- `ruff check` und `ruff format --check`: sauber.
- Schemata und `docs/regeln.md` aktuell (`--check`).
- Lizenzprüfung: 55 Pakete, 0 abgebrochen, 0 gemeldet.
- Wheel neu gebaut und frisch installiert: Es enthält alle Vorlagen; `proof render` läuft damit.
- `proof review verify` weist die ausgelieferten Vermerke wegen der Platzhalter ab, wie vorgesehen.

**Nicht lokal ausgeführt:** `pip-audit`; die Prüfung läuft in der CI.

**CI:** Lauf 42574043812 (ci #8) auf `3407f79`, beide Jobs erfolgreich: `test (ubuntu-latest)` in 49 s,
`test (windows-latest)` in 2:01 min. Alle Schritte grün: Lint, Tests mit Abdeckung, Lizenzprüfung, `pip-audit`, Wheel
in frischer Umgebung. Gelesen wurde der Status je Schritt; die Protokolle zeigt GitHub nur angemeldet.

**Offen (manuell, bei dir):**
- Ärztliche Prüfung je Sprache, für zh mit Klinikpraxis in China. Das Prüfpaket erzeugt
  `proof review packet --lang <sprache> --collection data/collections/fever-100`.
- Die zh-Texte (Vorlagen und Bezeichnungen) stammen von mir; ihre Natürlichkeit prüft die zh-Prüfung (RK-10).

**Abnahme U5 (DoD aus KONZEPT.md):** erfüllt.
- Jeder Fall von Fever-100 wird in zh, en und de dargestellt, jeder Fakt hat seine Textstelle
  (`test_every_fact_of_every_case_appears_in_every_language`).
- Kein Diagnose-, Warnzeichen- oder Einschätzungstext im Fall (`test_texts_hold_no_assessment_diagnosis_or_red_flag`).
- Der Prompt nennt alle erlaubten Codes (`test_the_prompt_names_every_allowed_code_and_the_format`).
- `review verify` weist fehlenden Vermerk, Platzhalter, reine Vorprüfung und abweichende Hashes ab
  (`test_a_missing_record_is_rejected`, `test_shipped_records_are_placeholders_with_current_hashes`,
  `test_a_pre_review_alone_is_rejected`, `test_changed_templates_invalidate_the_review`).
- Stichprobe deterministisch und mindestens 10 % (`test_sample_size_is_at_least_ten_percent`,
  `test_the_sample_is_deterministic_and_covers_every_target`).

### 09.11.2026 – U4 Fallschema, Sampler, Fever-100
**Neue Auslegungen:** A-66 bis A-69 (Sampler über die Regeln, Hintergrundverteilungen, Patient, Sammlungen).

**Umgesetzt:**
- **Fallschema** (`src/proof/cases/model.py`): `Case` mit genau den PRD-Feldern (A-34). Das JSON Schema
  `schema/case.schema.json` wird mit `tools/export_schemas.py` aus dem Modell erzeugt; ein Test prüft, dass es aktuell
  ist. Der Schlüssel nimmt jetzt nur `ddx.*` unter `ddx` und nur `rf.*` unter `red_flags` an.
- **Sampler** (`src/proof/cases/sampler.py`, `constraints.py`):
  - Ziel eines Falls: Diagnose und Warnzeichen-Status aus dem Zielplan; Seed *s* bekommt Eintrag (*s* − 1) mod Länge.
  - Das Ziel wird über die Regeln erreicht: Ihre Bedingungen werden in Alternativen zerlegt, eine passende wird
    gezogen (A-66). Ein Test prüft für jede Regel und jede Alternative, dass sie die Regel wirklich entscheidet.
  - Die übrigen Fakten kommen aus Hintergrundverteilungen (A-67). Laborwerte stammen aus den SynthEHR-Quantilen,
    Vitalwerte und Leukozyten aus eigenen Bereichen mit Quelle (SIRS und qSOFA, Sepsis-3).
  - Sampler-Profil der Fieberdomäne: `packs/fever/sampler.yaml`; Alter 18–90 Jahre (A-68).
  - Der Lader prüft das Profil vollständig: jedes Feld, Typ, Raster, physiologische Grenzen, Quellen, dünne Status und
    erreichbare Ziele.
- **Laborprofile:** volles Format `LabProfile` mit Prüfung auf innere Stimmigkeit (Zählwerte, Quantile, Status).
- **Sammlungen** (`src/proof/cases/collection.py`, A-69):
  - `proof cases build --domain fever --n 100 --seed-start 1` schreibt `cases.jsonl` und `collection.json`.
  - `proof cases validate <pfad>` prüft Schema, kanonische Form, Fakten, neu berechnete Schlüssel, Neuziehung aus dem
    Seed und das Manifest gegen Fälle und Eingaben.
- **Fever-100:** `data/collections/fever-100/`, gebaut aus Commit `3bc3f33` (sauberer Arbeitsbaum).
- **Repository-Prüfung (PR-C02):** kein Programm, keine Bibliothek, kein Quelltext von SynthEHR; Proof startet außer
  git kein Programm.
- **Doku:** `docs/methodik.md` Abschnitt 5 (Sampler, Hintergrund, Sammlungen), `docs/daten/synthehr.md` (SynthEHR-Lauf
  und Weg zu den Profilen), README.
- **Entwicklungsabhängigkeit:** `jsonschema` 4.26.0 (MIT, KONZEPT §2) mit `attrs`, `referencing`, `rpds-py` und
  `jsonschema-specifications` (alle MIT).

**Haltepunkt nach U4 (KONZEPT §11):**
- **Neubeschriftungen:** 0 von 100. Der Sampler erreicht jedes Ziel über die Regeln.
- **Status-Töpfe (RK-02):** Alle Töpfe, die der Sampler zieht, haben mindestens 21 Patienten (CRP 294/514,
  Kreatinin 243/366/892, Bilirubin 902/561, Laktat 31/59). Laktat „niedrig“ hat 9 Patienten und wird nicht gezogen; keine
  aktive Regel braucht ihn. CRP und Bilirubin haben keinen Topf „niedrig“, weil ihre untere Referenzgrenze 0 ist. Ein
  eigener Ersatzbereich war deshalb nicht nötig.
- **Verteilung Fever-100:**

  | Merkmal | Wert |
  |---|---|
  | Ziele | je Planeintrag 14 oder 15 Fälle |
  | Entscheidbarkeit | `answer` 42, `refer_urgent` 58 (Basisfälle sind nie `ask`, A-33) |
  | Warnzeichen `rf.qsofa_ge2` | 58 Fälle |
  | Fieberdiagnosen | bakterielle Meningitis 65, Sepsis 50, akute Pyelonephritis 37, Pneumonie 31 |
  | Labordiagnosen | CRP-Diagnosen je 54, Laktat-Diagnosen je 44, Bilirubin-Diagnosen je 33, Kreatinin-Diagnosen je 25, `ddx.sepsis_aki` 13 |
  | Diagnosen je Fall | 1 bis 19, Median 8 |
  | Kritische Felder je Fall | 1 bis 12, Median 6; jeder Fall hat mindestens eines (Material für MR1) |
  | Patienten | 47 `f`, 53 `m`, Alter 20 bis 90 |

- **Befunde für die ärztliche Prüfung:**
  - Die Meningitis-Regel (2 von 4 Kardinalsymptomen, A-60) greift in einem Fieberfall schon bei Kopfschmerz,
    Nackensteifigkeit oder verändertem Bewusstsein. Verändertes Bewusstsein ist zugleich qSOFA-Kriterium. Deshalb
    tragen 65 von 100 Fällen `ddx.bacterial_meningitis`.
  - Die migrierten Laborregeln der Fieberdomäne (A-64) fügen je erhöhtem Wert drei bis fünf Diagnosen hinzu, z. B.
    `ddx.gilbert_syndrome` bei erhöhtem Bilirubin oder `ddx.metformin_lactic_acidosis` bei erhöhtem Laktat.
  - Beides folgt aus den Entwurfsregeln, nicht aus dem Sampler. Ändern lässt es sich nur über die Regeln
    (Meningitis-Lesart, Auswahl der Laborregeln in `packs/fever/pack.yaml`).

**Geprüft** (lokal, Windows 11, Python 3.12.15):
- `uv run pytest --cov`: 584 Tests grün, Abdeckung 99,87 % (4:25 min).
- `ruff check` und `ruff format --check`: sauber.
- `proof cases validate data/collections/fever-100`: 100 Fälle gültig, 0 neu beschriftet.
- Schlüssel mit Ablation: langsamster Fall etwa 10 bis 25 ms (Grenze 1 s, PR-F04); der Test misst über alle 100 Fälle.
- Lizenzprüfung: 53 Pakete, 0 abgebrochen, 0 gemeldet.
- Wheel neu gebaut und in eine frische Umgebung installiert. Es enthält die neuen Module und `sampler.yaml`;
  `proof cases build` und `validate` laufen damit.

**Nicht lokal ausgeführt:** `pip-audit`; die Prüfung läuft in der CI.

**CI:** Lauf 42569793312 (ci #6) auf `90aaa3c`, beide Jobs erfolgreich: `test (ubuntu-latest)` in 58 s,
`test (windows-latest)` in 1:47 min. Alle Schritte grün: Lint, Tests mit Abdeckung, Lizenzprüfung, `pip-audit`, Wheel
in frischer Umgebung. Die Golden-Hashes und der bytegleiche Neubau von Fever-100 gelten damit unter beiden Systemen.
Die Protokolle der Schritte zeigt GitHub nur angemeldet; gelesen wurde der Status je Schritt.

**Abnahme U4 (DoD aus KONZEPT.md):** erfüllt.
- Alle Fever-100-Fälle bestehen Pydantic und JSON Schema (`test_fever_100_is_valid`,
  `test_fever_100_passes_the_json_schema`).
- Gleicher Seed, bytegleicher Fall: Golden-Hashes (`test_golden_case_hashes`) und bytegleicher Neubau von Fever-100
  (`test_fever_100_is_rebuilt_byte_for_byte`); in der CI unter Windows und Linux.
- Schlüssel mit Ablation unter 1 s je Fall, Maximum über die Sammlung
  (`test_key_with_ablation_takes_less_than_one_second_per_case`).
- Neubeschriftungen gezählt (`collection.json`, `test_relabeled_cases_are_counted`).
- Profile mit Herkunft und Zählwerten (`LabProfile`, `test_built_and_shipped_profiles_follow_the_full_format`).
- Kein SynthEHR-Code oder -Programm im Repository (`test_no_synthehr_program_or_code_in_the_repository`).
- Verteilung von Entscheidbarkeit, Warnzeichen und Diagnosen: oben.

### 09.11.2026 – U3 Fieber-Regelpaket und Migration
**Entscheidung:** B10 entschieden als D-11 („A: Nachschlagewerke“). Neue Auslegungen A-59 bis A-65.

**Umgesetzt:**
- **Profilbau** (aus U4 vorgezogen, A-56): `proof labs build --csv …` in `src/proof/cases/profiles.py`.
  - Liest nur die CSV und startet SynthEHR nicht.
  - Je Laborfeld einer Domäne entsteht ein Profil mit Referenzbereich, Zählwerten je Verwerfungsgrund, 21 Quantilen je
    Status und Herkunft (A-59).
  - Zensierte Werte (`<5`) gehen wie im Prototyp mit dem gemeldeten Grenzwert ein. Ohne sie lagen nur 19 von 536
    CRP-Patienten im Normalbereich.
- **Modell und Lader:**
  - Laborfelder nennen ihre SynthEHR-Codes (`synthehr`).
  - Grenzen dürfen nach oben offen sein. Jeder Fakt einer Domäne braucht Grenzen mit Quelle (A-65).
  - Neu ist die Migrationstabelle (`migration.yaml`). Der Lader prüft sie in beiden Richtungen gegen `migrated_from`.
- **Paket `fever`** (Domäne):
  - 14 eigene Fakten mit Bezeichnungen in zh, en und de.
  - Sechs Regeln: qSOFA ≥ 2, Sepsis, Pneumonie (zwei Regeln), akute Pyelonephritis, bakterielle Meningitis.
  - Sechs Quellen: Sepsis-3, Seymour 2016, ERS/ESCMID 2011, WHO AWaRe 2022, deutsche Meningitis-Leitlinie 2023,
    Wright 2024. Ihre Bedingungen sind geprüft und eingetragen (A-60, A-61).
  - Vier Profile: CRP, Kreatinin, Bilirubin, Laktat.
- **Paket `labs`** (Bibliothek): 184 migrierte Regeln mit 106 Diagnosecodes, 33 Laborfeldern und 54
  StatPearls-Kapiteln. Dazu kommt das MIMIC Code Repository für die Grenzen.
- **Migrationstabelle:**
  - Sie enthält alle 73 Schlüssel. 68 von 70 Einträgen mit Inhalt sind migriert (PRD: 60+).
  - Nicht migriert sind `GENERELL_HOCH` (Rückfall ohne Laborbedingung) und `PSAT_HOCH`; dessen einziger Text ist in
    keinem geprüften Kapitel belegt. Die drei leeren Einträge bleiben nach A-09 ausgelassen.
- **Fieberdomäne aktiviert** 22 Laborregeln über CRP, Kreatinin, Bilirubin und Laktat (A-64).
- **Doku:**
  - `docs/methodik.md` mit Nachrechnung des PRD-Beispiels.
  - `docs/regeln.md`, erzeugt mit `tools/rules_doc.py`; ein Test prüft, dass die Datei aktuell ist.
  - README mit Verweisen.

**Quellenprüfung:**
- **Gelesen** wurden die StatPearls-Kapitel und die Fieberquellen von sieben Hilfsagenten.
  - Jeder Beleg ist ein wörtliches Zitat von höchstens 15 Wörtern mit Abschnitt.
  - Die Zitate dienen nur der Prüfung; im Repository stehen nur Fundstellen und eigene Formulierungen.
- **Zugang:**
  - NCBI zeigt automatisierten Abrufen eine Browserprüfung (reCAPTCHA); sie wurde nicht gelöst und nicht umgangen.
  - Alle Kapitel sind im eingebauten Browser auf den normalen Seiten gelesen oder nachgeprüft.
  - Zwei Gruppen hatten zunächst einen anderen NCBI-Pfad bzw. Kopien im Internet Archive genutzt. Beide wurden auf den
    Live-Seiten wiederholt; kein Urteil änderte sich.
  - Fünf Belege aus drei Kapiteln habe ich zusätzlich selbst auf den Live-Seiten geprüft (Zinkmangel bei erniedrigter
    AP, Pseudohyperkaliämie, drei Aussagen zu Harnstoff und Kreatinin).
- **Ergebnis:**
  - Teilbelege sind nach A-62 nur im belegten Teil migriert.
  - Die Migrationstabelle nennt für jeden Text den Grund, wenn er keine Regel wurde.
- **Ausgeschlossen** nach ihren Bedingungen (A-61): EAU-Leitlinien und NEJM. OHDSI DQD enthält keine Messwertgrenzen
  mehr (A-65).

**PRD-Beispiel (D-05):**
- `refer_urgent` und `rf.qsofa_ge2` wie in der PRD.
- Kritisch sind Husten, CRP, Bewusstsein und Temperatur, nicht die qSOFA-Vitalwerte.
- Die Diagnosen sind Pneumonie, Sepsis, bakterielle Meningitis und vier Diagnosen aus `CRP_HOCH`.
- Test `test_prd_example_key_is_recalculated`.

**Geprüft** (lokal, Windows 11, Python 3.12.15):
- `uv run pytest`: 431 Tests grün, Abdeckung 99,8 %.
- `ruff check` und `ruff format --check`: sauber.
- `proof rules check`: ok. Paket `fever` 6 Regeln mit 39 Testvektoren, Paket `labs` 184 Regeln mit 574
  Testvektoren; Domäne `fever` mit 28 aktiven Regeln, 18 Feldern und 4 Referenzbereichen.
- Wheel gebaut und in eine frische Umgebung installiert: Es enthält beide Regelpakete mit Profilen;
  `proof rules check` und `proof rules list` laufen damit.

**Nicht lokal ausgeführt:** `pip-audit` und die Lizenzprüfung. Die Abhängigkeiten sind gegenüber U2 unverändert
(`uv.lock` gleich); beide laufen in der CI.

**CI:** Lauf 42536070825 auf Commit 02546d3.
- Jobs `test (windows-latest)` und `test (ubuntu-latest)` erfolgreich.
- Erfolgreich waren alle Schritte: Lint, Tests mit Abdeckung, Lizenzprüfung, pip-audit, Wheel frisch installiert.
- Gelesen über die öffentliche Actions-API (Jobs und Schritte).

**Offen bzw. für die ärztliche Prüfung vermerkt:**
- Alle Regeln tragen den Status „Entwurf, ärztlich ungeprüft“.
- Die Fieberdomäne aktiviert alle vier Regeln aus `CRP_HOCH` (A-64). Ob Diagnosen wie „Gewebeschädigung oder Trauma“
  im Fieberschlüssel stehen sollen, entscheidet die ärztliche Prüfung; abschalten heißt eine Zeile in
  `packs/fever/pack.yaml`.
- Zu wenige Werte im Status-Topf: CRP hat keinen Topf „niedrig“ (Untergrenze 0), Laktat nur 9 Patienten „niedrig“.
  Das prüft der Haltepunkt nach U4 (RK-02).
- 18 Laborfelder der Bibliothek haben keine Grenzen, weil keine offen lizenzierte Quelle sie nennt (A-65). Keine Domäne
  nutzt sie.
- `eGFR_NIEDRIG` → hypertensive Nephropathie stützt sich auf mehrere Aussagen des CKD-Kapitels zusammen, nicht auf
  einen Satz; die Migrationstabelle markiert sie für die ärztliche Prüfung.

**Abnahme U3 (DoD aus KONZEPT.md):** erfüllt.
- Die Migrationstabelle deckt alle 70 Einträge mit Inhalt ab; die 3 leeren sind nach A-09 begründet ausgelassen
  (`test_migration_table_covers_every_prototype_key`).
- Migriert sind 68 statt der in B10 geschätzten 69 Einträge: `PSAT_HOCH` bleibt nach der Regel aus D-11 ohne Regel,
  weil kein Kapitel seinen einzigen Text belegt.
- Jede Regel hat mindestens einen positiven und einen negativen Test, alle grün.
- qSOFA-Grenzwerttests: 21/22 pro Minute, 100/101 mmHg, Bewusstsein (`test_qsofa_boundaries`, Testvektoren von
  FEV-RF-001).
- Jede Quelle hat geprüfte Bedingungen, keine stammt von NICE (Test).
- Alle Regeln tragen den Status „Entwurf, ärztlich ungeprüft“ (Test).
- PRD-Beispiel wie in D-05 nachgerechnet (`docs/methodik.md`, Test).

### 08.11.2026 – U3 begonnen: SynthEHR-Lauf und Blocker B10
**SynthEHR-Lauf (D-03).** Befehl, im Ordner `proof/.local/synthehr/` und mit der Umgebungsvariable nur für diesen
Prozess:

```
DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1 SynthEHR.exe -d Biochemistry -s 42 <proof/.local/synthehr> 5000 100000
```

- SynthEHR 2.0.1 aus `Diagohelp\SynthEHR-cli-win-x64`, nur ausgeführt; die Ordnerliste ist vorher und nachher gleich.
- Lauf am 08.11.2026 von 14:33:53 bis 14:34:06 UTC, Exit 0.
- Ergebnis: `Biochemistry.csv`, 100 000 Zeilen, 5000 Patienten, 626 Testcodes, SHA-256
  `ae28f46c86b0f8fb4cce67b50c1681f1def2ea4a1b7f668ca72c43e4190be799`.
- Stichprobe der Referenzbereiche: CRP 0–10 mg/L, ALT 5–55 U/L, AP 30–130 U/L, Bilirubin 0–21 µmol/L, Albumin
  35–50 g/L, Kreatinin 44–80 µmol/L, Harnstoff 2,5–7,8 mmol/L, Kalium 3,5–5,3 mmol/L, Natrium 133–146 mmol/L, Laktat
  0,7–1,8 mmol/L.
- Negative Werte kommen vor (z. B. 5. Perzentil CRP −54 mg/L). Sie werden beim Profilbau verworfen und gezählt (D-03).
- Leukozyten fehlen (D-03); für CK, Harnsäure und eGFR fehlen die Referenzbereiche.

**Prototyp erfasst** (nur gelesen): `DDX_REGELN` hat 73 Einträge, davon 70 mit Inhalt, zusammen 194 Diagnosetexte über
47 Testcodes. Daraus ergibt sich B10 (ENTSCHEIDUNGEN.md).

### 08.11.2026 – U2 Regelmotor
**Umgesetzt** (`src/proof_rules/`):
- `model.py`:
  - Katalog: Felder mit Abschnitt, Typ, Einheit, Nachkommastellen, Grenzen mit Quelle, Bezeichnungen zh/en/de und
    Ausweicheinheiten;
  - Wortschatz, Quellenregister mit NICE-Sperre;
  - Bedingungen: `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `in` und `all`, `any`, `not`, `at_least`, Schwellen
    `{ref: lower|upper}`;
  - Regel mit Pflichtquelle, exakt passendem `requires` und Testvektoren;
  - Paketkonfiguration und Domäne.
- `logic.py`: dreiwertige Logik nach Kleene, Auswertung, Auswertungsbaum für Erklärungen.
- `engine.py`: Motor; Regeln mit gleichem Ziel werden mit „oder“ verknüpft; Entscheidbarkeit (A-53); Modelle `Key` und
  `VariantKey`.
- `ablation.py`: kritische Felder und Pflichtfragen (A-54).
- `keys.py`: Schlüssel mit Faktenprüfung gegen den Katalog.
- `loader.py`: Pakete lesen und prüfen, Domäne zusammensetzen, alle Testvektoren ausführen (A-55, A-56).
- `explain.py`: Klartext-Erklärung eines Schlüssels.
- Befehle:
  - `proof rules check` prüft alle Pakete;
  - `proof rules list` listet die aktiven Regeln einer Domäne;
  - `proof rules explain <fall>` zeigt Regelauswertung, Schlüssel und Ablation.
- Testpakete `tests/fixtures/packs/` (Domäne `demo`, Bibliothek `labx`): synthetisch und ohne klinische Aussage. Nur die
  qSOFA-Kriterien stammen aus der PRD.
- `tools/license_decisions.toml` mit certifi (D-10).

**Geprüft** (lokal, Windows 11, Python 3.12.15):
- `uv run pytest --cov`: 380 Tests grün, Abdeckung 99,8 %; `proof_rules` vollständig abgedeckt.
- `ruff check` und `ruff format --check`: sauber.
- Lizenzprüfung: 48 Pakete, 0 abgebrochen, 0 gemeldet (certifi per D-10 zugelassen).
- Wheel neu gebaut und in eine frische Umgebung installiert. Es enthält alle Module von `proof_rules`;
  `proof rules check` und `explain` laufen damit auf den Testpaketen.
- Laufzeit: Schlüssel mit Ablation für das PRD-Beispiel im Testpaket weit unter 1 s.
- D-05 nachgestellt:
  - PRD-Beispiel (qSOFA 3): kein Vitalwert kritisch.
  - Mit sRR 120 (qSOFA 2): Atemfrequenz und Bewusstsein kritisch, der Blutdruck nicht.

**Nicht lokal ausgeführt:** `pip-audit`. Die Abhängigkeiten sind gegenüber U1 unverändert (`uv.lock` gleich); die
Prüfung lief in der CI.

**CI** (gilt auch für die offenen Punkte aus U1):
- Repository `github.com/Ammxri/Proof`, Push von `dev`.
- Lauf 42489734249 auf Commit e472ad6: Jobs `test (windows-latest)` und `test (ubuntu-latest)` erfolgreich.
- Erfolgreich waren alle Schritte: Lint, Tests mit Abdeckung, Lizenzprüfung, pip-audit, Wheel frisch installiert.
- Damit gelten die Golden-Werte des Zufallsstroms auch unter Linux.
- Gelesen über die öffentliche Actions-API (Jobs und Schritte). Die Protokolltexte gibt die API nur mit Anmeldung
  heraus (403); sie sind nicht gelesen.

**Abnahme U2 (DoD aus KONZEPT.md):** erfüllt.
- Wahrheitstafeln aller Operatoren und Verknüpfungen, geprüft gegen alle zweiwertigen Belegungen.
- Handbeispiele für `answer`, `ask` und `refer_urgent`.
- Ablationstest je Regeltyp (Warnzeichen, Diagnose).
- Der Lader weist ab:
  - eine Regel ohne Quelle oder mit nicht registrierter Quelle;
  - ein unbekanntes Feld;
  - ein falsches `requires`.
- Ablation unabhängig von der Reihenfolge der Fakten (25 Permutationen).
- Importtest ohne Netz- oder Modellcode, statisch und zur Laufzeit; Schlüssel auch mit gesperrten Sockets.

**Folge für den Plan:** Der Profilbau aus U4 kommt an den Anfang von U3 (A-56).

### 08.11.2026 – U1 Grundgerüst
**Umgesetzt:**
- git (`dev`), `pyproject.toml`, `uv.lock`, `.python-version` 3.12.
- Abhängigkeiten: typer 0.28.0, pydantic 2.14.3, PyYAML 6.0.3; für die Entwicklung pytest, pytest-cov, ruff,
  pip-licenses, pip-audit.
- Ordnerstruktur nach §9 (A-31).
- Kernmodule in `src/proof/core/`:
  - `canonical`: kanonisches JSON und JSON Lines, strenges Parsen;
  - `hashing`: SHA-256;
  - `rng`: SHA-256-Zufallsstrom nach A-06, mit Golden-Werten;
  - `yamlio`: strenges YAML ohne doppelte Schlüssel und ohne Aliase; nur `true`/`false` sind Wahrheitswerte;
  - `i18n` mit `locales/{zh,en,de}.yaml`;
  - `disclaimer`: die Hinweissätze;
  - `manifest`: Manifest-Grundmodell mit Plattform und git-Stand;
  - `paths`: `PROOF_HOME`.
- CLI `proof` mit `--version`; jede Hilfe endet mit den Hinweisen in zh/en/de.
- Unter Windows wird umgeleitete Ausgabe auf UTF-8 gestellt.
- Lizenzdateien `LICENSE` (Apache-2.0) und `LICENSE-DATA` (CC BY 4.0), Originaltexte von apache.org und
  creativecommons.org, SHA-256 im Test. Dazu `NOTICE`, `README.md`, `.gitignore`, `.gitattributes` (LF) und
  `.env.example`.
- CI-Workflow `.github/workflows/ci.yml` für Windows und Linux, Aktionen per Commit-SHA gepinnt:
  - checkout v7.0.1, setup-uv v10.3.0;
  - Lint, Tests mit Abdeckung ≥ 85 %, Lizenzprüfung, pip-audit;
  - Wheel bauen und frisch installieren.
- `tools/check_licenses.py` (A-50, A-51).

**Geprüft (lokal, Windows 11, Python 3.12.15):**
- `uv run pytest --cov`: 145 Tests grün, Abdeckung 98,7 %.
- `ruff check` und `ruff format --check`: sauber.
- Lizenzprüfung: 48 Pakete, 0 GPL/AGPL. Gemeldet ist certifi 2026.10.23 (MPL-2.0), eine Abhängigkeit von pip-audit
  und ab U7 von httpx.
- `pip-audit`: keine bekannten Schwachstellen.
- Frische Installation: `uv build`, neue venv, Wheel installiert. `proof --version` und `proof --help` laufen, mit
  chinesischem Text auch bei umgeleiteter Ausgabe.
- Wheel enthält nur `proof` und `proof_rules` mit den Lizenzdateien. Das sdist enthält weder `.local/` noch die PRD.

**Nicht verifiziert:** CI unter Linux und Windows, und damit die Golden-Werte unter Linux. Grund: Das Repository fehlt
noch.

**Abnahme U1 (DoD aus KONZEPT.md):**
- Erfüllt:
  - frische Umgebung mit `uv sync --locked`;
  - Hinweise zh/en/de in der Hilfe (Test);
  - Golden-Werte unter Windows;
  - Strukturtest;
  - Unabhängigkeitstest.
- Offen: CI grün auf beiden Systemen.

### 08.11.2026 – Phase 2: Umsetzungskonzept
- Freigabe der Blocker: „Wir folgen überall deine Empfehlungen in diesem falle“. In ENTSCHEIDUNGEN.md bei D-02 bis D-08
  vermerkt.
- [KONZEPT.md](KONZEPT.md) geschrieben. Es enthält:
  - Architektur und Stack, Repository, Datenmodell, Schnittstellen, Rollen;
  - Sicherheit, Regulatorik, Teststrategie;
  - Phasenplan U1–U14 mit Definition of Done, GO-1, Risiken RK-01 bis RK-12;
  - Auslegungen A-31 bis A-48 und die Platzhalter.
- Abdeckung maschinell geprüft:
  - Von den 102 IDs der Matrix stehen 97 im Phasenplan und die 5 PRD-Risiken im Risikoabschnitt; keine fehlt.
  - Die Phasenspalte der Matrix ist daraus befüllt; es wurden nur Zellen ergänzt.
- Werkzeuge geprüft (nur gelesen):
  - uv 0.13.0 unter `%APPDATA%\Python\Python313\Scripts\uv.exe`, uv-verwaltetes Python 3.12.15, git 2.51.1,
    Ollama 0.11.11.
  - Im globalen Playwright-Ordner liegen die NeuroGrid-Browser; Proof nutzt einen eigenen Pfad (A-40).
- Prototyp nur gelesen: Aufbau von `DDX_REGELN` (Laborstatus-Schlüssel wie `CRP_HOCH` → Liste deutscher Diagnosen),
  Grundlage für A-32.

### 08.11.2026 – Einzelprüfung der Blocker, D-02 bis D-08
- Vorgabe: Grundsätzlich gelten die Empfehlungen, aber jede wird vorher einzeln nachgeprüft.
- B2: PRD-Zeitplan gelesen; v1.0 hat keinen Termin, kommt deshalb ans Ende und bekommt einen Go/No-Go-Punkt davor.
- B3:
  - Rohausgabe `out_biochem/Biochemistry.csv` analysiert: 15–17 Ziffern je Wert, auch in den Referenzbereichen. Ursache
    ist ein Gebietsschema-Fehler.
  - Testlauf von SynthEHR 2.0.1 ins Scratchpad, einmal normal, einmal mit `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`.
    Plausible Werte stiegen von 0–2,7 % auf 67–100 %.
  - Die SynthEHR-Ordnerliste blieb unverändert.
- B5: qSOFA-Ablation dreiwertig nachgerechnet (Beispiel und Variante mit qSOFA 2).
- B4/B9:
  - NICE-Bedingungen auf nice.org.uk gelesen: Nutzung außerhalb Großbritanniens ist gebühren- und lizenzpflichtig;
    KI-Nutzung ist eingeschränkt.
  - Surviving Sepsis Campaign 2021 zu qSOFA geprüft.
- B7/B8: `ollama list`, GPU-Auslastung, NeuroGrid-Remote und `gh` geprüft.

### 08.11.2026 – Grundregel D-01
- Vorgabe: Die PRD-Projekte sind unabhängig voneinander, und NeuroGrid wird nicht angefasst. Festgehalten als D-01.
  Danach entfallen PR-N08, PR-N10 und die Startbedingung in PR-G0 (bewusst abgewichen); B1 und B6 sind entschieden;
  A-30 regelt den gemeinsamen Rechner.
- Geprüft: Der NeuroGrid-Arbeitsbaum ist sauber, letzter Commit `3059f40` vom 03.11.2026.

### 08.11.2026 – Phase 0 und 1
- PRD (12 Seiten) per `pdftotext` (UTF-8) gelesen. Die Abbildung auf S. 4 wurde mit pypdf extrahiert und gesichtet
  (Ablauf: Sampler → Regelwerk + Ablation → Schlüssel → Bewertung; Varianten → Darstellung → Modell → Bewertung).
- Bestand gesichtet (nur gelesen):
  - Fieber-Prototyp `Desktop\Uni\Diagohelp\SynthEHR-cli-win-x64\scripts\`: `DDX_REGELN` hat 73 Einträge, davon 70 mit
    Diagnosen.
  - SynthEHR-Ausgabe: Laborwerte fast durchweg unplausibel (B3).
  - NeuroGrid-Kern `src/neurogrid/kernel` (5244 Zeilen; Importgrenze: Standardbibliothek, Pydantic, Jinja2, PyYAML,
    fontTools, Playwright, pypdf).
- Lokale Modelle: Ollama mit `mistral` und `nomic-embed-text`; GPU frei. NeuroGrid `full-2` läuft auf der CPU.
