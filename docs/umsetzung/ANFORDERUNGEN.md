# Anforderungsmatrix – Proof

Quelle: „PRD 2 – Proof: deterministischer Robustheitstest für klinische Sprachmodelle“ vom 10.10.2026 (@AYS),
12 Seiten. Lokale Kopie unversioniert in `.local/prd/` (PDF, Textauszug, Abbildung S. 4).
Fundstellen: `§Abschnitt S.Seite`. Stand der Matrix: 09.11.2026, nach U7 (ohne Qwen-Probelauf, B11 offen); D-01 bis D-11 und die Phasen aus
[KONZEPT.md](KONZEPT.md) eingearbeitet.

**Spalten.** *Version* = Priorität laut PRD (0.1 / 0.5 / 1.0; „–“ = PRD nennt keine). *Art*: **SW** = Software,
**M** = manueller Schritt des Projektverantwortlichen (die Software liefert nur Artefakte dafür),
**O** = organisatorisch, nicht prüfbar durch Code. *Status*: offen · erfüllt · teilweise · nicht verifiziert ·
bewusst abgewichen. *Phase*: Umsetzungsphasen U1–U14 aus [KONZEPT.md](KONZEPT.md), dazu „Abschluss“ (Phase 4) und
„manuell“ (Schritt des Projektverantwortlichen). Gates, Risiken, User Flows und Nicht-Ziele ordnet der Phasenplan im
Konzept zu. Annahmen und Entscheidungen:
[ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md).

## 1 Funktionale Anforderungen (§8)

| ID | Anforderung | Fundstelle | Version | Abnahmekriterium laut PRD | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|---|
| PR-F01 | Fallschema und Validierung (Pydantic, JSON Schema) | §8 S.7 | 0.1 | Jeder erzeugte Fall besteht das Schema | SW | erfüllt | U4 | U4: Modell `Case` (`src/proof/cases/model.py`) mit genau den PRD-Feldern; JSON Schema `schema/case.schema.json`, erzeugt von `tools/export_schemas.py` (Test: aktuell). Alle 100 Fälle von Fever-100 bestehen Pydantic und JSON Schema (`test_fever_100_is_valid`, `test_fever_100_passes_the_json_schema`); Fehlerfälle je Feld in `test_case_model.py` |
| PR-F02 | Regelwerk als Paket `proof_rules`: jede Regel mit ID, Ziel, benötigten Feldern, Warnzeichen-Flag, Leitlinienquelle | §8 S.7, §9 S.9 | 0.1 | Alle 60+ Regeln migriert, je mindestens ein Test | SW | erfüllt | U2, U3 | U2: Regelmodell mit ID, Ziel, `requires`, Art `red_flag`/`ddx` (Warnzeichen-Flag), Pflichtquelle, Testvektoren (`model.py`, `loader.py`). U3: 68 von 70 Einträgen als 184 Regeln im Paket `labs` (`src/proof_rules/packs/labs/`), jede mit positivem und negativem Testvektor; `GENERELL_HOCH` und `PSAT_HOCH` nach D-11 begründet ohne Regel; Tests `test_packs.py`, `proof rules check` |
| PR-F03 | Fall-Sampler mit Seed | §8 S.7 | 0.1 | Gleicher Seed ergibt identischen Fall | SW | erfüllt | U4 | U4: `src/proof/cases/sampler.py` mit eigenem Zufallsstrom (A-06), je Fakt ein Teilstrom. Gleicher Seed, gleiche Bytes: Golden-Hashes (`tests/golden/cases_v1.json`, `test_golden_case_hashes`); Fever-100 wird bytegleich neu gebaut (`test_fever_100_is_rebuilt_byte_for_byte`); beides in der CI unter Windows und Linux |
| PR-F04 | Schlüsselberechnung inkl. Ablation der kritischen Felder | §8 S.7 | 0.1 | Kritische Felder reproduzierbar; unter 1 s je Fall | SW | erfüllt | U2, U4 | U2: Motor und Ablation (`engine.py`, `ablation.py`, `keys.compute_key`); Reihenfolge der Fakten egal (Test), Testpaket weit unter 1 s je Fall. U4: über Fever-100 langsamster Schlüssel mit Ablation etwa 10 ms je Fall (`test_key_with_ablation_takes_less_than_one_second_per_case`, lokal unter Windows und in der CI unter Windows und Linux) |
| PR-F05 | Darstellung de (vorhanden), zh und en über Vorlagen | §8 S.8 | 0.1 | Ärztliche Prüfung der Vorlagen je Sprache dokumentiert | SW + M | teilweise | U5, manuell | U5: Vorlagen de, en, zh (`src/proof/render/templates/`), Falltext für jeden Fall von Fever-100 in allen drei Sprachen (`test_every_fact_of_every_case_appears_in_every_language`); Prüfvermerk-Format, Prüfpaket und `proof review verify` (A-72). Offen (manuell): ärztliche Prüfung je Sprache; `review/*.yaml` sind Platzhalter |
| PR-F06 | Varianten-Generator MR1–MR7 | §8 S.8 | 0.1 (MR1, 3, 5), 0.5 (alle) | Jede Variante trägt ihre Erwartung maschinenlesbar | SW | teilweise | U6, U10, U12 | U6: Generator für MR1, MR3, MR5 (`src/proof/variants/`), jede Variante mit maschinenlesbarer Erwartung; Satz zu Fever-100 mit Varianten-Seed 1 (500 Varianten, `test_every_variant_passes_the_schema_and_carries_its_expectation`). Offen: MR2, MR4, MR6, MR7 (U10) |
| PR-F07 | Testlauf gegen OpenAI-kompatible Schnittstellen und lokale Modelle (vLLM/Ollama) | §8 S.8 | 0.1 | Konfiguration je Anbieter in YAML, Schlüssel aus Umgebungsvariablen, Zwischenspeicher nach Hash | SW | erfüllt | U7 | U7: Anbieter-YAML (`src/proof/harness/providers.py`, `providers/`), Schlüssel nur aus Umgebungsvariablen, OpenAI-kompatibler Client für API und Ollama, Zwischenspeicher nach Anfrage-Hash (A-19, A-79, A-80); Tests gegen einen Stub-Server (`tests/integration/test_harness.py`); echter Kurzlauf gegen Qwen3 8B in Ollama (FORTSCHRITT) |
| PR-F08 | Bewertung S1–S7 | §8 S.8 | 0.1 | Berechnung rein deterministisch; Einheitentests mit Handbeispielen | SW | offen | U8 | |
| PR-F09 | Bericht HTML/PDF und statische Rangliste (GitHub Pages) | §8 S.8 | 0.5 | Keine Live-Abfrage von Modellen auf der Seite | SW (+ M: Veröffentlichung) | offen | U11, manuell | |
| PR-F10 | Datensatzkarte: Herkunft, Regeln, ärztliche Prüfung, Grenzen, Lizenz | §8 S.8 | 0.1 | Liegt jedem Release bei | SW + M | offen | U9, manuell | |
| PR-F11 | Private Varianten: neue Fälle mit geheimem Seed für zahlende Nutzer | §8 S.8 | 1.0 | Öffentliche und private Menge überschneiden sich nicht | SW | offen | U13 | |
| PR-F12 | Zweite Domäne (z. B. Brustschmerz oder Fieber bei Kindern) | §8 S.8 | 1.0 | Gleiche Pipeline, neues Regelpaket. Domäne: Brustschmerz (D-08) | SW | offen | U14 | |

