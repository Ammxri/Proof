# Umsetzungskonzept – Proof (STOPP 2)

Stand 08.11.2026. Grundlage sind die PRD, [ANFORDERUNGEN.md](ANFORDERUNGEN.md) und
[ENTSCHEIDUNGEN.md](ENTSCHEIDUNGEN.md) mit D-01 bis D-08 und A-01 bis A-30. Neue Auslegungen aus diesem Konzept sind
A-31 bis A-48 (Abschnitt 13); sie stehen auch in ENTSCHEIDUNGEN.md. Bis zur Freigabe entsteht kein Produktivcode.

Begriffe: **U1–U14** sind die Umsetzungsphasen dieses Plans. **P1–P3** sind die Gates der PRD (§13), **GO-1** ist der
Go/No-Go-Punkt dieses Plans.

## 1 Überblick

```
SynthEHR-CSV ──(einmalig, U4)──► Laborprofile ─┐
Regelpaket: Katalog, Regeln, Quellen ──────────┤
                                                ▼
Seed + Ziel (Diagnose, Warnzeichen) ──► Sampler ──► Fakten ──► Regelwerk + Ablation ──► Schlüssel ──► Fall
Fall ──► Varianten MR1–MR8 mit Erwartung ──► Darstellung zh/en/de ──► Prompt ──► Testlauf ──► Antwort
Antwort + Schlüssel/Erwartung ──► Bewertung S1–S7 ──► Profil ──► Bericht, Rangliste, Vergleich
Fälle + Regeln + Prüfvermerke ──► Datensatzkarte ──► Release-Paket
```

Leitlinien der Umsetzung:
- **Deterministisch:** Schlüssel und Bewertung rufen nie ein Sprachmodell auf (PR-N04). Gleiche Eingaben ergeben unter
  Windows und Linux bytegleiche Fälle.
- **Nachvollziehbar:** Jede erzeugte Datei hat eine Herkunft: Versionen, Hashes, Seeds und Quellen.
- **Eigenständig (D-01):** keine Abhängigkeit zu einem anderen Projekt. Diagohelp und SynthEHR werden nur gelesen.
- **Harte Grenzen statt Optionen:** Die EU-Grenze, das Verbot eines Sprachmodells als Richter und die Release-Sperre
  ohne ärztlichen Vermerk sind im Code erzwungen und getestet.

## 2 Architektur und Stack

| Baustein | Ort | Aufgabe | Anforderungen |
|---|---|---|---|
| Kern | `src/proof/core/` | kanonisches JSON, SHA-256, Zufallsstrom (A-06), sicheres YAML, Sprachtabellen, Manifest-Grundmodell, Hinweissätze | PR-N01, PR-D03 |
| Regelwerk | `src/proof_rules/` | Regel- und Katalogmodell, dreiwertige Logik, Schlussmotor, Ablation, Regelpakete je Domäne, Quellenregister | PR-F02, PR-F04, PR-K04–K09 |
| Fälle | `src/proof/cases/` | Fallschema, Laborprofile, Sampler, Sammlungen, Prüfvermerke, Release-Paket | PR-F01, PR-F03, PR-K01–K03, PR-W01, PR-W04, PR-F10, PR-F11 |
| Darstellung | `src/proof/render/` | Vorlagen zh/en/de, Einheiten, Schreibweisen, Prompts | PR-F05, PR-W02, PR-P01 |
| Varianten | `src/proof/variants/` | MR1–MR8 mit Erwartung | PR-F06, PR-M00, PR-MR1–MR8 |
| Testlauf | `src/proof/harness/` | Anbieter-YAML, OpenAI-kompatibler Client, Zwischenspeicher, EU-Sperre, Laufmanifest, Freitext-Spur | PR-F07, PR-N01–N03, PR-N05, PR-P03 |
| Bewertung | `src/proof/scoring/` | Antwortprüfung, S1–S7, Profil, Vergleich zweier Läufe | PR-F08, PR-S1–S7, PR-P02 |
| Bericht | `src/proof/report/` | HTML/PDF-Bericht, statische Rangliste, Datensatzkarte | PR-F09, PR-F10, PR-A04 |
| CLI | `src/proof/cli.py` | Typer-Befehle (Abschnitt 5) | alle |

**Stack laut PRD §14:** Python 3.12 (hier uv-verwaltet 3.12.15), uv 0.13 mit `uv.lock`, Typer, Pydantic v2, pytest,
ruff, GitHub Actions unter Windows und Linux.

**Weitere Bibliotheken.** Alle sind nicht GPL; die CI prüft die gesperrte Umgebung (A-26, A-44).

| Bibliothek | Zweck | Lizenz |
|---|---|---|
| PyYAML | Regelpakete, Anbieter, Prüfvermerke (`safe_load`, doppelte Schlüssel abgewiesen) | MIT |
| Jinja2 | Falltexte (Sandbox) und HTML (Autoescape) | BSD-3 |
| httpx | HTTP-Client des Testlaufs | BSD-3 (certifi: MPL-2.0, wird gemeldet) |
| Playwright | nur PDF aus dem HTML-Bericht (A-40) | Apache-2.0 |
| jsonschema, pypdf (nur Entwicklung) | JSON-Schema-Prüfung der Fälle; Textprüfung der PDFs | MIT, BSD-3 |
| pytest-cov, pip-licenses, pip-audit (nur Entwicklung) | Abdeckung, Lizenzprüfung, Prüfung auf bekannte Schwachstellen | MIT, MIT, Apache-2.0 |

Bewusst nicht dabei: kein Sprachmodell-SDK (der Client spricht das Chat-Protokoll direkt), keine Datenbank, keine Web-App.

## 3 Repository (PR-N09)

