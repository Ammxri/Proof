# Fortschritt – Proof

## Stand

**09.11.2026 – Phase 3, U3 abgeschlossen.**
- U1 (Grundgerüst), U2 (Regelmotor) und U3 (Fieber-Regelpaket und Migration) sind auf dem Zweig `dev` committet.
- Das Repository ist `github.com/Ammxri/Proof` (D-07). Gepusht wird nur `dev`.
- Die CI ist für U3 unter Windows und Linux grün (Lauf 42536070825).

- **Grundregel D-01:** Proof ist ein eigenständiges Projekt. Kein anderes Projekt wird geändert, und es gibt keine
  Abhängigkeit zu NeuroGrid.
- **Plan:** U1–U14 aus [KONZEPT.md](KONZEPT.md); v0.1 = U1–U9, v0.5 = U10–U12, v1.0 = U13–U14; GO-1 vor U13.

**Nächster Schritt:** U4 (Sampler, Fallschema, Fever-100). Die Laborprofile sind schon in U3 gebaut (A-56). Danach
folgt der Haltepunkt zu den dünnen Status-Töpfen (RK-02).

## Verlauf

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