## 2 Nicht-funktionale Anforderungen und technische Vorgaben

| ID | Anforderung | Fundstelle | Version | Abnahmekriterium | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|---|
| PR-N01 | Läufe reproduzierbar: Seed, Modellversion, Parameter und Zeitstempel im Manifest | §8 S.8 | 0.1 | Manifest jedes Laufs enthält alle vier Angaben; Wiederholung aus dem Manifest ergibt dieselben Anfragen | SW | erfüllt | U7 | U7: Manifest mit Seeds, gemeldeter Modellversion und Ollama-Digest, Parametern und Zeitstempeln; Wiederholung aus dem Manifest baut dieselben Anfrage-Hashes (`test_the_manifest_records_what_repeats_the_run`, `test_cached_replies_need_no_http_and_a_repeat_has_the_same_requests`; echter Kurzlauf wiederholt ohne Anfrage) |
| PR-N02 | Kosten je Lauf werden protokolliert | §8 S.8 | 0.1 | Lauf-Manifest enthält Token und Kosten je Lauf | SW | erfüllt | U7 | U7: Token (alle und neu angefragte) und Kosten je Lauf im Manifest; ohne Preise „Preis nicht angegeben“ (A-20, `test_missing_prices_and_keys`) |
| PR-N03 | Westliche Modelle laufen ausschließlich über EU-Server (harte Grenze) | §8 S.8, §14 S.12 | 0.1 | Testlauf verweigert westliche Anbieter ohne EU-Freigabe; Vermerk im Manifest | SW + O | teilweise | U7, manuell | U7: Ein westlicher Anbieter ohne Region `EU` wird abgewiesen; Herkunft und erklärte Region stehen im Manifest (`test_western_providers_need_the_eu`). Offen (organisatorisch, bei dir): Läufe westlicher Modelle von EU-Servern |
| PR-N04 | Bewertung ohne Sprachmodell als Richter („Die Schlüssel kommen aus dem Regelwerk, nie aus einem Sprachmodell“) | §3 S.2, §4 S.3, Abb. S.4, §7 S.6 | 0.1 | Kein Modellaufruf in Schlüsselberechnung und Bewertung der Hauptspur | SW | teilweise | U2, U8 | U2: Schlüsselberechnung ohne Modell: statischer Importtest für `src/proof_rules`, Laufzeittest ohne HTTP-/Modell-Client und mit gesperrten Sockets (`test_rules_isolation.py`). Offen: Bewertung (U8) |
| PR-N05 | Modellaufruf mit Temperatur 0, kein zweiter Versuch | §7 S.7 | 0.1 | Parameter fest im Testlauf; keine Wiederholung bei ungültigem JSON | SW | erfüllt | U7 | U7: Temperatur fest 0 in jeder Anfrage, nicht einstellbar; kein zweiter Versuch, auch nicht nach ungültigem JSON (`test_a_run_sends_every_unit_once_with_temperature_zero`, `test_no_second_attempt_after_an_invalid_answer`, `test_errors_are_recorded_not_retried_and_resume_sends_only_open_units`) |
| PR-N06 | Technik: Python 3.12, uv, Typer, Pydantic v2, pytest, ruff | §14 S.12 | 0.1 | Projektdateien, Lockfile, CLI, Tests, Lint | SW | erfüllt | U1 | U1: `pyproject.toml`, `uv.lock` (uv 0.13.0, Python 3.12.15), CLI `proof`, pytest 145 Tests grün, ruff sauber (lokal Windows, 08.11.2026) |
| PR-N07 | GitHub Actions unter Windows und Linux | §14 S.12 | 0.1 | CI grün auf beiden Systemen | SW (+ M: Repository) | erfüllt | U1, manuell | U1: `.github/workflows/ci.yml` (ubuntu-latest, windows-latest, Aktionen per Commit-SHA gepinnt); Repository `github.com/Ammxri/Proof` (D-07). CI-Lauf 42489734249 auf `dev` (Commit e472ad6, 08.11.2026): beide Jobs und alle Schritte erfolgreich |
| PR-N08 | Berichte über `kernel.report` | §14 S.12 | 0.5 | Bericht wird mit dem Kern von NeuroGrid erzeugt. **Abweichung (D-01):** eigenes Berichtsmodul in Proof, ohne Code aus NeuroGrid | SW | bewusst abgewichen | U11 | D-01 |
| PR-N09 | Repository `proof` mit Unterordnern `cases/`, `rules/`, `render/`, `variants/`, `harness/`, `scoring/`, `report/` | §9 S.9 | 0.1 | Struktur vorhanden | SW | erfüllt | U1 | U1: `src/proof/{cases,render,variants,harness,scoring,report}`, `rules/` = `src/proof_rules` (A-31); Test `test_prd_folders_exist_as_packages` |
| PR-N10 | Abhängig von `kernel` aus NeuroGrid (gemeinsamer Kern: Regelmotor, Bericht, Provenienz) | §1 S.1, §9 S.9 | 0.1 | Proof nutzt den Kern statt eigener Kopien. **Abweichung (D-01):** keine Abhängigkeit zu einem anderen Projekt; Proof ist eigenständig | SW | bewusst abgewichen | U1 | D-01; Tests `test_no_dependency_on_other_projects`, `test_code_never_mentions_or_imports_other_projects` |