```
proof/
  pyproject.toml, uv.lock          Distribution „proof“ mit den Importpaketen proof und proof_rules
  LICENSE (Apache-2.0), LICENSE-DATA (CC BY 4.0), NOTICE, README.md, .gitignore, .env.example
  .github/workflows/ci.yml         Windows + Linux; pages.yml nur manuell auslösbar
  src/proof/        cli.py, core/, cases/, render/, variants/, harness/, scoring/, report/
  src/proof_rules/  model.py, logic.py, engine.py, ablation.py, keys.py, explain.py, loader.py,
                    packs/fever/ (pack, catalog, vocabulary, rules/, sources, profiles/; A-55),
                    packs/labs/  (migrierte Laborregeln mit migration.yaml, A-08, D-11),
                    packs/chest_pain/ (U14)
  data/collections/  fever-100/, fever-500/ (Fälle und Varianten als JSONL, collection.json)
  schema/            case, variant, response (JSON Schema, aus Pydantic erzeugt)
  providers/         Beispiel-Anbieter: Qwen lokal, DeepSeek-API, westlicher Anbieter (EU)
  review/            Prüfvermerke je Sprache (Platzhalter bis zur Lieferung)
  docs/              methodik.md, regeln.md (erzeugt), daten/synthehr.md, umsetzung/
  tests/             unit/, integration/ (mit Stub-Server), e2e/, golden/
  tools/             Entwicklerwerkzeuge außerhalb des Pakets, z. B. Lizenzprüfung (A-50), Erzeugung von docs/regeln.md
  .proof/ .local/    nicht versioniert: Zwischenspeicher, Läufe, private Mengen, SynthEHR-Ausgabe, PRD
```

Die sieben Ordner aus §9 liegen im src-Layout. `rules/` ist das Paket `proof_rules`, das PR-F02 beim Namen nennt
(A-31). Das src-Layout verhindert, dass Python versehentlich Code aus dem Arbeitsverzeichnis lädt.

## 4 Datenmodell

### 4.1 Faktenkatalog (je Domäne, `catalog.yaml`)
Jeder Fakt hat folgende Angaben:
- `code` (z. B. `vital.resp_rate`);
- `section`: `hx`, `exam`, `vital` oder `lab`, zugleich die vier Abschnitte für MR3 (A-04);
- `type`: `number`, `int`, `bool` oder `enum`, bei `enum` die erlaubten Werte;
- die kanonische Einheit, die Nachkommastellen und die physiologischen Grenzen mit Quelle;
- Bezeichnungen und Abkürzungen je Sprache;
- alternative Einheiten mit Umrechnung (für MR6).

Daneben stehen zwei Listen: irrelevante Fakten für MR4 und Widerspruchsvorlagen für MR7, beide mit Anwendungsbedingung.

### 4.2 Wortschatz
`ddx.*` und `rf.*` mit Bezeichnung je Sprache. Die erlaubten Codes einer Antwort sind:
- `ddx` und `red_flags` aus diesem Wortschatz;
- `questions` und `contradictions` aus den Feldcodes des Katalogs.

### 4.3 Regel (`rules/*.yaml`)
```yaml
- id: FEV-RF-001
  kind: red_flag                  # red_flag | ddx; red_flag ist das Warnzeichen-Flag aus PR-F02
  target: rf.qsofa_ge2            # genau ein Ziel-Code (A-32)
  requires: [vital.mental_status, vital.resp_rate, vital.sbp]
  when:
    at_least: 2
    of:
      - {field: vital.resp_rate, op: ge, value: 22}
      - {field: vital.mental_status, op: eq, value: altered}
      - {field: vital.sbp, op: le, value: 100}
  sources: [{ref: SRC-0001, locator: "<Fundstelle, in U3 geprüft>"}]
  status: draft_unreviewed        # „Entwurf, ärztlich ungeprüft“ (D-04)
  migrated_from: null             # bei migrierten Regeln der alte Schlüssel, z. B. CRP_HOCH
  tests:                          # mindestens ein positiver und ein negativer Testvektor (A-32)
    - {facts: {vital.resp_rate: 22, vital.mental_status: altered, vital.sbp: 120}, expect: true}
    - {facts: {vital.resp_rate: 21, vital.mental_status: normal, vital.sbp: 101}, expect: false}
```
Die Bedingungssprache ist deklarativ:
- Vergleiche `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `in`;
- Verknüpfungen `all`, `any`, `not`, `at_least`;
- Schwellen dürfen auf die Referenzgrenzen eines Laborprofils zeigen (`value: {ref: upper}`). Das brauchen die
  migrierten Regeln „erhöht/erniedrigt“.

Es gibt kein `eval` und keinen Ausdruckstext. Beim Laden wird geprüft:
- `requires` stimmt genau mit den Feldern der Bedingung überein;
- jede Quelle steht im Quellenregister und hat eine Bedingungsprüfung;
- alle Codes existieren und alle IDs sind eindeutig.

### 4.4 Schlussmotor, Ablation, Entscheidbarkeit
- **Logik:** Jede Regel ergibt `wahr`, `falsch` oder `unbekannt` (Kleene). Ein fehlender Fakt ist unbekannt.
- **Ausgabe:** Entscheidbarkeit, Menge der wahren Warnzeichen und Menge der wahren Diagnosen.
- **Entscheidbarkeit (A-33):**
  - `refer_urgent`, wenn mindestens ein Warnzeichen wahr ist;
  - sonst `ask`, wenn eine Warnzeichen- oder Diagnoseregel unbekannt ist, weil ein fehlender Fakt sie entscheiden
    würde;
  - sonst `answer`.
  - Vollständige Basisfälle (A-07) ergeben deshalb nie `ask`. `ask` entsteht nur durch Lücken (MR1, MR2,
    MR8 Schritt 1).
- **Ablation (PR-K05):** Jedes Feld wird einzeln entfernt und der Motor erneut ausgeführt. Ändert sich die Ausgabe, ist
  das Feld kritisch.
- **Pflichtfragen (PR-K09):** die fehlenden kritischen Felder einer Variante (genau gefasst in A-54).
- **Regeln mit gleichem Ziel** werden mit dem dreiwertigen „oder“ verknüpft; `ask` richtet sich nach den Zielen (A-53).
- **Neubeschriftung (PR-K04):** Weicht der Schlüssel vom Ziel des Samplers ab, bleibt er so. Die Abweichung wird in der
  Sammlung gezählt; Fakten werden nie korrigiert.
- **Nachrechnung des PRD-Beispiels (D-05):** steht mit Test in `docs/methodik.md`.

### 4.5 Laborprofil (`packs/<domäne>/profiles/<test>.json`)
Ein Laborprofil enthält:
- den Test-Code aus SynthEHR, den Fakt-Code und die Einheit;
- den Referenzbereich aus SynthEHR und die physiologischen Grenzen mit Quelle;
- Quantile je Status (normal / erhöht / erniedrigt);
- Zählwerte: Zeilen, Patienten, verworfene Werte;
- die Herkunft: SynthEHR 2.0.1, Befehl, Seed, SHA-256 der CSV, Datum.

Die Werte werden je Patient über alle Termine gemittelt (PR-W01). Leukozyten und Vitalwerte haben eigene Bereiche mit
Quelle (PR-W04, D-03).

### 4.6 Fall (PR-K02), genau die Felder der PRD (A-34)
```json
{"case_id": "FEV-000123", "seed": 123, "patient": {"age": 67, "sex": "f"}, "complaint": "fever",
 "facts": {"vital.temp_c": 39.2, "...": "..."},
 "key": {"determinability": "refer_urgent", "red_flags": ["rf.qsofa_ge2"],
         "critical_fields": ["..."], "ddx": ["ddx.pneumonia", "ddx.sepsis"]}}
