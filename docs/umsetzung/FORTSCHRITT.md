# Fortschritt – Proof

## Stand

**08.11.2026 – Phase 3, U1 abgeschlossen.**
- Konzept freigegeben (D-09).
- Grundgerüst lokal auf dem Zweig `dev` committet.
- Das Repository `github.com/Ammxri/proof` fehlt noch (D-07). Darum ist die CI unter Windows und Linux noch nicht
  gelaufen.

- **Grundregel D-01:** Proof ist ein eigenständiges Projekt. Kein anderes Projekt wird geändert, und es gibt keine
  Abhängigkeit zu NeuroGrid.
- **Plan:** U1–U14 aus [KONZEPT.md](KONZEPT.md); v0.1 = U1–U9, v0.5 = U10–U12, v1.0 = U13–U14; GO-1 vor U13.

**Nächster Schritt:** U2 (Regelmotor). Sobald das Repository existiert: Push von `dev` und CI-Belege nachtragen.

## Verlauf

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