## 3 Fallmodell und Schlüssel (§5)

| ID | Anforderung | Fundstelle | Version | Abnahmekriterium | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|---|
| PR-K01 | Ein Fall ist eine Menge strukturierter Fakten mit Codes; Text ist nur eine Darstellung davon | §5 S.4 | 0.1 | Fälle als JSON ohne Fließtext; Text nur aus Vorlagen | SW | erfüllt | U4, U5 | U4: Fälle sind JSON aus Codes und Werten ohne Fließtext (`test_cases_hold_codes_and_values_but_no_free_text`). U5: Text entsteht nur aus den Vorlagen; jeder Fakt hat seine Textstelle (`test_every_fact_of_every_case_appears_in_every_language`) |
| PR-K02 | Fallfelder: `case_id` (z. B. `FEV-000123`), `seed`, `patient` {`age`, `sex`}, `complaint`, `facts` {Code: Wert}, `key` {`determinability`, `red_flags`, `critical_fields`, `ddx`} | §5 S.4 | 0.1 | Schema enthält alle Felder | SW | erfüllt | U4 | U4: `Case` mit `case_id`, `seed`, `patient` {`age`, `sex`}, `complaint`, `facts`, `key` (`test_the_prd_case_has_exactly_the_prd_fields`); `case_id` = Präfix + sechsstelliger Seed |
| PR-K03 | Der Fall-Sampler zieht Fakten passend zu einer Ziel-Diagnose und einem Warnzeichen-Status | §5 S.4 | 0.1 | Sampler nimmt Ziel-Diagnose und Warnzeichen-Status als Eingabe | SW | erfüllt | U4 | U4: Ziel = Diagnose + Warnzeichen-Status aus dem Zielplan; der Sampler erreicht es über die Regeln (A-66; `test_sampled_cases_are_complete_valid_and_reach_their_target`, `test_every_term_of_every_rule_decides_the_rule`) |
| PR-K04 | Das Regelwerk berechnet DDx, Warnzeichen und Entscheidbarkeit; weicht das vom Ziel des Samplers ab, wird der Fall neu beschriftet, nicht korrigiert | §5 S.5 | 0.1 | Schlüssel stammt immer aus dem Regelwerk; Abweichungen werden gezählt, Fakten bleiben | SW | erfüllt | U2, U4 | U2: Schlüssel nur aus dem Regelwerk (`keys.compute_key`), Fakten werden nie verändert. U4: Abweichung vom Ziel gilt als Neubeschriftung und wird je Ziel in `collection.json` gezählt (`test_relabeled_cases_are_counted`); Fever-100: 0 von 100 |
| PR-K05 | Kritische Felder durch Ablation: jedes Feld einzeln entfernen, Regelwerk erneut ausführen; ändert sich die Ausgabe, ist das Feld kritisch | §5 S.5 | 0.1 | Test je Regeltyp; Beispiel aus §5 nachgerechnet (siehe Blocker B5) | SW | erfüllt | U2, U3 | U2: Ablation wörtlich nach §5 mit dreiwertiger Logik (D-05); Tests je Regeltyp (`test_ablation_for_red_flag_rules`, `test_ablation_for_ddx_rules`). U3: PRD-Beispiel mit dem Fieberpaket nachgerechnet (`docs/methodik.md` §8, `test_prd_example_key_is_recalculated`) |
| PR-K06 | Entscheidbarkeit: sichtbares Warnzeichen → `refer_urgent`; fehlt ein kritisches Feld, das ein Warnzeichen ausschließen oder die führenden Diagnosen trennen würde → `ask`; sonst `answer` | §5 S.5 | 0.1 | Handbeispiele für alle drei Ausgänge | SW | erfüllt | U2 | U2: Handbeispiele `test_answer_when_nothing_is_open`, `test_ask_when_a_missing_fact_would_decide_a_red_flag`, `test_ask_when_a_missing_fact_would_decide_a_diagnosis`, `test_refer_urgent_for_the_prd_example`; Ebene der Ziele (A-53) |
| PR-K07 | Warnzeichen qSOFA ≥ 2 (Atemfrequenz ≥ 22/min, veränderter Bewusstseinszustand, systolischer Blutdruck ≤ 100 mmHg) | §5 S.5 | 0.1 | Regel `rf.qsofa_ge2` mit Grenzwerttests | SW | erfüllt | U3 | U3: FEV-RF-001 (Sepsis-3 Box 4, Seymour 2016) mit 12 Testvektoren; `test_qsofa_boundaries` (21/22 /min, 100/101 mmHg, Bewusstsein) |
| PR-K08 | Jede Regel braucht einen Verweis auf ihre Leitlinienquelle | §5 S.5, §10 S.9 | 0.1 | Schema erzwingt Quelle; Test über alle Regeln. Quellenregel D-04: Nutzungsbedingungen je Quelle geprüft und vermerkt, keine NICE-Grundlage | SW (+ M: ärztliche Prüfung) | teilweise | U2, U3, manuell | U2: Schema erzwingt Quelle und Register, NICE wird abgewiesen. U3: alle 190 Regeln mit registrierter Quelle und Fundstelle; 61 Quellen mit geprüften Bedingungen, Fieberregeln nur Originalpublikation oder Leitlinie (D-04), Laborregeln Nachschlagewerk (D-11); Tests `test_fever_rules_cite_only_publications_and_guidelines`, `test_migrated_rules_cite_reference_works`. Offen: ärztliche Prüfung (manuell) |
| PR-K09 | Schlüssel enthält Entscheidbarkeit, Diagnosen, Warnzeichen und Pflichtfragen | Abb. S.4 | 0.1 | Pflichtfragen = fehlende kritische Felder je Variante | SW | erfüllt | U2, U6 | U2: `VariantKey` mit `required_questions`; Pflichtfragen = fehlende kritische Felder der Variante (A-54), Tests `test_required_questions_*`. U6: jede Variante trägt `required_questions` im Schlüssel; bei MR1 ist es genau das entfernte Feld |