```
Listen sind sortiert. Fälle enthalten keinen Fließtext (PR-K01).

Herkunft und Zählwerte stehen in `collection.json`:
- Schema-, Regel-, Katalog- und Profil-Hashes;
- Seed-Bereich und Zielplan;
- Neubeschriftungen und Inhalts-Hash je Fall.

### 4.7 Variante (PR-M00)
`variant_id`, `case_id`, `mr`, `variant_seed`, `change` (entferntes Feld, Permutation, neue Fakten, Einheitensystem,
Widerspruch, Gesprächsschritte), `facts`, `render`, `key` (neu berechnet, dazu `required_questions`) und `expectation`:
- `kind: absolute`: Sollwerte, z. B. `decision: ask`, `questions_include: [vital.resp_rate]`;
- `kind: invariant`: Vergleichsfelder gegen die Antwort auf den Basisfall (A-14).

### 4.8 Antwort (PR-P01)
Genau sechs Schlüssel: `decision`, `ddx`, `questions`, `red_flags`, `contradictions`, `rationale`. Alle Listen enthalten
nur erlaubte Codes. Gültig ist eine Antwort nur, wenn der ganze Text ein solches JSON-Objekt ist (A-13). Den JSON-Modus
der Anbieter nutzt Proof nicht (A-38).

### 4.9 Anbieter (`providers/*.yaml`, PR-F07)
```yaml
name: qwen-local
api: openai_chat                 # /v1/chat/completions; gilt für Ollama, vLLM und APIs
base_url: http://127.0.0.1:11434/v1
model: <beim Download gewählt, D-06>
api_key_env: null                # bei APIs der Name der Umgebungsvariable, nie der Schlüssel
origin: cn                       # cn | western | other, Pflichtfeld
region: CN                       # erklärter Serverstandort; western verlangt EU (PR-N03)
ollama_digest: true              # Digest über /api/show (A-21)
params: {max_tokens: 1024, seed: 0, think: false}   # temperature ist fest 0 und nicht einstellbar
pricing: {input_per_mtok: 0, output_per_mtok: 0, currency: EUR}  # bei APIs Eingabe von dir (A-20)
```

### 4.10 Lauf (`.proof/runs/<run_id>/`)
- `manifest.json` (PR-N01, PR-N02):
  - Zeitstempel (UTC), Versionen von Proof und Regeln, Hashes von Prompts, Vorlagen und Sammlung;
  - Seeds und Varianten-Seed;
  - Anbieter ohne Schlüssel, Modellversion und Digest, Parameter, erklärte Region;
  - Token, Kosten, Laufzeit, Plattform, git-Commit.
- `units.jsonl` mit Anfrage-Hash, Antworttext und Status.
- `profile.json` mit allen Kennzahlen, jeweils mit Zähler und Nenner, ohne Gesamtwert.

### 4.11 Prüfvermerk (`review/<sprache>.yaml`, A-23)
Name, Rolle (`physician` oder `pre_reviewer`), Klinikpraxis, Datum, Umfang, Hashes der geprüften Vorlagen, geprüfte
Fall-IDs. Ein `pre_reviewer` erfüllt die Release-Prüfung nie (PR-A02).

### 4.12 Quellenregister (`sources.yaml`, D-04)
ID, Zitat, URL, Art der Quelle, Lizenz bzw. Nutzungsbedingungen, Datum der Prüfung, erlaubte Nutzung. NICE ist
ausgeschlossen (Test).

## 5 Schnittstellen

### 5.1 CLI (`proof`, Typer)

| Befehl | Zweck |
|---|---|
| `proof labs build --csv <Biochemistry.csv>` | Laborprofile aus der SynthEHR-CSV (nur lesen) |
| `proof rules check \| list \| explain <fall>` | Regelpaket prüfen, auflisten, Schlüssel eines Falls erklären |
| `proof cases build --domain fever --n 100 --seed-start 1` | Sammlung mit Schlüsseln erzeugen |
| `proof cases validate <pfad>` | Schema und neu berechnete Schlüssel prüfen |
| `proof render <fall> --lang zh` | Darstellung ansehen |
| `proof variants build --variant-seed <n>` | neue Varianten auf Knopfdruck (PR-D02) |
| `proof run --provider <yaml> --set <sammlung> [--track json\|freetext] [--resume]` | Testlauf |
| `proof run --from-manifest <manifest>` | Lauf aus dem Manifest wiederholen |
| `proof score <lauf>` / `proof compare <lauf-a> <lauf-b>` | Bewertung, Vergleich zweier Läufe |
| `proof report <lauf…>` / `proof leaderboard <lauf…> --out site/` | Bericht HTML/PDF, statische Rangliste |
| `proof review sample \| packet \| verify --lang <l>` | Stichprobe, Prüfpaket, Prüfvermerk prüfen |
| `proof card` / `proof release [--draft]` | Datensatzkarte, Release-Paket |
| `proof private build --n <n>` | private Menge (PR-F11) |

Die Hilfe jedes Befehls endet mit den Hinweissätzen in zh/en/de (A-24).

### 5.2 Netz
- Ausgehend nur zur `base_url` des gewählten Anbieters: `POST /chat/completions`, dazu bei Ollama `POST /api/show`.
- TLS-Prüfung bleibt an, es gibt Zeitlimits, und Umleitungen auf andere Hosts werden abgewiesen.
- Keine Telemetrie, sonst keine Netzaufrufe; Ausnahme ist der einmalige Download des PDF-Browsers.

### 5.3 Umgebungsvariablen (`.env.example`)
- `DEEPSEEK_API_KEY`, oder ein beliebiger Name aus `api_key_env`;
- `PROOF_PRIVATE_SEED` (U13);
- `PROOF_HOME`, Voreinstellung `.proof/`.

Keine Variable hat einen Standardwert mit Geheimnis.

## 6 Rollen

| Rolle | Wer | Aufgaben |
|---|---|---|
| Projektverantwortlicher | du (@AYS) | Freigaben, GO-1, Gates P1–P3, Repository anlegen, DeepSeek-Schlüssel und echte Läufe, westliche Läufe aus der EU, Veröffentlichung (Pages, Hugging Face, arXiv), Prüfende gewinnen, Gespräche |
| Ärztliche Prüfung | je Sprache eine Ärztin oder ein Arzt, für zh mit chinesischer Klinikpraxis | Vorlagen und 10 % der Fälle prüfen, Vermerk unterschreiben |
| Vorprüfung | Medizinstudent (Shanghai) | Vorprüfung; ersetzt die ärztliche Prüfung nicht und erfüllt die Release-Prüfung nicht |
| Entwicklung | ich | Umsetzung U1–U14, Tests, Doku, lokale Prüfläufe mit Qwen |
| Nutzende | Modellteams, Lesende der Rangliste | Proof lokal ausführen, statische Ergebnisse lesen |

Die Software selbst hat keine Benutzerkonten. Rollen erscheinen nur in den Prüfvermerken und in der Datensatzkarte.

## 7 Sicherheit

1. **Geheimnisse:** API-Schlüssel und der private Seed kommen nur aus Umgebungsvariablen. Ein Test mit einem
   Erkennungswert prüft, dass sie in keinem Zwischenspeicher, Manifest, Log, Bericht oder Paket landen. `.env` und
   `.proof/` sind in `.gitignore`.
2. **Eingaben:** YAML nur über `safe_load`, doppelte Schlüssel werden abgewiesen. Alle Dateien werden über
   Pydantic-Modelle geprüft. Regeln enthalten keinen ausführbaren Ausdruck.
3. **Vorlagen:** Falltexte entstehen in der Jinja2-Sandbox mit `StrictUndefined`. HTML wird immer escaped, denn
   `rationale` stammt vom Modell. Die Rangliste hat eine strenge CSP und lädt keine fremden Skripte.
4. **Netz:** siehe 5.2; kein Neuversuch, keine Weiterleitung auf fremde Hosts.
5. **Private Mengen:** Sie werden nie in versionierte Pfade geschrieben (U13 prüft den Zielpfad). Seeds werden per HMAC
   abgeleitet; das Geheimnis selbst wird nie gespeichert.
6. **Abhängigkeiten:**
   - Lockfile, `uv sync --locked`;
   - Lizenzprüfung (GPL/AGPL bricht ab, LGPL wird gemeldet, A-26);
   - `pip-audit` gegen bekannte Schwachstellen;
   - kein Laden von Code aus heruntergeladenen Daten.
7. **Gemeinsamer Rechner (A-30):**
   - Eigene `.venv`.
   - Der PDF-Browser liegt unter `.proof/ms-playwright`; der globale Playwright-Ordner mit den NeuroGrid-Browsern
     bleibt unberührt (A-40).
   - Ollama-Modelle werden nur hinzugefügt.
   - Vor jedem Modelllauf prüfe ich, dass kein NeuroGrid-Prozess rechnet.

## 8 Regulatorik und harte Grenzen

| Grenze | Umsetzung | Nachweis |
|---|---|---|
| Kein Medizinprodukt, keine Versorgung (PR-D03, NZ-01) | Hinweissätze in CLI, Bericht, Rangliste, Datensatzkarte (A-24) | Test je Ausgabe |
| Referenz, keine klinische Wahrheit (PR-A01, NZ-09) | Satz in jeder Datensatzkarte | Test |
| Westliche Modelle nur über EU (PR-N03) | Pflichtfeld `origin`; `western` ohne `region: EU` wird abgewiesen; erklärte Region im Manifest | Test mit Stub; von hier kein `mistral` (D-06) |
| Kein Sprachmodell als Richter (PR-N04, NZ-04) | `proof_rules` und `proof.scoring` importieren keinen Netz- oder Modellcode | Importtest |
| Temperatur 0, kein zweiter Versuch (PR-N05) | Wert fest im Client; keine Wiederholung | Test mit Stub |
| Keine Live-Spielwiese, kein Dienst (PR-A04, NZ-02) | nur statisches HTML; Pages nur manuell und mit Freigabe (D-07) | Test: keine Netzaufrufe, keine Formulare |
| Nur synthetische Daten (PR-A05, NZ-06) | Fakten nur aus Sampler und Laborprofilen; keine Patientendaten im Repository | Test und Prüfung im Abschluss |
| Kein SynthEHR-Code, keine GPL-Bibliothek (PR-C02, PR-C03, NZ-07) | nur CSV lesen; Lizenzprüfung in der CI | Test, CI |
| Lizenzen (PR-C01) | Code Apache-2.0, Fälle CC BY 4.0; Lizenztexte im Wortlaut der Lizenzgeber | Dateien, Paketmetadaten, Karte |
| Ärztliche Prüfung vor Release (PR-A02, PR-A06) | Release verweigert ohne gültigen Vermerk je Sprache; zh muss die aktuellen Vorlagen-Hashes abdecken | Tests je Fehlerfall |
| Quellenregel (D-04) | Bedingungen jeder Quelle geprüft und im Register vermerkt; keine NICE-Quelle; nur eigene Formulierung | Test über das Register |
| Keine Bezahlfunktion (PR-C04, NZ-08) | private Mengen ohne Abrechnung; keine Zahlungsbibliothek | Abschlussprüfung |
| Rangliste ohne Einzelzahl (PR-P02, NZ-03) | kein Gesamtwert in Profil, Bericht und Rangliste | Test |

## 9 Teststrategie

- **Einheitentests:**
  - Wahrheitstafeln der dreiwertigen Logik;
  - jede Regel mit ihren Testvektoren;
  - Ablation je Regeltyp;
  - Sampler-Determinismus;
  - Umrechnungen;
  - Kennzahlen mit Handbeispielen, auch ungültige Antworten und leere Nenner (PR-F08).
- **Golden-Dateien:** Hashes fester Fälle und Zufallswerte, unter Windows und Linux gleich (A-06).
- **Integrationstests:**
  - Testlauf gegen einen lokalen Stub-Server im Testordner (OpenAI-Protokoll, Ollama-Digest);
  - Zwischenspeicher, kein zweiter Versuch, EU-Sperre;
  - Wiederholung aus dem Manifest und Erkennungswert für Geheimnisse.
- **End-to-End:** Sammlung → Varianten → Lauf gegen Stub → Bewertung → Bericht HTML/PDF → Rangliste → Karte →
  Entwurfspaket. Am Ende alle Abläufe UF-01 bis UF-07.
- **Leistung:** Schlüssel mit Ablation unter 1 s je Fall, gemessen über ganze Sammlungen unter Windows und Linux
  (A-29).
- **Echte Läufe:**
  - lokaler Probelauf mit Qwen in U7, Volllauf Fever-100 in U9, nur bei ruhendem NeuroGrid;
  - Belege kommen in FORTSCHRITT.md;
  - DeepSeek und westliche Modelle laufen bei dir.
- **CI (`ci.yml`, Windows + Linux):**
  - `uv sync --locked`, `ruff check`, `ruff format --check`;
  - `pytest` mit Abdeckung, Untergrenze 85 %;
  - Lizenzprüfung und `pip-audit`;
  - Wheel bauen und frisch installieren (`proof --help`).
- **Lokal:**
  - Ich lasse nur die betroffenen Tests laufen, die Vollsuite läuft in der CI.
  - Bis das Repository existiert, läuft die Vollsuite lokal. Belege unter Linux sind bis dahin „nicht verifiziert“.
- **Regeln für Tests:** Tests werden nie abgeschwächt oder gelöscht. Ein roter Test ist ein Befund.

## 10 Phasenplan

Gemeinsame Definition of Done für jede Phase:
- vollständiger Code ohne TODO, Stub oder Mock im Produktivcode (Stubs nur in Tests);
- Tests der Abnahmekriterien grün, ruff sauber;
- Vollsuite grün (in der CI, sobald das Repository existiert);
- ANFORDERUNGEN, FORTSCHRITT und ENTSCHEIDUNGEN nachgezogen;
- Commit auf `dev`, kurzer Phasenbericht.

| Phase | Inhalt | Anforderungs-IDs | Definition of Done |
|---|---|---|---|
| U1 Grundgerüst | git (`dev`), `pyproject`/`uv.lock`, Ordnerstruktur, Typer-CLI mit Hinweissätzen, Kern (kanonisches JSON, SHA-256, Zufallsstrom, sicheres YAML, Sprachtabellen, Manifest-Grundmodell), Lizenzdateien, `.gitignore`, `.env.example`, CI-Workflow, Lizenz- und Schwachstellenprüfung, Unabhängigkeitstest | PR-N06, PR-N07, PR-N09, PR-N10, PR-C01, PR-C03, PR-D03, NZ-01, NZ-07 | Frische Umgebung mit `uv sync --locked`; `proof --help` zeigt die Hinweise zh/en/de (Test); Zufallsstrom trifft feste Golden-Werte; Strukturtest; kein Import und keine Abhängigkeit auf `neurogrid` (Test); CI-Workflow vorhanden und, sobald das Repository existiert, grün unter Windows und Linux |
| U2 Regelmotor | Modelle für Regel, Quelle, Katalog, Wortschatz, Domäne; Lader mit Prüfungen; Bedingungssprache; dreiwertige Logik; Motor (Warnzeichen, Diagnosen, Entscheidbarkeit); Ablation; Pflichtfragen; `proof rules` | PR-F02, PR-F04, PR-K04, PR-K05, PR-K06, PR-K08, PR-K09, PR-N04, NZ-04 | Wahrheitstafeln aller Operatoren; Handbeispiele für `answer`, `ask`, `refer_urgent`; Ablationstest je Regeltyp; Lader weist Regel ohne Quelle, mit unbekanntem Feld oder falschem `requires` ab; Ablation unabhängig von der Reihenfolge der Fakten; Importtest ohne Netz- oder Modellcode |
| U3 Fieber-Regelpaket und Migration | Quellenregister mit Bedingungsprüfung; Faktenkatalog Fieber mit Bezeichnungen zh/en/de; Wortschatz; `rf.qsofa_ge2` und weitere Warnzeichen- und Diagnoseregeln, jede mit Quelle; Migration aller 70 Prototyp-Regeln mit Migrationstabelle; Aktivierung je Domäne (A-08); Nachrechnung des PRD-Beispiels; `docs/regeln.md` | PR-F02, PR-K07, PR-K08, PR-W03, PR-A03, NZ-04 | Migrationstabelle deckt 70 von 70 alten Schlüsseln ab, die 3 leeren sind begründet ausgelassen (A-09); jede Regel hat mindestens einen positiven und einen negativen Test, alle grün; qSOFA-Grenzwerttests (21/22 /min, 100/101 mmHg, Bewusstsein); jede Quelle mit geprüften Bedingungen, keine NICE-Quelle (Test); Status aller Regeln „Entwurf, ärztlich ungeprüft“; PRD-Beispiel nachgerechnet wie in D-05 |
| U4 Laborprofile, Sampler, Fallschema, Fever-100 | SynthEHR einmal mit dokumentiertem Befehl nach `.local/synthehr/`; Profilbau (nur CSV lesen, Mittel je Patient über alle Termine, Grenzen mit Quelle, verworfene Werte gezählt, Herkunft); eigene Bereiche für Leukozyten und Vitalwerte; Fallschema (Pydantic, JSON Schema); Sampler (Seed, Ziel-Diagnose, Warnzeichen-Status); Neubeschriftung; Sammlung Fever-100 mit `collection.json` | PR-F01, PR-F03, PR-F04, PR-K01, PR-K02, PR-K03, PR-K04, PR-W01, PR-W04, PR-A05, PR-C02, PR-D04, PR-L01, NZ-06, UF-01 | Alle Fever-100-Fälle bestehen Pydantic und JSON Schema; gleicher Seed ergibt bytegleichen Fall (Test, Golden-Hashes unter Windows und Linux); Schlüssel mit Ablation unter 1 s je Fall (Maximum über die Sammlung); Neubeschriftungen gezählt; Profile mit Herkunft und Zählwerten; kein SynthEHR-Code oder -Programm im Repository (Test); Verteilung von Entscheidbarkeit, Warnzeichen und Diagnosen im Fortschritt dokumentiert |
| U5 Darstellung, Prompt, Antwortschema, Prüfvermerke | Vorlagen de, en, zh mit vier Abschnitten (Aufbau nach der Langform des Prototyps, ohne Einschätzung und DDx); Zahlen- und Einheitenformat je Sprache; Systemprompt je Sprache mit erlaubten Codes; Antwortschema; Prüfvermerk-Format, 10-%-Stichprobe, Prüfpaket, `proof review` | PR-F05, PR-W02, PR-P01, PR-A02, PR-D01, PR-K01 | Jeder Fall wird in zh/en/de dargestellt, jeder Fakt erscheint im Text (Test über die Zuordnung Fakt → Textstelle); kein Diagnose-, Warnzeichen- oder Einschätzungstext im Fall (Test); Prompt nennt alle erlaubten Codes (Test); `review verify` weist fehlenden Vermerk, Platzhalter, reine Vorprüfung und abweichende Hashes ab (Tests); Stichprobe deterministisch und mindestens 10 % |
| U6 Varianten MR1, MR3, MR5 | Variantenmodell mit Erwartung; MR1 (kritisches Feld weg, Schlüssel neu, Pflichtfrage); MR3 (Permutation ungleich der Identität); MR5 (Sprachpaare); Varianten-Seed | PR-F06, PR-M00, PR-MR1, PR-MR3, PR-MR5, PR-D02, UF-01, UF-05 | Jede Variante besteht das Schema und trägt ihre Erwartung; MR1-Erwartung gleich dem Motor auf den Variantenfakten (`ask`, außer bei anderem sichtbarem Warnzeichen) und mit dem Feld in den Fragen; MR3 ändert nur die Reihenfolge; gleicher Varianten-Seed gleiche Varianten, neuer Seed neue (Tests) |
| U7 Testlauf | Anbieter-YAML; Schlüssel nur aus Umgebungsvariablen; OpenAI-kompatibler Client für API, Ollama und vLLM; Ollama-Digest; Temperatur 0, kein zweiter Versuch, kein JSON-Modus; Zwischenspeicher nach Hash; EU-Sperre; Laufmanifest mit Token und Kosten; Wiederholung aus dem Manifest; `--resume`; Beispiel-Anbieter; Qwen-Download und Probelauf | PR-F07, PR-N01, PR-N02, PR-N03, PR-N05, PR-C05, PR-L02, UF-02 | Tests gegen Stub: Temperatur 0 in jeder Anfrage; keine zweite Anfrage nach ungültigem JSON; Treffer im Zwischenspeicher ohne HTTP; Erkennungswert für Geheimnisse nirgends; westlicher Anbieter ohne EU abgewiesen, mit EU im Manifest vermerkt; Manifest enthält Seed, Modellversion, Parameter, Zeitstempel, Token, Kosten; Wiederholung aus dem Manifest ergibt gleiche Anfrage-Hashes; Qwen-Probelauf (10 Fälle × 3 Sprachen) mit Manifest belegt |
| U8 Bewertung | Strenge Antwortprüfung; S1–S7 mit Zähler und Nenner; S3 getrennt nach vollständig/unvollständig; S5 je MR; S6 Spannweite; Profil ohne Gesamtwert; `proof score`, `proof compare` | PR-F08, PR-S1, PR-S2, PR-S3, PR-S4, PR-S5, PR-S6, PR-S7, PR-P02, PR-D01, PR-D02, PR-N04, NZ-03, UF-02, UF-05 | Handbeispiele je Kennzahl, auch ungültiges JSON, Markdown-Codeblock, unbekannte Codes und leere Nenner (als „n/a“, nie 0); Profil ohne Gesamtfeld (Test); Vergleich zweier Stub-Läufe zeigt Änderungen je Kennzahl und Einheit; Importtest ohne Netz- oder Modellcode |
| U9 Datensatzkarte und Release v0.1 | Datensatzkarte (`README.md` mit Hugging-Face-Metadaten): Herkunft, Regeln, ärztliche Prüfung, Grenzen, Lizenz, Hinweise; Release-Paket mit allen Prüfungen; Entwurfsmodus; Entwurfspaket Fever-100; Volllauf Qwen auf Fever-100 | PR-F10, PR-A01, PR-A02, PR-A06, PR-C01, PR-D03, PR-D04, PR-L01, NZ-09, UF-04 | Release verweigert ohne gültige Vermerke, je Fehlerfall ein Test; Entwurfspaket in Karte und Ordnername als Entwurf markiert; Karte enthält den Satz aus PR-A01 in zh/en/de und alle Pflichtabschnitte (Test); Paket mit `SHA256SUMS` vollständig; Volllauf Qwen ergibt ein Profil (Beleg); v0.1-Anforderungen erfüllt oder „teilweise, manueller Rest offen“ |
| U10 Varianten MR2, MR4, MR6, MR7 | MR2 (unkritisches Feld weg); MR4 (irrelevante Fakten); MR6 (Einheiten und Schreibweisen); MR7 (Widerspruch) | PR-F06, PR-MR2, PR-MR4, PR-MR6, PR-MR7 | MR2 entfernt nur Felder, deren Ablation nichts ändert; MR4-Fakten werden von keiner aktiven Regel genutzt und ändern die Ausgabe nicht; MR6: Rundung im Text erhält alle Regelwerte, sonst wird die Variante verworfen und gezählt (A-39), Umrechnungen getestet; MR7 nur, wo die Vorlage passt, Erwartung enthält den Feldcode (Tests) |
| U11 Bericht, Rangliste, Freitext-Spur | HTML-Bericht je Lauf und Vergleich; PDF über Chromium; statische Rangliste unter `site/`; `pages.yml` nur manuell; Freitext-Spur mit Extraktionsmodell, überall als nicht deterministisch gekennzeichnet | PR-F09, PR-A04, PR-P02, PR-P03, PR-S3, PR-N08, PR-D03, PR-D05, PR-L05, PR-L06, NZ-02, NZ-03, UF-03, UF-07 | HTML ohne externe URL, Skriptquelle, Netzaufruf und Formular, mit CSP (Test); S3 in jeder Tabelle getrennt; keine Gesamtspalte; PDF unter Windows und Linux, chinesischer Text per pypdf lesbar; Freitext-Ergebnisse tragen `deterministic: false` und fehlen in der Haupttabelle (Test); das Extraktionsmodell wird in der Hauptspur nie aufgerufen (Test) |
| U12 500 Fälle und Release v0.5 | Sammlung Fever-500 mit MR1–MR7; Stichprobe der Fälle je Sprache für die ärztliche Prüfung; Hugging-Face-Paket (ohne Upload); Entwurfsrelease v0.5 | PR-L03, PR-L04, PR-A02, PR-F06, UF-04 | Fever-500 gültig, Schlüssel neu berechnet gleich, unter 1 s je Fall; Prüfpakete je Sprache; Karten-Metadaten gegen die dokumentierten Hugging-Face-Felder geprüft; Entwurfsrelease vollständig; v0.5-Anforderungen erfüllt oder „teilweise, manueller Rest offen“ |
| **GO-1** | Go/No-Go vor den v1.0-Phasen (D-02) | – | Entscheidung von dir, siehe Abschnitt 11 |
| U13 Private Mengen und MR8 | Private Mengen über HMAC mit eigenem ID-Präfix und Prüfung auf Überschneidung; Zielpfad außerhalb versionierter Pfade; MR8 mit zwei Gesprächsschritten in Testlauf und Bewertung | PR-F11, PR-MR8, PR-D05, PR-C04, NZ-08, UF-06 | Keine Überschneidung von IDs und Inhalts-Hashes zwischen öffentlicher und privater Menge (Test mit 10 000 Fällen); ohne `PROOF_PRIVATE_SEED` abgewiesen; Geheimnis nirgends gespeichert; gleiches Geheimnis gleiche Menge; MR8-Erwartung und -Bewertung gegen Stub mit zwei Schritten (Tests); keine Bezahlfunktion |
| U14 Zweite Domäne Brustschmerz | Regelpaket Brustschmerz: Katalog mit neuen Faktentypen (z. B. EKG, Troponin), Wortschatz, Regeln mit Quellen (D-04, D-08), Wertebereiche, Sampler-Profile, Bezeichnungen zh/en/de; Beispielsammlung | PR-F12, PR-D05 | Dieselben Befehle mit `--domain chest_pain` ergeben gültige Fälle, Schlüssel, Darstellungen, Varianten, Lauf und Bewertung (Stub); jede Regel mit Quelle und Tests; die Pipeline hat keinen domänenspezifischen Code (Test) |
| Abschluss (Phase 4) | Vollsuite, frische Installation, alle Abläufe End-to-End, Matrix Zeile für Zeile mit Nachweis, Abschlussbericht mit Platzhalterliste | alle IDs, insbesondere PR-C04, NZ-05, NZ-08, UF-01, UF-02, UF-03, UF-04, UF-05, UF-06, UF-07 | CI grün unter Windows und Linux; frische Installation aus dem Wheel; UF-01 bis UF-07 ausgeführt; jeder Matrixeintrag mit Status und Nachweis |
| Manuell (du) | Schritte außerhalb der Software; die Software liefert die Artefakte | PR-L02, PR-L05, PR-L06, PR-L07, PR-G0, PR-G1, PR-G2, PR-G3, PR-C04, NZ-05; manuelle Teile von PR-F05, PR-F09, PR-F10, PR-A02, PR-A06, PR-L01, PR-L03, PR-L04, PR-N07 | Status bleibt „offen“, bis du den Schritt meldest; Nachweis ist deine Angabe |

Zuordnung zu den PRD-Versionen:
- v0.1 = U1–U9;
- v0.5 = U10–U12;
- v1.0 = U13–U14.

Die Reihenfolge folgt dem Plan in PRD §11: Fallschicht, Renderer, Testlauf, Bewertung, dann v0.5.

Umstellung nach U2 (A-56): Der SynthEHR-Lauf und der Profilbau aus U4 laufen zu Beginn von U3. Grund: Die migrierten
Laborregeln brauchen die Referenzgrenzen der Profile, sonst lädt die Fieberdomäne nicht. Inhalt und
Anforderungs-IDs der Phasen bleiben gleich.

## 11 Go/No-Go-Punkte und Haltepunkte

**GO-1, vor U13 (Pflicht-Stopp, D-02).** Bis dahin sind v0.1 und v0.5 fertig. Ich lege vor:
- den Stand der Matrix;
- das Profil des Qwen-Volllaufs;
- die offenen manuellen Punkte;
- einen Vorschlag für die Brustschmerz-Scores mit geprüften Quellen (D-08).

Du entscheidest, ob v1.0 (U13, U14) jetzt gebaut wird oder erst nach PRD-Gate P2.

**Weitere Pflicht-Stopps:**
- **Zugang:** Nach U1 brauche ich `github.com/Ammxri/proof` (D-07). Bis dahin arbeite ich lokal weiter, und CI-Belege
  stehen auf „nicht verifiziert“.
- **Abweichung:** Muss ich von PRD oder Konzept abweichen, frage ich vorher.
- **Kostenpflichtig oder unumkehrbar:** Push auf `main`, Releases, Pages, Upload zu Hugging Face und echte
  DeepSeek-Läufe nur mit dir. Kostenlos und ohne Stopp: der Qwen-Download (etwa 5 GB, nur hinzugefügt) und der
  PDF-Browser (etwa 150 MB, unter `.proof/`).

**Technische Haltepunkte (ohne Stopp, Ergebnis im Phasenbericht):**
- **Nach U4:** Ich prüfe die Verteilung von Entscheidbarkeit, Warnzeichen und Diagnosen in Fever-100, die Quote der
  Neubeschriftungen und ob jeder Status-Topf der Laborprofile genug Werte hat. Fehlt ein Topf, nutze ich den eigenen
  Bereich mit Quelle und kennzeichne das. Ein stilles Auffüllen gibt es nicht.
- **Vor jedem Modelllauf:** Kein NeuroGrid-Prozess rechnet (A-30).

PRD-Gates P1–P3 entscheidest du nach deinen Läufen. Sie halten keine Phase dieses Plans auf. Fällt P1 durch, lässt
sich der Umfang über den Sprachparameter auf zh/en verkleinern, ohne Umbau.

## 12 Risiken

| ID | Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|---|
| RK-01 | Umfang der klinischen Inhalte: 70 migrierte Regeln mit oft mehreren Diagnosen, dazu neue Fieberregeln, jede mit geprüfter Quelle | U3 dauert am längsten | Quellenregister: eine geprüfte Quelle trägt viele Regeln. Status „Entwurf“; die ärztliche Prüfung bleibt bei dir |
| RK-02 | Ein Status-Topf eines Laborprofils hat zu wenige SynthEHR-Werte | Sampler kann den Status nicht ziehen | Zählwerte im Profil; eigener Bereich mit Quelle, gekennzeichnet (Haltepunkt nach U4) |
| RK-03 | Datenlizenz der SynthEHR-Ausgabe ungeklärt (D-03) | Release v0.1 betroffen | Offener Punkt vor dem ersten Release; Ausweg: alle Labore mit eigenen Bereichen, entscheidest du |
| RK-04 | Ungünstige Verteilung, z. B. kaum `answer`-Fälle | S1 wenig aussagekräftig | Zielplan geschichtet; Verteilung berichtet; Fakten werden nie korrigiert (PR-K04) |
| RK-05 | Bytegleichheit Windows/Linux (Gleitkomma, Unicode, Zeilenenden) | Reproduzierbarkeit | kanonisches JSON, nur Grundrechenarten im Sampler, `\n` fest, Golden-Hashes in der CI |
| RK-06 | Chinesische Schrift im PDF | PDF unvollständig | Systemschrift unter Windows, `fonts-noto-cjk` in der CI, Textprüfung per pypdf |
| RK-07 | Rechenzeit lokaler Läufe (Fever-100: etwa 2 000 Anfragen) | Stunden je Lauf | Zwischenspeicher, `--resume`, Läufe nur bei ruhendem NeuroGrid |
| RK-08 | Denkmodus oder Markdown-Ausgabe von Qwen senkt S7 | niedrige Werte | Ist Messergebnis, kein Fehler: gleicher Prompt für alle Modelle; der Denkmodus steht im Manifest |
| RK-09 | Repository fehlt noch | CI-Belege fehlen | lokale Vollsuite; „nicht verifiziert“, bis die CI läuft |
| RK-10 | Unnatürliches Chinesisch (PRD R5) | Glaubwürdigkeit | ärztliche Prüfung der zh-Vorlagen; Release-Sperre (PR-A06) |
| RK-11 | Umrechnung oder Rundung kippt eine Schwelle (MR6) | falsche „unverändert“-Erwartung | Rundtrip-Prüfung je Variante (A-39) |
| RK-12 | DeepSeek-API ändert sich | Lauf scheitert | nur das Standard-Chatprotokoll; Stub-Tests; echte Läufe bei dir |

PRD-Risiken aus der Matrix:
- PR-R1 → PR-L06 (manuell), PR-D01 (U5, U8), PR-F11 (U13);
- PR-R2 → U3, U9;
- PR-R3 → U6, U13;
- PR-R4 → U11;
- PR-R5 → U5, U9 und manuell.

## 13 Neue Auslegungen (A-31 bis A-48)

Sie stehen gleichlautend in ENTSCHEIDUNGEN.md und gelten mit der Freigabe dieses Konzepts.

- **A-31 Struktur:** src-Layout; die sieben Ordner aus §9 unter `src/proof/`, `rules/` als `src/proof_rules/`.
- **A-32 Regeln:**
  - Eine Regel hat genau ein Ziel.
  - Ein Prototyp-Eintrag mit k Diagnosen wird zu k Regeln mit gleichem `migrated_from`.
  - „Alle 60+ migriert“ heißt: Jeder der 70 Einträge ist auf mindestens eine Regel abgebildet. Die Migrationstabelle
    belegt das.
  - Jede Regel hat mindestens einen positiven und einen negativen Testvektor.
- **A-33 Entscheidbarkeit bei Lücken:** wie in 4.4. Basisfälle ergeben nie `ask`.
- **A-34 Fallobjekt:** genau die Felder der PRD, sortierte Listen; Herkunft und Zählwerte in `collection.json`.
- **A-35 Sampler-Profile:**
  - Sie sind Erzeugungsparameter, keine epidemiologische Aussage; das steht in der Karte.
  - Plausibilität kommt aus Wertebereichen mit Quelle, der Schlüssel immer aus dem Regelwerk.
  - Keine transzendenten Funktionen im Sampler, Rundung ganzzahlig.
- **A-36 Übertragungsfehler:**
  - Kein automatischer Neuversuch; die Einheit bekommt den Status `error` und zählt nicht in S1–S7.
  - Der Lauf ist dann unvollständig. `--resume` sendet nur Einheiten ohne Antwort.
  - Unvollständige Läufe kommen nicht in die Rangliste.
- **A-37 Wertung von MR5 und MR8:**
  - MR5 wird paarweise über die drei Sprachen der Basisfälle gewertet.
  - Bei MR8 zählt Schritt 1 als unvollständige Einheit, Schritt 2 als vollständige.
- **A-38 Kein JSON-Modus:** Proof nutzt weder JSON-Modus noch strukturierte Ausgabe der Anbieter, damit S7 die
  Formattreue des Modells misst.
- **A-39 MR6-Rundung:** Der gerundete Wert im Text, zurückgerechnet, muss alle Regelwerte erhalten. Sonst wird die
  Variante verworfen und gezählt.
- **A-40 PDF:** Chromium über Playwright mit eigenem Browser-Pfad unter `.proof/`. Chinesische Schrift: Systemschrift
  bzw. `fonts-noto-cjk` in der CI.
- **A-41 Entwurfspaket:** Ohne gültige Vermerke entsteht nur ein deutlich markiertes Entwurfspaket. Es ist kein
  Release und nicht zum Hochladen bestimmt.
- **A-42 Rangliste:** Standardsortierung nach Modellname; jede Spalte ist sortierbar (lokales Skript, kein Netz).
- **A-43 Sprache zh:** vereinfachtes Chinesisch (zh-Hans).
- **A-44 Prüfwerkzeuge:** pip-licenses und pip-audit in der CI als Teil des Sicherheitskonzepts, keine
  Produktfunktion.
- **A-45 Versionen:**
  - Proof bekommt 0.1.0, 0.5.0 und 1.0.0; `proof_rules` hat eine eigene Version im Manifest.
  - Tags nur lokal bis zur Freigabe.
- **A-46 Versionierte Sammlungen:** Fälle und Varianten der öffentlichen Sammlungen liegen als JSONL im Repository.
  Darstellungen entstehen erst im Release-Paket.
- **A-47 Zweite Domäne:** Die PRD nennt keine Größe. Die Beispielsammlung hat 100 Fälle; die Größe ist ein Parameter.
- **A-48 Lokale Belegläufe:** Qwen-Probelauf in U7, Volllauf Fever-100 in U9, beide nur als Beleg; veröffentlicht wird
  nichts.

## 14 Platzhalter, die bis zum Abschlussbericht offen bleiben können

| Platzhalter | Wo | Liefert |
|---|---|---|
| Namen, Rollen, Daten der ärztlichen Prüfung je Sprache | `review/*.yaml`, Datensatzkarte | du |
| Preise je 1 Mio. Token für DeepSeek und westliche Anbieter | `providers/*.yaml` | du |
| EU-Endpunkte westlicher Anbieter | `providers/*.yaml` | du |
| Hugging-Face-Namensraum, Pages-Adresse | Karte, `pages.yml` | du |
| Autor- und Kontaktangabe der Datensatzkarte | Karte | du |
| Datenlizenz der SynthEHR-Ausgabe | Karte, Abschlussbericht | Klärung offen (D-03) |