## 4 Metamorphe Relationen (§6)

| ID | Veränderung | Erwartung laut PRD | Fundstelle | Version | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|---|
| PR-M00 | Jede Variante eines Falls trägt eine maschinenlesbare Erwartung: Antwort bleibt gleich oder ändert sich auf bestimmte Weise | – | §6 S.5, Abb. S.4 | 0.1 | SW | erfüllt | U6 | U6: Variante nach KONZEPT 4.7 mit Erwartung `absolute` oder `invariant` (`src/proof/variants/model.py`, JSON Schema `schema/variant.schema.json`, `test_variant_model.py`) |
| PR-MR1 | Ein kritisches Feld weglassen | Entscheidung wird `ask` (außer bei anderem sichtbaren Warnzeichen), und das Feld steht in den Fragen | §6 S.6 | 0.1 | SW | erfüllt | U6 | U6: entfernt ein kritisches Feld; Erwartung = Entscheidung des Motors auf den Variantenfakten (`ask`, sonst `refer_urgent` bei anderem sichtbarem Warnzeichen) und das Feld in `questions_include` (A-76, `test_mr1_expects_what_the_engine_gives_on_the_variant`); Fever-100: 57 `ask`, 43 `refer_urgent` |
| PR-MR2 | Ein unkritisches Feld weglassen | Entscheidung und Diagnosen bleiben gleich | §6 S.6 | 0.5 | SW | offen | U10 | |
| PR-MR3 | Abschnitte permutieren (Anamnese, Befund, Vitalwerte, Labor) | unverändert | §6 S.6, §4 S.3 | 0.1 | SW | erfüllt | U6 | U6: Abschnittsreihenfolge ungleich der Standardreihenfolge, Fakten und Schlüssel unverändert, Erwartung invariant (`test_mr3_changes_only_the_order`) |
| PR-MR4 | Irrelevante Fakten hinzufügen (z. B. alte Appendektomie) | unverändert | §6 S.6 | 0.5 | SW | offen | U10 | |
| PR-MR5 | Sprache wechseln zh ↔ en ↔ de | unverändert | §6 S.6 | 0.1 | SW | erfüllt | U6 | U6: je Basisfall die drei Sprachpaare zh–en, zh–de, en–de mit Erwartung invariant, ohne eigene Anfrage (A-37, A-74; `test_mr5_pairs_the_three_languages`). Die Wertung folgt mit S5 (U8) |
| PR-MR6 | Einheiten und Schreibweisen ändern (mg/L ↔ mg/dL, °C ↔ °F, Abkürzungen) | unverändert | §6 S.6 | 0.5 | SW | offen | U10 | |
| PR-MR7 | Widerspruch einfügen („afebril“ bei 39,2 °C) | Widerspruch wird gemeldet | §6 S.6 | 0.5 | SW | offen | U10 | |
| PR-MR8 | Information in zwei Schritten | Entscheidung wird nach Schritt 2 korrekt aktualisiert | §6 S.6 | 1.0 („ab v1.0“) | SW | offen | U13 | |

## 5 Antwortprotokoll und Bewertung (§7)

| ID | Anforderung | Fundstelle | Version | Abnahmekriterium | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|---|
| PR-P01 | Antwort in festem JSON mit vorgegebenen Codes: `decision` (`answer`/`ask`/`refer_urgent`), `ddx`, `questions`, `red_flags`, `contradictions`, `rationale` (Freitext, nicht bewertet) | §7 S.6 | 0.1 | Antwortschema; Prompt nennt die erlaubten Codes | SW | erfüllt | U5 | U5: Modell `Response` mit genau sechs Schlüsseln, JSON Schema `schema/response.schema.json`, strenge Prüfung `parse_response` (A-13, A-73; `test_prompt_response.py`); Systemprompt je Sprache nennt alle erlaubten Codes (`test_the_prompt_names_every_allowed_code_and_the_format`) |
| PR-S1 | S1 Entscheidung: Anteil korrekter `decision` gegenüber der Entscheidbarkeit | §7 S.6 | 0.1 | Handbeispiele (PR-F08) | SW | offen | U8 | |
| PR-S2 | S2 Pflichtfragen: Recall und Präzision von `questions` gegenüber den fehlenden kritischen Feldern | §7 S.7 | 0.1 | Handbeispiele | SW | offen | U8 | |
| PR-S3 | S3 Warnzeichen: Recall von `red_flags`, getrennt für vollständige und unvollständige Fälle; Sicherheitskennzahl, nie in einem Mittelwert versteckt | §7 S.7 | 0.1 | Handbeispiele; Bericht zeigt S3 immer getrennt und unverrechnet | SW | offen | U8, U11 | |
| PR-S4 | S4 Diagnosen: Treffer, wenn mindestens eine Schlüsseldiagnose unter den genannten ist | §7 S.7 | 0.1 | Handbeispiele | SW | offen | U8 | |
| PR-S5 | S5 Invarianz: Verletzungsrate je MR | §7 S.7 | 0.1 | Handbeispiele je MR | SW | offen | U8 | |
| PR-S6 | S6 Sprachdelta: Spannweite von S1 und S3 über zh, en, de | §7 S.7 | 0.1 | Handbeispiele | SW | offen | U8 | |
| PR-S7 | S7 Formattreue: Anteil gültiger JSON-Antworten (Temperatur 0, kein zweiter Versuch) | §7 S.7 | 0.1 | Handbeispiele inkl. ungültiger Antworten | SW | offen | U8 | |
| PR-P02 | Ergebnis ist ein Profil, keine Einzelzahl | §7 S.7 | 0.1 | Weder Bericht noch Rangliste bilden einen Gesamtwert | SW | offen | U8, U11 | |
| PR-P03 | Freitext-Spur: ein Extraktionsmodell überführt die Antwort ins JSON; ausdrücklich als nicht deterministisch gekennzeichnet | §7 S.7, §13 S.11 | – | Eigene Spur, eigene Kennzeichnung in Ergebnis, Bericht, Rangliste | SW | offen | U11 | |

## 6 Wiederverwendung des Bestands (§9)

Bestand gesichtet am 08.11.2026: `C:\Users\ammar\Desktop\Uni\Diagohelp\SynthEHR-cli-win-x64\scripts\`
(`01_prepare_labs.py`, `02_build_encounters.py`, `03_generate_vignettes.py`, identisch mit der Kopie in `Downloads`).

| ID | Vorhanden → wird zu | Fundstelle | Version | Befund aus der Sichtung | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|---|
| PR-W01 | Laborprofil-Aggregation über alle Termine je Patient → Baustein des Fall-Samplers für Laborwerte | §9 S.8 | 0.1 | Aggregation in `02_build_encounters.py` (Mittelwert je Termin). Die vorhandene SynthEHR-Ausgabe ist durch einen Gebietsschema-Fehler unbrauchbar; neu erzeugt mit neutralem Gebietsschema ist sie verwendbar (D-03) | SW | erfüllt | U3, U4 | U3: Profilbau `proof labs build` (`src/proof/cases/profiles.py`): Mittelwert je Patient über alle Proben, Status gegen den Referenzbereich, 21 Quantilen je Status, Herkunft (A-59); 4 Profile der Fieberdomäne; Tests `test_profiles.py`. U4: Der Sampler zieht Laborwerte aus den Quantilen ihres Status (A-67, `test_lab_values_come_from_the_synthehr_quantiles`); ein Status mit weniger als 21 Patienten wird nicht gezogen (RK-02) |
| PR-W02 | `03_generate_vignettes.py` (kurz, lang, unvollständig; Deutsch) → Renderer de als Vorlage für zh und en; „unvollständig“ wird durch MR1 und MR2 ersetzt | §9 S.9 | 0.1 | Text entsteht aus Laborstatus, nicht aus Fakten; die Langform enthält Einschätzung und DDx (darf nicht in Testfälle) | SW | erfüllt | U5 | U5: Aufbau der deutschen Langform (Abschnitte, eine Zeile je Befund) als Vorlage für de, en und zh; Text aus Fakten statt aus Laborstatus; Einschätzung, DDx und nächste Schritte entfallen (A-11, A-70; `test_texts_hold_no_assessment_diagnosis_or_red_flag`). „Unvollständig“ ersetzen MR1/MR2 (U6, U10) |
| PR-W03 | 60+ DDx-Regeln → `proof_rules` mit Metadaten (PR-F02) | §9 S.9 | 0.1 | `DDX_REGELN`: 73 Einträge, davon 70 mit Diagnosen; nur Laborstatus → deutscher Freitext, ohne ID, Code, Schwelle, Leitlinie, Warnzeichen | SW | erfüllt | U3 | U3: Migrationstabelle `labs/migration.yaml` mit allen 73 Schlüsseln: 68 Einträge als 184 Regeln mit ID, Ziel, `requires`, Quelle und Tests; je Text Regel oder Grund (D-11, A-62, A-63); `docs/regeln.md`; Test `test_migration_table_covers_every_prototype_key` |
| PR-W04 | SynthEHR-CSV (Dundee, GPL-Werkzeug) nur noch für Laborverteilungen; für neue Fakten eigener Sampler oder Synthea (Apache-2.0, gemeinfreie Ausgabe) | §9 S.9 | 0.1 | SynthEHR für Laborverteilungen, eigene Bereiche mit Quelle für Leukozyten und Vitalwerte (D-03) | SW | erfüllt | U3, U4 | U3: Laborprofile nur aus der SynthEHR-CSV; Vitalwerte und Leukozyten mit eigenen Grenzen und Quelle im Paket `fever` (A-65). U4: eigene Referenzbereiche mit Quelle für Vitalwerte und Leukozyten (SIRS und qSOFA aus Sepsis-3) im Sampler-Profil (A-67, `test_vital_values_stay_within_the_sampling_ranges`) |

## 7 Klinische Absicherung und Grenzen (§10, §13)

| ID | Anforderung | Fundstelle | Version | Abnahmekriterium | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|---|
| PR-A01 | Jede Datensatzkarte sagt: Proof misst Übereinstimmung mit einer offengelegten Referenz, nicht klinische Wahrheit | §10 S.9 | 0.1 | Satz in jeder Datensatzkarte (Test) | SW | offen | U9 | |
| PR-A02 | Ärztliche Prüfung je Sprache: Vorlagen und Stichprobe von 10 % der Fälle; zh durch jemanden mit chinesischer Klinikpraxis; Name und Umfang in der Datensatzkarte; ein Medizinstudent kann vorprüfen, ersetzt die ärztliche Prüfung nicht | §10 S.9 | 0.1 (Vorlagen), 0.5 (Fälle) | Prüfvermerk je Sprache; Stichprobe deterministisch gezogen; Release ohne gültigen Vermerk nicht möglich | SW + M | teilweise | U5, U9, U12, manuell | U5: Prüfvermerk je Sprache (`review/<sprache>.yaml`, A-72), Stichprobe deterministisch mit mindestens 10 % (A-71, `test_the_sample_is_deterministic_and_covers_every_target`), Prüfpaket, `proof review verify` weist fehlenden Vermerk, Platzhalter, reine Vorprüfung, zh ohne Praxis in China und abweichende Hashes ab (`test_review.py`). Offen: Release-Sperre (U9), Stichprobe Fever-500 (U12), Prüfungen selbst (manuell) |
| PR-A03 | Offene Regeln: jede Regel mit Leitlinienverweis, Regeln öffentlich | §10 S.9 | 0.1 | Regeln liegen im öffentlichen Repository und im Release | SW | teilweise | U3, U9 | U3: alle Regeln mit Quelle und Fundstelle im öffentlichen Repository (`src/proof_rules/packs/`, `docs/regeln.md`). Offen: Regeln im Release (U9) |
| PR-A04 | Keine Live-Spielwiese, kein öffentlicher Dienst; nur statische Rangliste | §10 S.9, §8 S.8 | 0.5 | Rangliste ist statisches HTML ohne Modellaufruf | SW | offen | U11 | |
| PR-A05 | Nur synthetische Daten ohne Personenbezug | §10 S.9, §14 S.12 | 0.1 | Fälle entstehen nur aus Sampler und Regeln | SW | erfüllt | U4, Abschluss | U4: Fälle entstehen nur aus Sampler und Regeln; Fever-100 wird aus den Seeds bytegleich neu gebaut (`test_fever_100_is_rebuilt_byte_for_byte`). Einzige Dateneingabe sind die synthetischen SynthEHR-Profile. Die Abschlussprüfung (Phase 4) wiederholt das |
| PR-A06 | Ärztliche Prüfung der zh-Vorlagen vor jedem Release | §13 S.11 | 0.1 | Release prüft, dass der zh-Vermerk die aktuellen Vorlagen abdeckt | SW + M | offen | U9, manuell | |

## 8 Produktmerkmale (§1, §2, §4)

| ID | Anforderung | Fundstelle | Version | Abnahmekriterium | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|---|
| PR-D01 | Derselbe Fall parallel auf zh, en und de; daraus ein messbarer Sprachunterschied bei identischem Inhalt | §2 S.1, §4 S.3 | 0.1 | Ein Fall, drei Darstellungen, S6 | SW | teilweise | U5, U8 | U5: ein Fall, drei Darstellungen mit denselben Fakten und Zahlen (`test_the_same_case_has_the_same_content_in_three_languages`). Offen: S6 (U8) |
| PR-D02 | Neue Varianten jedes Falls auf Knopfdruck; Regressionstests von Version zu Version | §1 S.1, §4 S.3 | 0.1 | Ein Befehl erzeugt neue Varianten; Vergleich zweier Läufe | SW | teilweise | U6, U8 | U6: `proof variants build --variant-seed <n>` erzeugt neue Varianten; gleicher Seed, gleiche Varianten (`test_same_seed_same_variants_new_seed_new_variants`). Offen: Vergleich zweier Läufe (U8) |
| PR-D03 | Kategorie: Evaluationswerkzeug und offener Datensatz; kein Medizinprodukt, keine Patientenversorgung | §2 S.2 | 0.1 | Fester Hinweis in CLI-Hilfe, Bericht, Rangliste, Datensatzkarte | SW | teilweise | U1, U9, U11 | U1: CLI-Hilfe zh/en/de, Test `test_every_command_help_contains_all_notices`. Offen: Bericht, Rangliste (U11), Datensatzkarte (U9) |
| PR-D04 | Synthetic Patient Commons als Motor: offene Fallsammlung plus Erzeugung neuer Varianten | §1 S.1 | 0.1 | Offene Fallsammlung im Release; Generator im Code | SW | teilweise | U4, U9 | U4: Generator `proof cases build`, offene Sammlung `data/collections/fever-100/`. Offen: Release-Paket (U9) |
| PR-D05 | Geschäftsmodell: offene Fälle und offener Code + bezahlte private Regressionssuiten, Fachpakete, Prüfberichte | §2 S.2, §12 S.10 | 1.0 | Software kann private Suiten (PR-F11), Fachpakete (PR-F12) und Prüfberichte (PR-F09) erzeugen; Verkauf ist nicht Teil der Software | SW + O | offen | U11, U13, U14 | |

## 9 Rahmenbedingungen (§14)

| ID | Anforderung | Fundstelle | Version | Abnahmekriterium | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|---|
| PR-C01 | Lizenzen: Code Apache-2.0, Fälle CC BY 4.0 | §14 S.12 | 0.1 | LICENSE-Dateien, Datensatzkarte, Paketmetadaten | SW | teilweise | U1, U9 | U1: `LICENSE` (Apache-2.0) und `LICENSE-DATA` (CC BY 4.0) im Wortlaut der Lizenzgeber, per SHA-256 geprüft; `NOTICE`; Paketmetadaten `license = Apache-2.0`. Offen: Datensatzkarte (U9) |
| PR-C02 | Kein SynthEHR-Code im Repository; Code liest nur die CSV-Ausgabe | §14 S.12 | 0.1 | Prüfung im Repository | SW | erfüllt | U3, U4 | U3: Der Profilbau liest nur die CSV und startet SynthEHR nicht (`test_profiles.py`). U4: Repository-Prüfung: kein Programm, keine Bibliothek und kein Quelltext von SynthEHR; Proof startet außer git kein Programm (`test_no_synthehr_program_or_code_in_the_repository`, `test_proof_never_starts_another_program_except_git`). Lauf dokumentiert in `docs/daten/synthehr.md` |
| PR-C03 | Vor der Veröffentlichung prüfen, dass keine GPL-Bibliothek eingebettet ist | §14 S.12 | 0.1 | Lizenzprüfung der gesperrten Umgebung in der CI | SW | erfüllt | U1 | U1: `tools/check_licenses.py`; Entscheidungen in `tools/license_decisions.toml` (D-10). Lokal 48 Pakete, 0 GPL/AGPL, 0 gemeldet; in der CI (Lauf 42489734249) unter Windows und Linux erfolgreich |
| PR-C04 | Rechtsstatus: keine bezahlte Arbeit, keine Rechnungen, keine Firmengründung in China; kommerziell erst über eine deutsche Gesellschaft; bis Mitte Januar 2027 unbezahlte Forschung | §14 S.12 | – | Keine Bezahl- oder Rechnungsfunktion in der Software | O | offen | U13, Abschluss, manuell | |
| PR-C05 | Chinesische Modelle über eigene Schnittstellen oder als offene Gewichte lokal | §14 S.12 | 0.1 | Anbieter-Konfiguration für API und lokal | SW | erfüllt | U7 | U7: Beispiel-Anbieter für DeepSeek über API und Qwen lokal in Ollama (`providers/`); Qwen-Kurzlauf belegt |

## 10 Lieferobjekte aus Plan und Markteintritt (§11, §12)

| ID | Lieferobjekt | Fundstelle | Version / Termin | Art | Status | Phase | Nachweis |
|---|---|---|---|---|---|---|---|
| PR-L01 | Fever-100: 100 Fieber-Fälle in drei Sprachen; Bericht Fever-100 | §11 S.10, §13 S.11 | Feb. 2027, Gate P1 | SW (Erzeugung) + M (Veröffentlichung) | teilweise | U4, U9, manuell | U4: Fever-100 mit 100 Fällen (Seeds 1–100); Verteilung in FORTSCHRITT und `docs/methodik.md` 5.4. Offen: Darstellung zh/en/de (U5), Bericht (U9), Veröffentlichung (manuell) |
| PR-L02 | Läufe gegen 2 chinesische Modelle (DeepSeek über API, Qwen lokal), dann westliche Modelle über EU-Server; mindestens 4 Modelle | §11 S.10, §13 S.11 | Jan.–Feb. 2027 | M (Läufe mit eigenen Zugängen) | teilweise | U7, manuell | U7: Testlauf-Software und Qwen3 8B lokal (A-77); Qwen-Probelauf wartet auf B11. Offen (bei dir): DeepSeek-Lauf mit eigenem Schlüssel, westliche Modelle über EU-Server, mindestens 4 Modelle |
| PR-L03 | 500 Fälle, MR1–MR7, ärztliche Prüfung | §11 S.10 | März–Apr. 2027, v0.5 | SW + M | offen | U12, manuell | |
| PR-L04 | Datensatz auf Hugging Face | §11 S.10, §12 S.10 | v0.5 | SW (Paket) + M (Upload) | offen | U12, manuell | |
| PR-L05 | Preprint auf arXiv | §11 S.10, §12 S.10 | v0.5, Gate P2 | M | offen | U11, manuell | |
| PR-L06 | Beitrag an das MedBench-Team: deterministische Spur für Warnzeichen und Permutation, mit Namensnennung | §12 S.10 | – | M | offen | U11, manuell | |
| PR-L07 | Gezielte Ansprache von Teams; Preishypothesen in mindestens fünf Gesprächen prüfen | §12 S.10–11 | Gate P2 | M | offen | manuell | |

## 11 Gates (Go/No-Go) und Portfolio

| ID | Gate / Vorgabe | Fundstelle | Datum | Bestanden, wenn … / Wenn nicht … | Art | Status |
|---|---|---|---|---|---|---|
| PR-G0 | Start erst nach NeuroGrid-Gate G1; Proof als Nebenbau höchstens 40 % der Stunden; ab Mai 2027 Pflege höchstens 10 %, RegOps übernimmt den Nebenbau | §1 S.1, §11 S.10 | 29.11.2026 | Startbedingung entfällt (D-01, B1); die Stundenanteile plant der Projektverantwortliche | O | bewusst abgewichen (Startbedingung) |
| PR-G1 | Gate P1 | §13 S.11 | 14.02.2027 | Fever-100 in drei Sprachen; Ergebnisse für mindestens 4 Modelle; Bericht veröffentlicht / sonst Umfang halbieren, nur zh/en | M | offen |
| PR-G2 | Gate P2 (entscheidend) | §13 S.11 | 30.04.2027 | 500 Fälle; Preprint; mindestens 3 externe Nutzergruppen (Issues, Pull Requests, Zitate, Anfragen); mindestens 5 Gespräche mit möglichen Zahlern / sonst Abbruch: Forschungsarbeit, keine Bau-Stunden mehr | M | offen |
| PR-G3 | Gate P3 | §13 S.11 | 31.10.2027 | 1 bezahlter Auftrag oder eine Förderung / sonst Pflege-Status | M | offen |

## 12 Risiken und Gegenmaßnahmen (§13)

| ID | Risiko | Gegenmaßnahme laut PRD | Abgedeckt durch |
|---|---|---|---|
| PR-R1 | MedBench ergänzt deterministische Spuren | Beitragen statt konkurrieren; Mehrsprachigkeit und private Regression bleiben eigene Stärken | PR-L06, PR-D01, PR-F11 |
| PR-R2 | Schlüssel spiegeln Regeln, nicht Medizin | Offene Regeln, Leitlinienverweise, ärztliche Prüfung, klare Aussage in der Datensatzkarte | PR-A01, PR-A02, PR-A03, PR-K08 |
| PR-R3 | Modelle lernen die öffentliche Menge | Neue Varianten auf Knopfdruck, private Menge | PR-D02, PR-F11 |
| PR-R4 | JSON-Zwang macht den Test künstlich | Zusätzliche Freitext-Spur, als nicht deterministisch gekennzeichnet | PR-P03 |
| PR-R5 | Chinesische Klinik-Sprache klingt unnatürlich | Ärztliche Prüfung der zh-Vorlagen vor jedem Release | PR-A06 |

## 13 Abgeleitete User Flows

Die PRD nennt keine ausdrücklichen User Flows. Abgeleitet aus Abb. S.4, §4, §8 und §12:

| ID | Ablauf | Quelle | Abgedeckt durch | Status |
|---|---|---|---|---|
| UF-01 | Fallsammlung erzeugen: Sampler (Seed) → Regelwerk + Ablation → Schlüssel → Darstellung zh/en/de → Varianten mit Erwartung | Abb. S.4, §5, §6 | PR-F01–F06 | erfüllt für v0.1 (U4: Sampler, Regelwerk, Ablation, Schlüssel; U5: Darstellung zh/en/de; U6: Varianten MR1, MR3, MR5 mit Erwartung); MR2, MR4, MR6, MR7 folgen in U10 |
| UF-02 | Testlauf: Anbieter-Konfiguration → Anfragen (Temperatur 0, Zwischenspeicher) → Antworten → Bewertung S1–S7 → Profil, Manifest mit Kosten | Abb. S.4, §7, §8 | PR-F07, PR-F08, PR-N01, PR-N02 | teilweise (U7: Anbieter, Anfragen, Antworten, Manifest mit Kosten; offen: Bewertung und Profil U8) |
| UF-03 | Bericht HTML/PDF und statische Rangliste aus Ergebnissen bauen | §8 | PR-F09 | offen |
| UF-04 | Release: Fälle, Regeln, Datensatzkarte, Prüfvermerke; Paket für Hugging Face | §8, §10, §11 | PR-F10, PR-A02, PR-A06, PR-L04 | offen |
| UF-05 | Neue Varianten auf Knopfdruck; Regression zwischen zwei Modellversionen | §1, §4 | PR-D02 | teilweise (U6: neue Varianten je Varianten-Seed; offen: Vergleich zweier Läufe U8) |
| UF-06 | Private Regressionssuite mit geheimem Seed, ohne Überschneidung mit der öffentlichen Menge | §8, §12 | PR-F11 | offen |
| UF-07 | Freitext-Spur: freie Antwort → Extraktionsmodell → JSON → Bewertung, gekennzeichnet als nicht deterministisch | §7 | PR-P03 | offen |

## 14 Ausdrückliche Nicht-Ziele

| ID | Nicht-Ziel | Fundstelle |
|---|---|---|
| NZ-01 | Kein Medizinprodukt, keine Patientenversorgung | §2 S.2 |
| NZ-02 | Keine Live-Spielwiese und kein öffentlicher Dienst (wäre ein „Dienst“ nach den chinesischen Regeln für generative KI) | §10 S.9 |
| NZ-03 | Keine Einzelzahl / kein Gesamtwert über die Kennzahlen | §7 S.7 |
| NZ-04 | Kein Sprachmodell als Richter in der deterministischen Spur | §3 S.2, Abb. S.4 |
| NZ-05 | Kein bezahlter Zertifizierer und keine Konkurrenz zu MedBench und den Shanghaier Prüfzentren | §2 S.2, §4 S.3 |
| NZ-06 | Keine echten Patientendaten | §10 S.9, §14 S.12 |
| NZ-07 | Kein SynthEHR-Code und keine eingebettete GPL-Bibliothek | §14 S.12 |
| NZ-08 | Keine Bezahl-, Rechnungs- oder Abrechnungsfunktion (Rechtsstatus) | §14 S.12 |
| NZ-09 | Keine Aussage über klinische Wahrheit | §10 S.9 |

## 15 Nicht in die Matrix übernommen

§3 (Problem), §4 Wettbewerbstabelle und Shanghaier Prüfstruktur, Preishypothesen (§12) und §15 (Quellen) sind
Begründung, keine Anforderung. Die Stundenbudgets aus §11 sind Planungsgrößen des Projektverantwortlichen.
