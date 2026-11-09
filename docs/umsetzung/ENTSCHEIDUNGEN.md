# Entscheidungen und Annahmen – Proof

Rangfolge bei Konflikten: Antworten und Freigaben des Projektverantwortlichen > PRD > bestehender Code > Annahmen.
IDs: **B** = Blocker-Frage (wartet auf Antwort), **A** = Annahme (Nicht-Blocker, gilt bis zum Widerspruch),
**D** = Entscheidung des Projektverantwortlichen.

## Eingaben des Auftrags

Die Eingabefelder des Auftrags waren leer. Belegt bzw. angenommen:

| Eingabe | Stand |
|---|---|
| PRD | „PRD 2 – Proof“ (10.10.2026), Kopie in `.local/prd/` |
| Ausgangslage | Neues Repository `Projekte/proof`; Bestand: Fieber-Prototyp unter `C:\Users\ammar\Desktop\Uni\Diagohelp\` (nur lesen), Kern in `Projekte/neurogrid/src/neurogrid/kernel` (wird weder genutzt noch kopiert; D-01) |
| Technische Vorgaben | laut PRD §14: Python 3.12, uv, Typer, Pydantic v2, pytest, ruff, GitHub Actions Windows + Linux, Berichte über `kernel.report` (abgewichen: eigenes Berichtsmodul, D-01); hier vorhanden: uv 0.13.0, uv-verwaltetes Python 3.12.15 |
| Zugänge und Dienste | keiner bekannt außer lokalem Ollama (nur `mistral`, `nomic-embed-text`); kein bezahlter LLM-Zugang; kein GitHub-Token, kein `gh` → B7, B8 |
| Regulatorik | laut PRD §10, §14 |
| Nicht anfassen | alle anderen Projekte, vor allem NeuroGrid (D-01); Diagohelp-Ordner (A-02) |
| Freigabemodus | angenommen: A, autonom nach Konzeptfreigabe (A-01) |

## Blocker (alle entschieden, siehe D-01 bis D-08, D-11 und D-12)

### B1 Startzeitpunkt – entschieden durch D-01
**Entscheidung:** Die Startbedingung „erst nach NeuroGrid-G1“ entfällt, denn die Projekte hängen nicht voneinander ab.
Die Umsetzung beginnt nach der Freigabe von STOPP 2. Die Rücksicht auf laufende NeuroGrid-Jobs regelt A-30.

Ursprüngliche Frage: PRD §1: Proof startet erst, wenn NeuroGrid Gate G1 am 29.11.2026 bestanden hat, und bekommt höchstens 40 % der
Stunden. Heute ist der 08.11.2026; auf demselben Rechner läuft NeuroGrid `full-2` noch bis etwa 09.11. mittags.
- **A (Empfehlung):** Konzept (STOPP 2) jetzt; Umsetzung direkt nach Freigabe. NeuroGrid hat Vorrang: keine Modellläufe
  und keine Lasttests, solange NeuroGrid-Läufe rechnen.
- B: Umsetzung erst ab dem 29.11.2026 nach bestandenem G1.

### B2 Umfang dieser Umsetzung – entschieden (D-02)
Die PRD reicht bis v1.0 (PR-F11, PR-F12, MR8); der Zeitplan in §11 endet aber mit v0.5, und v1.0 hat keinen Termin.
- **A (Empfehlung):** alle Software-Anforderungen bis v1.0 (PR-F01–F12, MR1–MR8, Freitext-Spur), Phasen nach Version
  geschnitten. Nicht-Software bleibt bei dir: ärztliche Prüfung, Läufe gegen ≥ 4 Modelle, Preprint, Upload zu
  Hugging Face, Gespräche, Gates. Die Software liefert dafür die Artefakte.
- B: nur v0.1 (PR-F01–F08, F10; MR1, MR3, MR5).
- C: v0.1 und v0.5, ohne PR-F11, PR-F12 und MR8.

### B3 Laborwerte: die SynthEHR-Ausgabe ist unbrauchbar – entschieden (D-03, Empfehlung geändert)
PRD §9 sieht SynthEHR „nur noch für Laborverteilungen“ vor. Gemessen am 08.11.2026 in
`Diagohelp\SynthEHR-cli-win-x64\output\_processed\biochem_clean.csv` (aus SynthEHR 2.0.1), Anteil der Zahlenwerte im
plausiblen Bereich: CRP 27 von 399 (6,8 %, z. B. −5,97·10¹⁴ mg/L), Bilirubin 3,5 %, Kreatinin, Harnstoff, Kalium, ALT,
AP, Albumin und Laktat je 0 %. Leukozyten und Vitalwerte fehlen ganz. Auch der „Laborstatus“ des Prototyps beruht auf
diesen Werten.
- **A (Empfehlung):** eigener Sampler: Wertebereiche je Laborwert und Status (normal / erhöht / erniedrigt) stehen im
  Regelpaket, mit Quelle des Referenzbereichs. SynthEHR und die Laborprofil-Aggregation (PR-W01) entfallen
  (**Abweichung** von §9).
- B: Synthea (Apache-2.0) für Labor- und Vitalwerte. Braucht Java, deckt nur wenige fieberrelevante Werte ab, mehr Aufwand.
- C: SynthEHR in anderer Version neu erzeugen und erneut messen (Ausgang offen).

### B4 Klinische Inhalte: wer legt Regeln, Schwellen, Codes und Leitlinienquellen fest? – entschieden (D-04)
Die 70 vorhandenen Regeln bilden nur Laborstatus auf deutschen Freitext ab (z. B. „regelmäßige körperliche
Aktivität“, „PSA erhöht → BPH“). Sie haben keine IDs, Codes, Schwellen, Leitlinien oder Warnzeichen und nutzen keine
Vitalwerte. Fieber-Schlüssel brauchen aber Vitalwerte, Anamnese, Befund, Warnzeichen (qSOFA u. a.) und Codes wie
`ddx.pneumonia`.
- **A (Empfehlung):** Ich entwerfe die Fieber-Domäne (Faktenkatalog, DDx- und Warnzeichen-Codes, Regeln, Schwellen,
  Sampler-Profile) aus öffentlich zugänglichen Leitlinien mit genauer Fundstelle. Alle 70 Regeln werden migriert
  (Codes statt Freitext, Schwellen statt Status). Jede Regel trägt bis zur ärztlichen Prüfung den Status „Entwurf,
  ärztlich ungeprüft“; die Datensatzkarte sagt das.
- B: Du bzw. eine Ärztin lieferst Regeln, Schwellen und Quellen; ich setze nur um. PR-F02 und PR-F04 warten so lange.

### B5 Ablation und das Beispiel in §5 widersprechen sich – entschieden (D-05)
Das Beispiel (AF 24, Bewusstsein verändert, sRR 96 → qSOFA 3) nennt alle drei Felder kritisch. Nach der Regel in §5
(„ein Feld entfernen; ändert sich die Ausgabe, ist es kritisch“) ist keines der drei kritisch: Fehlt eines, bleibt
qSOFA ≥ 2. Dafür wären Felder wie `hx.cough` kritisch, sofern sie Diagnosen trennen. Das Beispiel listet sie nicht.
- **A (Empfehlung):** Regel wörtlich. Fehlende Felder werden dreiwertig ausgewertet (wahr / falsch / unbekannt),
  die Ausgabe ist (Entscheidbarkeit, Warnzeichen-Menge, DDx-Menge). Das Beispiel gilt als Illustration, sein
  nachgerechneter Schlüssel kommt in die Doku. Folge: MR1 ergibt genau dann `ask`, wenn ein Warnzeichen oder eine
  führende Diagnose unentscheidbar wird.
- B: Die Ausgabe enthält zusätzlich die erfüllten Einzelkriterien der Warnzeichen. Damit sind die drei Felder des
  Beispiels kritisch, aber fast jedes genutzte Feld ebenso, und MR1 bleibt oft `refer_urgent`.

### B6 Anbindung an den NeuroGrid-Kern – entschieden durch D-01
**Entscheidung:** Alle drei Optionen entfallen. A wäre eine Abhängigkeit, B eine Änderung an NeuroGrid und C eine Kopie
fremden Codes. Proof baut Bericht (HTML/PDF), Manifest/Provenienz, kanonisches JSON, sicheres YAML-Laden und
Sprachtabellen selbst, schlank und nur für den eigenen Bedarf. Den Schlussmotor baut Proof ohnehin selbst. PR-N08 und
PR-N10 sind damit bewusst abgewichen.

Ursprüngliche Frage: `kernel` ist ein Unterpaket der Distribution `neurogrid`, die mne, scikit-learn, onnxruntime, deno u. a. mitzieht.
Sein Regelmotor prüft Datensätze (Klausel, Schweregrad, Nachweis) und kennt keine dreiwertige Schlusslogik über Fakten.
- **A (Empfehlung):** Proof hängt per Git-Abhängigkeit an `neurogrid` (fester Commit, öffentliches Repository) und nutzt
  `neurogrid.kernel` für HTML/PDF-Bericht, Manifest/Provenienz, kanonisches JSON, sicheres YAML-Laden und
  Sprachtabellen. Den Schlussmotor baut Proof in `proof_rules` selbst (**Abweichung** von §1 „Regelmotor“).
  NeuroGrid bleibt unverändert; Preis: eine große Installation.
- B: Der Kern wird in NeuroGrid als eigene kleine Distribution ausgelagert und Proof hängt nur daran. Das ist eine
  Änderung an NeuroGrid, erst nach dessen Läufen und mit eigener Freigabe.
- C: Kopie des Kerns in Proof mit Abgleichskript.

### B7 Westliche Modelle, dein Standort und das Prüfmodell – entschieden (D-06)
§8/§14: westliche Modelle ausschließlich über EU-Server; laut PRD bist du bis Mitte Januar 2027 in China. Lokal liegt
in Ollama nur `mistral` (westlich, offene Gewichte); Qwen fehlt. Die DeepSeek-API ist kostenpflichtig, und es gibt
keinen bezahlten Zugang.
- **A (Empfehlung):** Die Grenze gilt wörtlich, also auch für westliche offene Gewichte lokal: von hier kein
  `mistral`. Ich lade ein aktuelles Qwen-Instruct-Modell (7–8 B, ca. 5 GB, `ollama pull`) für die lokalen Prüfläufe.
  Die CI nutzt einen lokalen Stub-Server. Westliche Anbieter brauchen im Testlauf die erklärte Region `EU`, die im
  Manifest steht (technisch nicht nachprüfbar). Die DeepSeek-Anbindung wird gebaut und mit dem Stub geprüft; echte
  Läufe machst du mit eigenem Schlüssel.
- B: Lokale offene Gewichte sind erlaubt (auch `mistral`); nur API-Zugriffe auf westliche Anbieter brauchen die EU.
  Kein Download nötig.

### B8 GitHub-Repository und CI – entschieden (D-07)
§14 verlangt GitHub Actions unter Windows und Linux, §8 GitHub Pages. Es gibt lokal weder Token noch `gh`.
- **A (Empfehlung):** Du legst `github.com/Ammxri/proof` öffentlich an. Ich pushe nur auf `dev`; `main`, Releases und
  Pages nur mit deiner Freigabe. Bis dahin arbeite ich lokal mit git.
- B: privat bis zum ersten Release. Pages und öffentliche CI-Belege kommen erst danach.

### B9 Zweite Domäne (PR-F12, nur bei B2 = A) – entschieden (D-08, Empfehlung geändert)
- **A (Empfehlung):** Fieber bei Kindern unter 5 Jahren nach dem Ampelsystem von NICE NG143. Die Tabelle ist
  ausdrücklich deterministisch und teilt den Faktenkatalog mit der Fieber-Domäne.
- B: Brustschmerz (ESC-Leitlinien). Braucht neue Faktentypen (EKG, Troponin-Verlauf).

### B10 Quellen der 70 migrierten Laborregeln – entschieden (D-11)
Befund aus der maschinellen Erfassung von `DDX_REGELN` (nur gelesen, SHA-256 der Datei `6a82aa96…12c4b`):
- 73 Einträge, davon 70 mit Inhalt. Zusammen sind es 194 Diagnosetexte über 47 Testcodes. Nach A-32 (eine Regel je
  Ziel) werden daraus rund 190 Regeln.
- Die Texte sind Lehrbuchzuordnungen, z. B. „AP erniedrigt → Zinkmangel“. Für fast keine gibt es eine
  Originalpublikation oder eine Leitlinie mit genau dieser Aussage. Die Quellenregel aus D-04 erlaubt aber nur diese
  beiden Arten.
- `GENERELL_HOCH` ist ein Rückfall ohne Laborbedingung: Er greift, wenn keine andere Regel greift, und enthält keine
  Diagnose. Als Regel über Fakten lässt er sich nicht ausdrücken.
- Ein Eintrag bezeichnet einen anderen Laborwert als gedacht: `UR` hat in SynthEHR den Referenzbereich 3–8,5 mmol/L und
  ist damit Harnstoff. `UR_HOCH` führt im Prototyp aber zu Hyperurikämie.

Optionen:
- **A (Empfehlung):** Für die migrierten Laborregeln sind zusätzlich Nachschlagewerke mit geprüften Bedingungen
  zugelassen, je Laborabweichung ein Kapitel (z. B. StatPearls im NCBI Bookshelf, je Kapitel CC BY-NC-ND 4.0, dazu die
  Nutzungsbedingungen von StatPearls).
  - Übernommen werden nur Tatsache und Fundstelle, in eigener Formulierung.
  - Eine Zuordnung, die das Kapitel nicht belegt, wird nicht zur Regel; die Migrationstabelle vermerkt das.
  - `GENERELL_HOCH` wird begründet ausgelassen; damit sind 69 von 70 Einträgen migriert (PRD: 60+).
  - Für Fieberregeln und Warnzeichen bleibt D-04 unverändert.
- B: D-04 gilt streng auch für die Laborregeln. Viele Zuordnungen bleiben ohne Quelle und werden nicht migriert. Die
  60+ der PRD sind dann gefährdet.
- C: Alle Zuordnungen werden migriert, mit deutlich markierter Platzhalterquelle („Quelle ausstehend“). Die Quellen
  lieferst du oder die ärztliche Prüfung nach. PR-K08 bleibt bis dahin „teilweise“, und das Release ist gesperrt.

### B11 Qwen ohne Denkmodus über Ollama – entschieden (D-12)
Befund vom 09.11.2026:
- **Modell:** Geladen ist `qwen3:8b` (5,2 GB, Digest `500a1f06…`, A-77). Es ist ein Hybridmodell, das vor der Antwort
  „denkt“. Ein reines Instruct-Modell von Qwen3 gibt es in Ollama nur mit 4 B und 30 B.
- **Schnittstelle:** Ollama 0.11.11 ignoriert auf seiner OpenAI-kompatiblen Schnittstelle jeden Schalter, der das
  Denken abstellt (`think: false`, `options.think`; `reasoning_effort` wird abgelehnt). Die Antwort beginnt dann mit
  `<think>…</think>`, erst danach folgt das JSON. Nach A-13 ist jede solche Antwort ungültig.
- **Kurzlauf** (1 Fall × 3 Sprachen): 3 von 3 Antworten ungültig. Das JSON am Ende wäre jeweils plausibel gewesen
  (`refer_urgent`, `rf.qsofa_ge2`).
- **Ollamas eigene API** (`POST /api/chat` mit `think: false`) liefert die Antwort ohne Denkteil.

Optionen:
- **A (Empfehlung):** Eine zweite Schnittstellenart `ollama_chat` für lokale Ollama-Modelle.
  - Gleiche Nachrichten, Temperatur 0, Seed und Tokengrenze; der Denkmodus ist abschaltbar und steht im Manifest.
  - Anfragen gehen nur an diesen Rechner.
  - **Abweichung** von KONZEPT 4.9 und 5.2, die für Ollama nur das OpenAI-Protokoll vorsehen.
  - Die PRD verlangt „lokale Modelle (vLLM/Ollama)“ ohne Vorgabe der Schnittstelle (PR-F07). Prüfmodell bleibt
    Qwen3 8B.
- **B:** Prüfmodell `qwen2.5:7b-instruct`, ein reines Instruct-Modell ohne Denkmodus, eine Generation älter.
  - 4,7 GB zusätzlich, nur hinzugefügt. Keine Änderung am Konzept.
  - `qwen3:8b` bleibt geladen, denn Ollama-Modelle werden nur hinzugefügt (A-30).
- **C:** Qwen3 8B mit Denkmodus. Die ungültigen Antworten sind Messergebnis (RK-08).
  - Keine Änderung, aber Probe- und Volllauf zeigen dann kaum mehr als S7 = 0.

Nicht empfohlen: Ollama aktualisieren. Das wäre eine globale Änderung auf dem gemeinsamen Rechner (A-30).

## Annahmen (Nicht-Blocker)

**A-01 Freigabemodus.** A: Nach der Konzeptfreigabe arbeite ich die Phasen autonom durch. Ich stoppe trotzdem bei
den Pflicht-Stopps des Auftrags (Abweichung, Go/No-Go, unumkehrbar/kostenpflichtig, fehlender Zugang).

**A-02 Nicht anfassen.** Für NeuroGrid und alle anderen Projekte gilt jetzt D-01. Zusätzlich wird
`Desktop\Uni\Diagohelp` nur gelesen: Der Prototyp ist Bestand, keine Baustelle.

**A-03 Projektordner.** `C:\Users\ammar\Desktop\Buisness\Projekte\proof`, neben NeuroGrid. Die PRD liegt
unversioniert in `.local/prd/`. Vorgehen wie bei NeuroGrid, nur als Vorbild und ohne gemeinsame Dateien: `dev`-Zweig,
Vollsuite in der CI, lokal nur betroffene Tests.

**A-04 Codes.** Englische, punktgetrennte Codes mit festen Präfixen wie im Beispiel: `hx.` (Anamnese), `exam.`
(Befund), `vital.` (Vitalwerte), `lab.` (Labor), `ddx.`, `rf.`. Die vier Präfixe der Fakten sind zugleich die vier
Abschnitte für MR3. Die Bezeichnungen je Sprache stehen in Sprachtabellen.

**A-05 Einheiten.** Fakten tragen kanonische Einheiten (wie im Beispiel: °C, mg/L, G/L, mmHg, /min). MR6 ändert nur die
Darstellung (Umrechnung beim Rendern); Fakten und Schlüssel bleiben gleich.

**A-06 Zufall.** Der Sampler nutzt einen eigenen, aus SHA-256 abgeleiteten Zufallsstrom statt `random`. So ist ein Fall
für denselben Seed auf Windows, Linux und über Python-Versionen hinweg bytegleich. `case_id` = Domänenpräfix +
sechsstelliger Seed (`FEV-000123` ↔ Seed 123), wie im Beispiel.

**A-07 Vollständige Basisfälle.** Ein Basisfall enthält alle Felder, die die aktiven Regeln seiner Domäne brauchen, plus
unkritische Kontextfakten (damit MR2 Material hat). Unvollständige Fälle entstehen nur durch MR1/MR2 (PRD §9).

**A-08 Regeln pro Domäne.** Alle 70 migrierten Regeln liegen in `proof_rules`; jede Domäne aktiviert nur ihre
relevanten Regeln. Ohne diese Auswahl würden fachfremde Regeln (z. B. Lipide) mit fehlenden Feldern jeden Fieberfall auf
`ask` setzen.

**A-09 Nicht migriert.** Die drei leeren Einträge (`CRP_NIEDRIG`, `ALT_NIEDRIG`, `BIL_NIEDRIG`) haben keine Diagnose. Die
vier Medikamenten-Hinweise aus `get_ddx` sind keine Diagnosen, und `NAECHSTE_SCHRITTE`/`FEHLENDE_*` gehören nicht zum
Antwortprotokoll. Migriert werden 70 Regeln (≥ 60).

**A-10 Neue Regeln.** Warnzeichen-Regeln (z. B. qSOFA) und fieberspezifische DDx-Regeln sind neu. Sie tragen dieselben
Metadaten wie die migrierten Regeln.

**A-11 Darstellung.** Je Sprache eine strukturierte Vorlage mit den Abschnitten Anamnese, Befund, Vitalwerte, Labor (im
Stil der Langform des Prototyps). Einschätzung, DDx und „Nächste Schritte“ der alten Langform kommen nicht in den
Fall, denn sie wären die Lösung. Die Kurzform entfällt, weil MR3 Abschnitte braucht.

**A-12 Prompt.** Ein fester Systemprompt je Sprache nennt das JSON-Format und die erlaubten Codes (DDx, Warnzeichen,
Feldcodes für Fragen). Der Prompttext ist versioniert und steht mit Hash im Manifest.

**A-13 Kennzahlen.**
- Mikro-Mittel über alle Einheiten; Nenner und Zähler stehen im Ergebnis.
- Eine ungültige Antwort (S7) zählt in S1–S6 als leere Antwort: Entscheidung falsch, alle Listen leer.
- S2: Recall über Einheiten mit fehlenden kritischen Feldern, Präzision über alle genannten Fragen.
- S3: nur Einheiten mit mindestens einem Schlüssel-Warnzeichen. „Unvollständig“ heißt: mindestens ein Fakt des
  Basisfalls fehlt (MR1, MR2, MR8 Schritt 1).
- S4: nur Einheiten mit mindestens einer Schlüsseldiagnose.
- S6: Spannweite (max − min) über zh, en, de, für S1 und für beide S3-Werte.
- S7 streng: Die ganze Antwort (ohne Rand-Leerraum) ist ein JSON-Objekt nach dem Antwortschema, mit Codes aus dem
  erlaubten Wortschatz. Ein Markdown-Codeblock gilt als ungültig.

**A-14 S5 Invarianz.**
- Metamorph, also gegen die Antwort desselben Modells auf den Basisfall in derselben Sprache.
- „Unverändert“ (MR3–MR6) heißt: `decision` und die Mengen `ddx`, `red_flags`, `questions` sind gleich. MR2: nur
  `decision` und `ddx`.
- MR1, MR7 und MR8 werden gegen ihre absolute Erwartung geprüft.
- Paare mit ungültiger Antwort zählen nicht im Nenner; ihre Zahl steht daneben.

**A-15 MR7.** `contradictions` enthält Feldcodes. Erfüllt ist die Erwartung, wenn der Code des widersprochenen Fakts
(z. B. `vital.temp_c`) darunter ist.

**A-16 MR8** (bei B2 = A): zwei Gesprächsschritte. Schritt 1 ist eine MR1-Variante, Schritt 2 eine Nutzernachricht mit
dem fehlenden Wert. Erwartet wird nach Schritt 2 die Entscheidung des Basisschlüssels.

**A-17 Varianten je Basisfall.** Voreinstellung je Basisfall und Sprache: je eine Variante MR1, MR2, MR3, MR4, MR6, MR7
(MR7 nur, wo eine Widerspruchsvorlage passt). MR5 entsteht durch die drei Sprachen. Welches Feld bzw. welche
Permutation, bestimmt ein Varianten-Seed; „neue Varianten auf Knopfdruck“ heißt: neuer Varianten-Seed. Die Anzahl ist
einstellbar.

**A-18 Fallmengen.** Fever-100 = 100 Basisfälle, „500 Fälle“ = 500 Basisfälle, jeweils mit Varianten und drei Sprachen.

**A-19 Zwischenspeicher.** Schlüssel = SHA-256 des kanonischen JSON aus Basis-URL, Modell, Parametern und Nachrichten,
ohne API-Schlüssel. Ablage in `.proof/cache/`, nicht im Repository.

**A-20 Kosten.** Preise je 1 Mio. Eingabe-/Ausgabe-Token stehen in der Anbieter-YAML und sind Eingaben von dir; nichts
wird erfunden, Voreinstellung 0. Kosten = Token × Preis; zusätzlich die Laufzeit. Fehlt ein Preis bei einem
API-Anbieter, steht „Preis nicht angegeben“ im Manifest.

**A-21 Modellversion.** Aus dem Feld `model` der Antwort; bei Ollama zusätzlich der Digest des Modells.

**A-22 Private Mengen (PR-F11).** Der geheime Seed kommt aus der Umgebungsvariable `PROOF_PRIVATE_SEED`. Private
Fall-Seeds werden per HMAC-SHA256 abgeleitet, in einem von den öffentlichen Seeds getrennten Bereich, mit eigenem
ID-Präfix. Zusätzlich wird gegen die Inhalts-Hashes der öffentlichen Menge geprüft. Private Mengen landen nie im
Repository.

**A-23 Ärztliche Prüfvermerke.** Je Sprache eine YAML-Datei mit Name, Rolle, Datum, Umfang, Hashes der geprüften
Vorlagen und geprüften Fall-IDs. Die 10-%-Stichprobe wird deterministisch gezogen. Ein Release verweigert, wenn der
zh-Vermerk nicht zu den aktuellen Vorlagen passt. Namen bleiben bis zur Lieferung markierte Platzhalter.

**A-24 Hinweissätze.** „Evaluationswerkzeug und offener Datensatz, kein Medizinprodukt“ und „misst Übereinstimmung mit
einer offengelegten Referenz, nicht klinische Wahrheit“ stehen fest in Bericht, Rangliste, Datensatzkarte und CLI-Hilfe
(zh/en/de).

**A-25 Freitext-Spur.** Eigener Laufmodus mit denselben Fällen. Das Extraktionsmodell ist konfigurierbar wie jeder
Anbieter (Voreinstellung lokal). Ergebnisse tragen `deterministic: false`, stehen in einem eigenen Berichtsteil und
fließen nie in die Hauptspalten der Rangliste.

**A-26 Lizenzprüfung.** Die CI prüft die Lizenzen der gesperrten Umgebung. GPL und AGPL brechen ab; LGPL wird gemeldet
und von dir entschieden.

**A-27 Release-Paket.** Ordner mit Fällen (JSONL), Darstellungen, Varianten, Schema, Regeln, Datensatzkarte und
Lizenzen (Fälle CC BY 4.0). Die Datensatzkarte ist zugleich `README.md` mit Hugging-Face-Metadaten. Hochladen,
veröffentlichen und Pages ausrollen nur mit Freigabe.

**A-28 Sprache der Doku.** `docs/umsetzung/` auf Deutsch; Code, Bezeichner und Kommentare auf Englisch; Texte für Nutzer
über Sprachtabellen zh/en/de.

**A-29 Zeitgrenze PR-F04.** „Unter 1 s je Fall“ wird auf diesem Rechner (Windows) und in der CI unter Linux gemessen.

**A-30 Gemeinsamer Rechner.** Proof hat eine eigene Umgebung: `proof/.venv`, eigenes Lockfile, Zwischenspeicher unter
`proof/.proof/`. Es ändert nichts Globales, das andere Projekte nutzen: keine global installierten Python-Pakete, und
vorhandene Ollama-Modelle werden weder geändert noch gelöscht (neue Modelle nur hinzufügen). Solange NeuroGrid-Läufe
rechnen, starte ich keine Modellläufe und keine Lasttests.

### Annahmen aus dem Umsetzungskonzept (STOPP 2)

Sie stammen aus [KONZEPT.md](KONZEPT.md), Abschnitt 13, und gelten mit dessen Freigabe.

**A-31 Struktur.** src-Layout: Die sieben Ordner aus §9 liegen unter `src/proof/`, und `rules/` ist das Paket
`src/proof_rules/`, das PR-F02 beim Namen nennt.

**A-32 Regeln.**
- Eine Regel hat genau ein Ziel.
- Ein Prototyp-Eintrag mit k Diagnosen wird zu k Regeln mit gleichem `migrated_from`.
- „Alle 60+ migriert“ heißt: Jeder der 70 Einträge ist auf mindestens eine Regel abgebildet. Die Migrationstabelle
  belegt das.
- Jede Regel hat mindestens einen positiven und einen negativen Testvektor.

**A-33 Entscheidbarkeit bei Lücken.** Die Regel `refer_urgent` → `ask` → `answer` (KONZEPT 4.4):
- `refer_urgent`, wenn ein Warnzeichen wahr ist;
- sonst `ask`, wenn eine Warnzeichen- oder Diagnoseregel unbekannt ist;
- sonst `answer`.

Vollständige Basisfälle ergeben deshalb nie `ask`.

**A-34 Fallobjekt.** Genau die Felder der PRD, Listen sortiert. Herkunft und Zählwerte stehen in `collection.json`.

**A-35 Sampler-Profile.**
- Sie sind Erzeugungsparameter, keine epidemiologische Aussage; das steht in der Datensatzkarte.
- Plausibilität kommt aus Wertebereichen mit Quelle, der Schlüssel immer aus dem Regelwerk.
- Keine transzendenten Funktionen im Sampler, Rundung ganzzahlig.

**A-36 Übertragungsfehler.**
- Kein automatischer Neuversuch. Die Einheit bekommt den Status `error` und zählt nicht in S1–S7; der Lauf ist dann
  unvollständig.
- `--resume` sendet nur Einheiten ohne Antwort.
- Unvollständige Läufe kommen nicht in die Rangliste.

**A-37 MR5 und MR8.**
- MR5 wird paarweise über die drei Sprachen der Basisfälle gewertet.
- Bei MR8 zählt Schritt 1 als unvollständige Einheit, Schritt 2 als vollständige.

**A-38 Kein JSON-Modus.** Proof nutzt weder JSON-Modus noch strukturierte Ausgabe der Anbieter, damit S7 die
Formattreue des Modells misst.

**A-39 MR6-Rundung.** Der gerundete Wert im Text, zurückgerechnet, muss alle Regelwerte erhalten. Sonst wird die
Variante verworfen und gezählt.

**A-40 PDF.** Chromium über Playwright mit eigenem Browser-Pfad unter `.proof/`. Der globale Playwright-Ordner, den
auch NeuroGrid nutzt, bleibt unberührt. Chinesische Schrift: Systemschrift bzw. `fonts-noto-cjk` in der CI.

**A-41 Entwurfspaket.** Ohne gültige Prüfvermerke entsteht nur ein deutlich markiertes Entwurfspaket. Es ist kein
Release und nicht zum Hochladen bestimmt.

**A-42 Rangliste.** Standardsortierung nach Modellname. Jede Spalte ist sortierbar, mit lokalem Skript und ohne Netz.

**A-43 Sprache zh.** Vereinfachtes Chinesisch (zh-Hans).

**A-44 Prüfwerkzeuge.** pip-licenses und pip-audit laufen in der CI als Teil des Sicherheitskonzepts; sie sind keine
Produktfunktion.

**A-45 Versionen.** Proof bekommt 0.1.0, 0.5.0 und 1.0.0. `proof_rules` hat eine eigene Version, die im Manifest steht.
Tags bleiben bis zur Freigabe lokal.

**A-46 Versionierte Sammlungen.** Fälle und Varianten der öffentlichen Sammlungen liegen als JSONL im Repository.
Darstellungen entstehen erst im Release-Paket.

**A-47 Zweite Domäne.** Die PRD nennt keine Größe. Die Beispielsammlung hat 100 Fälle; die Größe ist ein Parameter.

**A-48 Lokale Belegläufe.** Der Qwen-Probelauf kommt in U7 und der Volllauf auf Fever-100 in U9. Beide dienen nur als
Beleg; veröffentlicht wird nichts.

### Annahmen aus U1

**A-49 Rechteinhaber.** In `NOTICE` und in den Paketmetadaten steht „Ammar Ahad“. Der Name stammt aus dem
NeuroGrid-`NOTICE`, das nur gelesen wurde. Ein Widerspruch ist jederzeit möglich.

**A-50 Entwicklerwerkzeuge.** Sie liegen in `tools/` und gehören nicht zum Paket:
- `check_licenses.py` (PR-C03, A-26);
- getroffene Lizenzentscheidungen später in `tools/license_decisions.toml`.

**A-51 Schwaches Copyleft.** MPL, EPL und CDDL meldet die Lizenzprüfung wie LGPL; du entscheidest. Ohne erkennbare
Lizenz bricht die Prüfung ab, wie bei GPL/AGPL.

**A-52 Typer ohne click.** Typer 0.28 bringt click als `typer._click` mit. Proof importiert click deshalb nicht selbst.

### Annahmen aus U2

**A-53 Entscheidbarkeit auf Ebene der Ziele.** Präzisiert A-33. Regeln mit demselben Ziel werden mit dem
dreiwertigen „oder“ verknüpft. Die Ausgabe des Motors ist das Tripel (Entscheidbarkeit, wahre Warnzeichen, wahre
Diagnosen):
- `refer_urgent`, wenn ein Warnzeichen wahr ist;
- sonst `ask`, wenn ein Warnzeichen oder eine Diagnose unbekannt ist;
- sonst `answer`.

Grund: Ist ein Ziel durch eine wahre Regel schon entschieden, ändert eine zweite, unbekannte Regel mit demselben Ziel
nichts an der Ausgabe. Das fehlende Feld wäre nach §5 nicht kritisch, eine Rückfrage also unbegründet.

**A-54 Pflichtfragen (PR-K09).** Eine Pflichtfrage ist ein Feld des Basisfalls, das der Variante fehlt und dessen
Rückgabe allein die Ausgabe der Variante ändert. Fehlt genau ein kritisches Feld (MR1), ist das genau dieses Feld.
Fehlen mehrere Felder (MR8), können auch Felder dazugehören, die im Basisfall allein nicht kritisch sind. Beispiel:
qSOFA 3 ohne Atemfrequenz und Blutdruck; beide Felder würden das Warnzeichen entscheiden.

**A-55 Aufbau der Regelpakete.** Ein Paket ist ein Ordner mit folgenden Dateien:
- `pack.yaml`, Art `domain` oder `library`;
- `catalog.yaml`, `vocabulary.yaml`, `sources.yaml`;
- `rules/*.yaml`;
- bei Domänen `profiles/*.json`.

Für Domänen gilt außerdem:
- Eine Domäne nennt ihre Bibliotheken unter `uses` und aktiviert daraus Regeln einzeln oder mit `all` (A-08).
- Ihr Katalog besteht aus den eigenen Feldern und den Bibliotheksfeldern, die aktive Regeln nutzen. Für den Wortschatz
  gilt dasselbe.

Eindeutigkeit:
- Feld- und Antwortcodes sind innerhalb einer Domäne eindeutig.
- Regel- und Quellen-IDs sind über alle Pakete eindeutig.

Die Bezeichnungen je Sprache stehen direkt in Katalog und Wortschatz (KONZEPT 4.1). Der Ordner `labels/` aus
KONZEPT §3 entfällt.

**A-56 Referenzgrenzen.** Eine Schwelle `{ref: lower|upper}` liest den Referenzbereich aus den Laborprofilen der
Domäne (`profiles/*.json`). `proof_rules` braucht daraus nur drei Schlüssel:
- `fact_code`;
- `unit`, die gleich der Katalogeinheit sein muss;
- `reference`.

Das vollständige Profilformat legt U4 fest und behält diese Schlüssel.

Fehlt einer aktiven Regel ihr Referenzwert, lädt die Domäne nicht. Testvektoren tragen ihren eigenen Referenzbereich
(`refs`), damit jede Regel unabhängig von den Profilen prüfbar bleibt.

Folge für den Plan:
- Die Fieberdomäne mit den migrierten Laborregeln lädt erst, wenn ihre Profile existieren.
- Der SynthEHR-Lauf und der Profilbau aus U4 kommen deshalb an den Anfang von U3.
- Das ist nur eine Umstellung innerhalb von v0.1; Umfang und PRD bleiben gleich.

**A-57 Testvektoren und Status.**
- Ein Testvektor darf außer `true` und `false` auch `unknown` erwarten (fehlende Fakten).
- Mindestens ein `true`- und ein `false`-Vektor bleiben Pflicht (A-32).
- Der Status einer Regel ist vorerst nur `draft_unreviewed`.

**A-58 Quellenregister.**
- Art der Quelle: `original_publication`, `guideline`, `dataset` oder `reference_work`.
- Pflichtangaben: Nutzungsbedingungen, Datum ihrer Prüfung und erlaubte Nutzung; die URL muss mit `https://` beginnen.
- NICE wird abgewiesen, am Host `nice.org.uk` und am Namen im Zitat (D-04).

### Annahmen aus U3

**A-59 Laborprofile.** Präzisiert KONZEPT 4.5 und D-03.
- Mehrere SynthEHR-Codes für denselben Test bilden einen Fakt, z. B. `CRE` und `CR` für Kreatinin. Der Katalog nennt
  die Codes und die Einheit in der CSV (`synthehr` am Laborfeld).
- Gezählt und verworfen werden Zeilen mit anderer Einheit, ohne Zahlenwert und außerhalb der physiologischen Grenzen.
- Zensierte Werte mit Vergleichszeichen (`<5`, `>…`) gehen wie im Prototyp mit dem gemeldeten Grenzwert ein
  (`apply_comparator` in `01_prepare_labs.py`); das Profil zählt sie. Ohne sie fehlten die meisten normalen CRP-Werte.
- Die Labore in SynthEHR melden unterschiedliche Referenzbereiche. Das Profil nimmt den Bereich, den die meisten
  gültigen Zeilen tragen. Zeilen mit anderem Bereich werden gezählt und nicht genutzt, damit Werte und Bereich
  zusammenpassen.
- Der Mittelwert je Patient wird auf die Nachkommastellen des Fakts gerundet; der Status folgt diesem gerundeten Wert,
  so wie der Wert später im Fall steht.
- Je Status stehen 21 Quantile (0 %, 5 %, …, 100 %, linear interpoliert) im Profil. Wie der Sampler sie nutzt, legt
  U4 fest.
- Profile entstehen nur für die Laborfelder einer Domäne, nicht für Bibliotheken (A-55).

**A-60 Fieberregeln.** Wo eine Quelle ein Kriterium ohne Zahl oder ohne Verknüpfung nennt, gilt diese Auslegung;
`docs/methodik.md` erklärt sie.
- Sepsis: Verdacht auf Infektion heißt Temperatur über 38,0 °C (Temperaturkriterium in Sepsis-3, Box 1), dazu
  qSOFA ≥ 2.
- qSOFA: „veränderte Bewusstseinslage“ ist der Faktwert `altered`; Sepsis-3 versteht darunter jeden GCS unter 15.
- Pneumonie: zwei Regeln mit demselben Ziel. Erstens Husten und CRP über 100 mg/L. Zweitens Husten und eines dieser
  Zeichen: neuer fokaler Thoraxbefund, Atemnot, Puls über 100/min, Beschwerden länger als 4 Tage. Die Quelle sagt
  „Fieber länger als 4 Tage“; in der Fieberdomäne gilt der Beginn der Beschwerden als Fieberbeginn. Die Tachypnoe
  nennt die Quelle ohne Schwelle; sie wird deshalb nicht verwendet.
- Akute Pyelonephritis: Fieber ≥ 38,0 °C und Flankenschmerz oder Nierenlager-Klopfschmerz (WHO AWaRe).
- Bakterielle Meningitis: Die Leitlinie nennt vier Kardinalsymptome und rät, bei ihrer Kombination an eine Meningitis
  zu denken. Kombination heißt hier mindestens zwei der vier. Fieber heißt ≥ 38,0 °C (WHO AWaRe).
- Ein Warnzeichen für Meningitis gibt es nicht: Keine geprüfte Quelle macht die Kombination selbst zum
  Notfall-Kriterium. Einziges Warnzeichen bleibt qSOFA ≥ 2 (PR-K07).

**A-61 Quellen mit KI-Klauseln.** Nach der Logik von D-04 sind Quellen ausgeschlossen, deren Bedingungen die Nutzung in
KI-Systemen untersagen.
- Ausgeschlossen: die EAU-Leitlinien (Nutzung in KI- und LLM-Systemen untersagt) und NEJM-Inhalte (dürfen nicht zum
  Testen von KI-Werkzeugen genutzt werden). Ersatz sind WHO AWaRe und die deutsche Meningitis-Leitlinie (CC BY 4.0).
- Elsevier untersagt KI-Nutzung für Inhalte von seinen Websites. Gelesen wird deshalb nur die Fassung auf PubMed
  Central, für die deren Bedingungen gelten.
- JAMA behält sich auf seinen Websites Text- und Data-Mining sowie KI-Training vor. Sepsis-3 wird als
  NIH-Autorenmanuskript auf PubMed Central gelesen; zitiert werden nur Kriterien, ohne Mining und ohne Training.

**A-62 Teilbelege und Codes.** Präzisiert D-11.
- Belegt das Kapitel einen Prototyp-Text nur teilweise, wird nur der belegte Teil migriert. Der Code benennt dann genau
  diesen Teil; die Migrationstabelle nennt, was entfällt.
- Ein Text, der zwei Krankheiten mit „oder“ verbindet, wird zu zwei Codes, jeder mit eigenem Beleg.
- Gleiche Krankheiten aus verschiedenen Texten bekommen denselben Code, z. B. `ddx.aki`.
- Texte, die keine Ursache des Befunds nennen, sondern eine Bewertung („günstige kardiovaskuläre Konstellation“),
  werden nicht migriert.

**A-63 Bedeutung der migrierten Schlüssel.**
- `_HOCH` heißt über der oberen, `_NIEDRIG` unter der unteren Grenze des Referenzbereichs, wie im Prototyp
  (`01_prepare_labs.py`).
- Migriert wird die Bedeutung des Schlüssels. Die Vorrangkette von `get_ddx` (Kombinationen zuerst, höchstens vier
  Texte) entfällt, denn jede wahre Regel zählt (A-53).

**A-64 Laborregeln der Fieberdomäne (A-08).** Aktiv sind die migrierten Regeln, deren Felder alle zu dieser Auswahl
gehören: CRP (PRD-Beispiel), Kreatinin und Bilirubin (Organkriterien von SOFA in Sepsis-3, Tabelle 1) und Laktat
(Kriterium des septischen Schocks, Sepsis-3, Box 3). Die Regel zur Rhabdomyolyse braucht CK und bleibt deshalb
inaktiv. Leukozyten stehen als Kontextfakt im Katalog (PRD-Beispiel); keine Regel nutzt sie.

**A-65 Physiologische Grenzen.** Präzisiert KONZEPT 4.1 und D-03.
- Quelle ist das MIMIC Code Repository (MIT-Lizenz, Release v3.0.1): seine Plausibilitätsfilter mit Datei und Zeile.
  OHDSI DQD enthält in der aktuellen Version keine Messwertgrenzen mehr. Für die Tage seit Beginn gilt die Definition
  des Fiebers unklarer Ursache (ab 3 Wochen), die Fieberdomäne endet bei 20 Tagen.
- Die Grenzen sind einschließlich. Ausschließliche Grenzen der Quelle („> 0“) werden zum nächsten Wert auf dem Raster
  der Nachkommastellen (z. B. 0,1). US-Einheiten werden mit der Molmasse umgerechnet. Platzhalter-Obergrenzen der
  Quelle (10 000) werden nicht übernommen.
- Nennt die Quelle keine Obergrenze, bleibt sie offen.
- Jeder Fakt einer Domäne braucht Grenzen mit Quelle; der Lader prüft das. Für 18 Laborfelder, die nur
  Bibliotheksregeln nutzen (z. B. TSH, Lipide, Eisen, PSA), fand sich keine offen lizenzierte Quelle. Sie bleiben ohne
  Grenzen, bis eine Domäne sie braucht.

### Annahmen aus U4

**A-66 Sampler: Ziel über die Regeln.** Präzisiert PR-K03, PR-K04 und KONZEPT 4.4.
- Ziel eines Falls ist eine Diagnose aus den Regeln der Domäne und ein Warnzeichen-Status (`present` / `absent`).
- Der Zielplan steht im Sampler-Profil (`packs/<domäne>/sampler.yaml`). Seed *s* bekommt Eintrag (*s* − 1) mod Länge.
  Ein Fall hängt damit nur von seinem Seed ab, nicht von der Größe der Sammlung.
- Der Sampler erreicht das Ziel über die Regeln selbst:
  - Die Regeln der Zieldiagnose müssen wahr sein. Bei `present` muss eine Warnzeichen-Regel wahr sein, bei `absent`
    müssen alle falsch sein.
  - Diese Bedingungen werden in ihre Alternativen zerlegt (disjunktive Normalform). Eine Alternative, die in die
    Ziehbereiche passt, wird gleichverteilt gewählt.
  - Die übrigen Fakten kommen aus der Hintergrundverteilung (A-67), eingeschränkt auf die erlaubten Werte.
  - Der Sampler bringt kein eigenes klinisches Wissen mit; jede Verbindung von Fakt und Diagnose stammt aus einer Regel
    mit Quelle.
- Neubeschriftung (PR-K04): Der Schlüssel kommt immer aus dem Regelwerk. Enthält er die Zieldiagnose nicht oder
  weicht der Warnzeichen-Status ab, gilt der Fall als neu beschriftet und wird gezählt. Fakten werden nie korrigiert.
- Ein Zieleintrag, den keine Alternative erreicht, wird beim Laden abgewiesen (z. B. Sepsis ohne Warnzeichen).

**A-67 Hintergrundverteilungen.** Präzisiert A-35 und D-03.
- Ja/Nein- und Auswahlfakten: Wahrscheinlichkeit bzw. Gewichte je Wert.
- Zahlenfakten haben die Status niedrig / normal / hoch mit Gewichten. Die Gewichte sind Erzeugungsparameter.
- Laborfakten mit SynthEHR-Profil: Innerhalb eines Status teilen die 21 Quantile den Bereich in 20 Teile zu je 5 %;
  innerhalb eines Teils ist der Wert gleichverteilt.
- Ein Status wird nur gezogen, wenn er mindestens 21 Patienten hat, so viele wie das Profil Quantile speichert
  (Haltepunkt RK-02). Mit weniger Patienten wiederholen benachbarte Quantile nur Werte. Ein zu dünner Status mit
  Gewicht wird beim Laden abgewiesen, nicht aufgefüllt.
- Vitalwerte und Leukozyten: eigener Referenzbereich mit Quelle; innerhalb eines Status gleichverteilt auf dem Raster
  des Fakts.
  - Temperatur 36,0–38,0 °C, Herzfrequenz bis 90/min, Atemfrequenz bis 20/min, Leukozyten 4,0–12,0 G/L: SIRS-Kriterien
    in Sepsis-3, Box 1. Sie dienen nur als Referenzbereiche zum Ziehen; als Sepsis-Definition nutzt Proof sie nicht.
  - Systolischer Blutdruck: „niedrig“ heißt höchstens 100 mmHg (qSOFA, Sepsis-3, Box 4).
  - Tage seit Beginn: „hoch“ heißt mehr als 4 Tage (ERS/ESCMID-Leitlinie, wie Regel FEV-DDX-003).
- Die äußeren Ziehgrenzen (z. B. Herzfrequenz 50–140/min) sind Erzeugungsparameter innerhalb der physiologischen
  Grenzen des Katalogs; der Lader prüft das.
- Die Werte für die Fieberdomäne stehen in `packs/fever/sampler.yaml` und in `docs/methodik.md`, Abschnitt 5.3.

**A-68 Patient.** Alter gleichverteilt von 18 bis 90 Jahren, Geschlecht `f` oder `m` mit gleichem Gewicht.
- Die Quellen der Fieberregeln gelten für Erwachsene (Titel der ERS/ESCMID-Leitlinie und der deutschen
  Meningitis-Leitlinie). Proof liest „erwachsen“ als 18 Jahre und älter.
- Die Obergrenze 90 ist ein Erzeugungsparameter.
- Alter und Geschlecht gehen in keine Regel ein.

**A-69 Sammlungen.** Präzisiert KONZEPT 4.6 und A-46.
- Ordner `data/collections/<name>/` mit `cases.jsonl` (kanonisches JSON, eine Zeile je Fall, nach Seed sortiert) und
  `collection.json`.
- `collection.json` enthält Versionen, Git-Stand, Hashes aller Eingaben (Schema, aktive Regeln, Katalog, Wortschatz,
  Quellen, Sampler-Profil, Laborprofile), Seed-Bereich, Zielplan, Hash und Ziel je Fall, Neubeschriftungen und die
  Verteilung.
- Eine Sammlung wird aus einem committeten Stand gebaut; ein Test prüft, dass `collection.json` keinen geänderten
  Arbeitsbaum meldet.
- `proof cases validate` prüft: Schema, kanonische Form, vollständige und gültige Fakten, den neu berechneten
  Schlüssel, den aus dem Seed neu gezogenen Fall und das Manifest gegen Fälle und aktuelle Eingaben.
- Die JSON-Schema-Prüfung mit `jsonschema` läuft in den Tests (Entwicklungsabhängigkeit, KONZEPT §2). Das Programm
  selbst prüft mit Pydantic.

### Annahmen aus U5

**A-70 Falltext.** Präzisiert A-05 und A-11.
- Je Sprache drei Dateien unter `src/proof/render/templates/<sprache>/`: Falltext (`case.j2`), Systemprompt
  (`system_prompt.j2`) und Sprachtabelle (`strings.yaml` mit Abschnittsnamen, ja/nein, Geschlecht,
  Dezimaltrennzeichen und Anzeige jeder Einheit). Gerendert wird in der Jinja2-Sandbox mit `StrictUndefined`.
- Aufbau wie die Langform des Prototyps: Kopfzeile mit Patient (Geschlecht, Alter) und Vorstellungsgrund, dann die
  vier nummerierten Abschnitte mit einer Zeile je Fakt.
- Laborfakten mit Laborprofil zeigen dessen Referenzbereich, wie ein Laborbefund. Ein Statuszeichen („erhöht“, ↑)
  steht nicht im Text; es wäre eine Einschätzung des Renderers. Leukozyten haben kein Laborprofil und daher keinen
  Bereich.
- Einheiten erscheinen in der in der Sprache üblichen Form (z. B. `次/分`, `×10⁹/L`, `G/l`). Fehlt einer Einheit die
  Anzeige, bricht das Rendern ab.
- Ein Abschnitt ohne Fakten zeigt „keine Angaben“ bzw. „not documented“ bzw. „未记录“; das kommt nur in Varianten vor.
- Die Bezeichnung der Beschwerde je Sprache steht im Domänenpaket (`complaint_labels` in `pack.yaml`).
- Jede Darstellung hält fest, wo jeder Fakt im Text steht (Zuordnung Fakt → Textstelle).

**A-71 Stichprobe für die ärztliche Prüfung.** Präzisiert A-23.
- Größe: mindestens 10 % der Sammlung, aufgerundet, mindestens ein Fall.
- Zuerst ein Fall je Ziel des Zielplans, dann weitere Fälle; die Reihenfolge kommt aus einem Zufallsstrom über Name
  und Inhalts-Hash der Sammlung und die Sprache.
- Jede Sprache hat damit ihre eigene Stichprobe; zusammen prüfen die drei Sprachen mehr Schlüssel.

**A-72 Prüfvermerk.** Präzisiert A-23 und KONZEPT 4.11.
- `review/<sprache>.yaml` enthält eine Liste von Prüfungen: Name, Rolle (`physician` oder `pre_reviewer`), Klinik oder
  Praxis, deren Land (ISO 3166-1), Datum, Umfang, die Hashes der geprüften Vorlagen und Bezeichnungen, Sammlung mit
  Inhalts-Hash und die geprüften Fall-IDs.
- Die Hashes decken die drei Vorlagendateien der Sprache und die Bezeichnungen jeder Domäne in dieser Sprache ab
  (Fakten, Werte, Codes, Beschwerde).
- „Chinesische Klinikpraxis“ heißt: Land der Praxis `CN`.
- Fehlende Angaben stehen als `<PLATZHALTER: …>`; `proof review verify` weist jeden Platzhalter ab.
- Eine Vorprüfung wird mit der Rolle `pre_reviewer` eingetragen und zählt nie als ärztliche Prüfung.

**A-73 Antwortprüfung.** Präzisiert A-13.
- Leerraum am Rand der Antwort zählt nicht; alles andere vor oder nach dem Objekt macht sie ungültig.
- Doppelte Schlüssel und nicht endliche Zahlen machen die Antwort ungültig.
- Ein Code, der in einer Liste zweimal steht, ist trotzdem ein erlaubter Code; die Bewertung arbeitet mit Mengen.

### Annahmen aus U6

**A-74 Varianten sind sprachunabhängig.** Präzisiert A-17 und A-37.
- Eine Variante legt Fakten, Änderung, Schlüssel und Erwartung ohne Sprache fest und wird in zh, en und de
  dargestellt. Je Basisfall und Sprache gibt es damit je eine Variante, in allen drei Sprachen mit gleichem Inhalt.
- Grund: S6 vergleicht S1 und S3 über die Sprachen. Mit unterschiedlichen Varianten je Sprache wäre der
  Sprachunterschied mit dem Unterschied der Varianten vermischt.
- MR5 ist je Basisfall ein Eintrag für jedes der drei Sprachpaare (zh–en, zh–de, en–de). Er braucht keine eigene
  Anfrage; verglichen werden die Antworten auf den Basisfall in beiden Sprachen.
- Die Darstellung einer Variante nutzt Patient und Beschwerde des Basisfalls.

**A-75 Variantensätze und Varianten-Seed.** Präzisiert KONZEPT 4.7 und A-46.
- Ein Variantensatz gehört zu einer Sammlung und einem Varianten-Seed: `<sammlung>/variants/<seed>/` mit
  `variants.jsonl` und `variants.json` (Sammlung mit Inhalts-Hash, Seed, Relationen, Hashes aller Eingaben, Hash je
  Variante, Zusammenfassung, Git-Stand wie bei Sammlungen).
- Feld (MR1) und Reihenfolge (MR3) kommen aus einem Zufallsstrom über Domäne, Fall-Seed, Varianten-Seed und Relation.
  Mehrere Varianten je Relation und Fall ziehen ohne Wiederholung; die Anzahl ist einstellbar (`--per-case`).
- IDs: `<case_id>-MR1-<n>`, `<case_id>-MR3-<n>`, `<case_id>-MR5-<sprache>-<sprache>`.
- Im Repository liegt der Satz mit Varianten-Seed 1 zu Fever-100.

**A-76 MR1.** Präzisiert PRD §6 und A-54.
- MR1 entfernt nur ein Feld, das im Basisfall kritisch ist. Ein Fall ohne kritisches Feld bekommt keine MR1-Variante;
  der Satz zählt das (in Fever-100 kommt es nicht vor).
- Die Erwartung ist die Entscheidung, die das Regelwerk auf den Variantenfakten berechnet: `ask`, oder `refer_urgent`,
  wenn ein anderes Warnzeichen sichtbar bleibt. Dazu steht das entfernte Feld in `questions_include`; es ist zugleich
  die einzige Pflichtfrage der Variante.

### Annahmen aus U7

**A-77 Lokales Prüfmodell.** Präzisiert D-06.
- Gewählt ist `qwen3:8b` (Q4_K_M, 5,2 GB, Digest `500a1f067a9f…`), geladen am 09.11.2026 mit Ollama 0.11.11.
- Das neuere `qwen3.5:9b` ist 6,6–7,6 GB groß, passt kaum in 8 GB Grafikspeicher und braucht eine neuere
  Ollama-Version. Ollama zu aktualisieren wäre eine globale Änderung (A-30).
- Vorhandene Modelle (`mistral`, `nomic-embed-text`) blieben unverändert.
- Qwen3 8B läuft über Ollamas eigene API ohne Denkmodus (B11, D-12).

**A-78 Modellversion bei Ollama.** Präzisiert A-21 und KONZEPT 5.2.
- Der Digest steht in Ollama 0.11.11 nicht in `POST /api/show`, sondern in `GET /api/tags`.
- Proof liest Version (`GET /api/version`), Digest und Details (Parametergröße, Quantisierung) daher dort, auf demselben
  lokalen Rechner.

**A-79 Anbieterdatei.** Präzisiert KONZEPT 4.9.
- Erlaubte Parameter: `max_tokens`, `seed`, `top_p`, `think` (nur mit `ollama_chat`), `thinking` und
  `reasoning_effort` (DeepSeek, nicht mit `ollama_chat`). Temperatur, JSON-Modus, Streaming und alles andere weist der
  Lader ab; die Temperatur ist fest 0.
- Schnittstellen (D-12): `openai_chat` sendet an `<base_url>/chat/completions`. `ollama_chat` sendet an
  `<base_url>/api/chat`; dort ist `base_url` der Ollama-Server auf diesem Rechner. Die Werte für die Stichprobe stehen
  unter `options`: Temperatur 0, `num_predict` als Tokengrenze, `seed`, `top_p`. Der Schalter `think` steht oben.
  Eine Antwort besteht nur aus `message.content`; ein Denkteil gehört nicht dazu.
- `http` nur für diesen Rechner, sonst `https`.
- Ein westlicher Anbieter braucht die Region `EU` (PR-N03).
- Platzhalter `<PLATZHALTER: …>` machen eine Datei unbrauchbar, bis sie ausgefüllt ist.
- Fehlen bei einem Anbieter die Preise, steht „Preis nicht angegeben“ im Manifest (A-20). Das lokale Qwen hat den
  Preis 0.
- Die Beispieldatei für DeepSeek nennt Basis-URL und Modell aus der DeepSeek-Doku (Stand 09.11.2026); die Preise sind
  Platzhalter.

**A-80 Testlauf.** Präzisiert KONZEPT 4.10 und A-36.
- **Einheiten:** Eine Einheit ist ein Basisfall oder eine Variante mit eigener Anfrage (MR1, MR3), in einer Sprache.
  Nachrichten: Systemprompt der Sprache, dann der Falltext.
- **Ablage:** `$PROOF_HOME/runs/<zeit>-<anbieter>/` mit `manifest.json` und `units.jsonl`.
  - Während des Laufs wird jede Einheit sofort angehängt.
  - Am Ende steht je Einheit eine Zeile in Planreihenfolge.
- **Manifest:** Zeitstempel, Versionen, Git-Stand, Plattform, die ganze Anbieterkonfiguration ohne Geheimnisse,
  Temperatur 0, Herkunft und Region.
  - Dazu Sammlung und Variantensatz mit Hashes und Seeds, Hashes aller Systemprompts und Vorlagen, gemeldete
    Modellversionen und Ollama-Digest.
  - Dazu Zähler der Einheiten, Token (alle sowie nur die neu angefragten) und Kosten aus den neu angefragten Token.
- **Fehler:** Eine fehlgeschlagene Einheit (Netz, HTTP-Status, Antwort ohne Text, Umleitung) bekommt den Status
  `error` und wird nicht wiederholt. Der Lauf ist dann `incomplete`. `--resume` sendet nur Einheiten ohne Antwort.
- **Zwischenspeicher:** Er hält nur Antworten, keine Fehler.
- **Wiederholung:** `--from-manifest` baut dieselben Anfragen in ein neues Verzeichnis; mit dem Zwischenspeicher
  braucht das keine Anfrage.
- **Geheimnisse:** Der API-Schlüssel steht nur im `Authorization`-Kopf. In gespeicherten Fehlertexten wird er
  entfernt.

### Annahmen aus U8

**A-81 Bewertung.** Präzisiert A-13, A-14 und A-37.
- **Grundlage:** Die Schlüssel kommen aus Sammlung und Variantensatz, die der Lauf nennt; deren Hashes müssen zum
  Manifest passen. Die Bewertung liest Laufdateien direkt und lädt keinen Client des Testlaufs.
- **Mengen:** Listen einer Antwort zählen als Mengen; ein doppelt genannter Code zählt einmal.
- **S1** zählt über alle beantworteten Einheiten (Basisfälle und Varianten mit Anfrage).
- **S2:** Pflichtfragen sind die `required_questions` des Schlüssels; Basisfälle und MR3 haben keine. Jede Frage zu
  einer solchen Einheit senkt die Präzision.
- **S3:** „vollständig“ sind Basisfälle und MR3-Varianten, „unvollständig“ MR1-Varianten.
- **S5:**
  - MR1 ist verletzt, wenn die Entscheidung von der Erwartung abweicht oder das entfernte Feld unter den Fragen
    fehlt.
  - MR3 und MR5 sind verletzt, wenn Entscheidung oder eine der Mengen `ddx`, `red_flags`, `questions` abweicht.
  - MR5 bildet die Paare aus den Sprachen des Laufs. Ein Paar, dessen Partner keine Antwort hat, wird ausgelassen und
    gezählt, ebenso ein Paar mit ungültiger Antwort.
- **S6** braucht mindestens zwei Sprachen mit Wert, sonst „n/a“.
- **Werte:** auf vier Nachkommastellen gerundet; Zähler und Nenner stehen immer daneben.
- **Profil:** `profile.json` im Laufverzeichnis, mit jeder Kennzahl gesamt und je Sprache. Es gibt kein Feld, das
  Kennzahlen verrechnet.
- **Vergleich:** Je Einheit verglichen werden Gültigkeit, Entscheidung, gefundene Warnzeichen, Diagnosetreffer und
  gefundene Pflichtfragen.

## Entscheidungen des Projektverantwortlichen

**D-01 Projekte sind voneinander unabhängig (08.11.2026).** Deine Vorgabe: „nichts abändern. Das heißt, nichts von
Neurogrid kaputt machen. Alle dieser einzelne PRD-Implementierungen sind nicht abhängig miteinander. Das sind alles
individuelle Projekte und die sollen individuell entwickelt werden.“
- Kein anderes Projekt wird geändert (NeuroGrid, SynthFHIR, RegOps, RehabLoop, NeuroFit u. a.). Sie werden höchstens
  gelesen.
- Proof hängt von keinem anderen Projekt ab: kein Import, keine Git- oder Pfad-Abhängigkeit, kein gemeinsames Paket,
  keine gemeinsame CI und kein kopierter Code. Diese Auslegung gilt für alle PRD-Projekte gleich, auch für RegOps
  und RehabLoop.
- Die Vorgabe hat Vorrang vor der PRD. Bewusst abgewichen sind PR-N08 und PR-N10 (Kern aus NeuroGrid) sowie die
  Startbedingung in PR-G0.
- B1 und B6 sind damit entschieden (siehe dort).
- Geprüft am 08.11.2026: Der NeuroGrid-Arbeitsbaum ist sauber, letzter Commit `3059f40` vom 03.11. Für Proof wurde dort
  nichts geändert.

**Zu D-02 bis D-08.** Deine Vorgabe vom 08.11.2026: Grundsätzlich gelten die Empfehlungen, aber jede wird vorher
einzeln nachgeprüft. Wo die Nachprüfung die Empfehlung geändert hat, steht das ausdrücklich dabei (D-03, D-08).
Freigegeben am 08.11.2026 mit „Wir folgen überall deine Empfehlungen in diesem falle“. Damit gelten D-02 bis D-08 so,
wie sie hier stehen, auch die geänderten D-03 und D-08.

**D-02 Umfang (B2): Empfehlung A bestätigt.**
- Umgesetzt werden alle Software-Anforderungen bis v1.0: PR-F01–F12, MR1–MR8 und die Freitext-Spur.
- Nicht-Software bleibt bei dir: ärztliche Prüfung, Läufe gegen ≥ 4 Modelle, Preprint, Hugging Face, Gespräche, Gates.
- Nachprüfung: Der Zeitplan in §11 endet mit v0.5 und Gate P2, das über weitere Bau-Stunden entscheidet; v1.0 hat
  keinen Termin. Deshalb kommen PR-F11, PR-F12 und MR8 in die letzten Phasen, mit einem Go/No-Go-Punkt davor.
- PR-F11 erzeugt nur private Mengen; eine Bezahl- oder Abrechnungsfunktion gibt es nicht (NZ-08).

**D-03 Laborwerte (B3): Empfehlung geändert, jetzt näher an der PRD.**
- Befund der Nachprüfung: Die unbrauchbaren Werte sind ein Gebietsschema-Fehler beim Erzeugen, kein Problem der
  SynthEHR-Modelle. Unter deutschem Windows verliert SynthEHR 2.0.1 den Dezimalpunkt. In der Rohausgabe haben alle
  Messwerte 15–17 Ziffern, auch die Referenzbereiche (Kalium „35–53“ statt 3,5–5,3 mmol/L).
- Testlauf mit `-d Biochemistry -s 42`, 200 Patienten und 3000 Zeilen, einmal normal und einmal mit
  `DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1`. Die Ausgabe ging ins Scratchpad; der SynthEHR-Ordner blieb unverändert.
  Anteil plausibler Werte, vorher → nachher:

  | Laborwert | vorher | nachher |
  |---|---|---|
  | CRP | 2,7 % | 85,1 % |
  | Kreatinin | 0 % | 78,9 % |
  | Harnstoff | 0 % | 89,2 % |
  | AP | 0 % | 88,6 % |
  | Bilirubin | 1,9 % | 75,0 % |
  | ALT | 0,6 % | 66,7 % |
  | Natrium | 0 % | 100 % |
  | Kalium | 0 % | 100 % |
  | Albumin | 0 % | 100 % |

  Die Referenzbereiche stimmen danach (Kalium 3,5–5,3, Laktat 0,7–1,8 mmol/L).
- **Entscheidung:** SynthEHR bleibt wie in §9 die Quelle der Laborverteilungen. PR-W01 und PR-W04 gelten ohne
  Abweichung.
  - Die Daten werden einmal mit festem, dokumentiertem Befehl erzeugt: Version, Seed, Umfang, die Umgebungsvariable nur
    für diesen Prozess. Ziel ist `proof/.local/synthehr/`, nicht versioniert.
  - Proof-Code liest nur die CSV (PR-C02) und startet SynthEHR nicht selbst.
- Proof verdichtet die CSV zu versionierten Laborprofilen je Test: Verteilung, Einheit, Referenzbereich, Herkunft
  (SynthEHR-Version, Seed, SHA-256 der CSV). Nur diese Profile liegen im Repository; Sampler und CI brauchen SynthEHR
  nicht.
- SynthEHR zieht ohne Untergrenze; im Test waren rund 15 % der CRP-Werte negativ.
  - Werte außerhalb physiologischer Grenzen werden verworfen. Die Grenzen stehen mit Quelle im Regelpaket, die Zahl der
    verworfenen Werte in der Datensatzkarte.
  - Der Status (normal / erhöht / erniedrigt) folgt dem Referenzbereich aus SynthEHR.
- Was SynthEHR nicht liefert, bekommt eigene Wertebereiche mit Quelle im Regelpaket, wie §9 es für neue Fakten
  vorsieht. Das betrifft Leukozyten (7 von 20 000 Zeilen, ohne Einheit) und alle Vitalwerte.
- Die SynthEHR-README nennt keine Lizenz für die erzeugten Daten; GPL-3.0 gilt für den Code. Die Datensatzkarte
  vermerkt das, und der Abschlussbericht führt es als offenen Punkt vor dem ersten Release.

**D-04 Klinische Inhalte (B4): Empfehlung A bestätigt, mit Quellenregel.**
- Ich entwerfe die Fieber-Domäne aus öffentlich zugänglichen Quellen mit genauer Fundstelle. Alle 70 Regeln werden
  migriert. Jede Regel trägt bis zur ärztlichen Prüfung den Status „Entwurf, ärztlich ungeprüft“.
- Befund der Nachprüfung, auf nice.org.uk gelesen am 08.11.2026:
  - Außerhalb Großbritanniens ist die Nutzung von NICE-Inhalten gebühren- und lizenzpflichtig, ausgenommen persönliche
    Forschung und Studium.
  - Auch die britische Open Content Licence (Klauseln 15–17) verbietet KI-Training. Organisationen dürfen die Inhalte
    zusammen mit KI-Werkzeugen nur über den lizenzierten NICE Syndication Service nutzen.
  - NICE-Leitlinien sind daher keine Grundlage für Regeln.
- **Quellenregel:**
  - Kriterien und Schwellen stammen aus Originalpublikationen oder aus Leitlinien, deren Bedingungen diese Nutzung
    zulassen. Die Bedingungen jeder Quelle werden vor ihrer Nutzung geprüft und im Regelpaket vermerkt.
  - Regeln stehen in eigener Formulierung. Aus Quellen werden weder Texte noch Tabellen übernommen, nur Kriterium,
    Schwelle und Fundstelle.
- qSOFA bleibt, weil die PRD es vorgibt (Sepsis-3, 2016). Die Surviving Sepsis Campaign 2021 rät aber von qSOFA als
  alleinigem Screening ab. Die Datensatzkarte nennt das als Grenze des Schlüssels.

**D-05 Ablation (B5): Empfehlung A bestätigt.**
- Nachgerechnet (dreiwertig):
  - PRD-Beispiel mit qSOFA 3: Kein Feld ist kritisch, unter jeder Logik, denn ohne eines der drei Felder bleibt
    qSOFA ≥ 2.
  - Variante mit sRR 120 (qSOFA 2): Atemfrequenz und Bewusstsein sind kritisch, der Blutdruck nicht.
  - Die Regel arbeitet also wie gedacht; das Beispiel liegt am Rand.
- Die Regel gilt wörtlich mit dreiwertiger Logik. Das Beispiel dient als Illustration; sein nachgerechneter Schlüssel
  kommt in die Doku.

**D-06 EU-Grenze und Prüfmodell (B7): Empfehlung A bestätigt.**
- Die PRD plant selbst „DeepSeek über API, Qwen lokal“ (§11, W13–W14) und westliche Modelle über EU-Server nach deiner
  Rückkehr (§14). Von hier läuft also kein `mistral`.
- Bestand am 08.11.2026: Ollama hat nur `mistral` und `nomic-embed-text`; die GPU (RTX 3080 Laptop, 8 GB) ist frei.
- Lokales Prüfmodell: ein aktuelles Qwen-Instruct-Modell der Klasse 7–8 B, etwa 5 GB.
  - Die genaue Variante wähle ich beim Download nach dem dann aktuellen Ollama-Katalog. Der Digest steht im Manifest.
  - Der Download fällt in die Phase des Testlaufs, nie während NeuroGrid-Läufen.
  - Ollama-Modelle nur hinzufügen (A-30). RegOps plant ebenfalls Qwen; ein gemeinsam genutztes Modell im
    Ollama-Speicher ist keine Code-Abhängigkeit.
  - Ein Denkmodus des Modells ist ein Laufparameter und steht im Manifest.
- Die CI nutzt einen lokalen Stub-Server.
- Westliche Anbieter brauchen die erklärte Region `EU`; sie steht im Manifest.
- Die DeepSeek-Anbindung wird gebaut und mit dem Stub geprüft. Echte Läufe startest du mit eigenem Schlüssel; das ist
  kostenpflichtig.

**D-07 GitHub (B8): Empfehlung A bestätigt.**
- Bestand: Konto `Ammxri` (NeuroGrid-Remote), kein `gh` auf dem Rechner.
- Ein öffentliches Repository hat kostenlose CI unter Windows und Linux und kostenlose Pages. Ein privates bräuchte für
  Pages ein Bezahl-Abo und hätte begrenzte CI-Minuten.
- Du legst `github.com/Ammxri/proof` öffentlich und leer an, sobald die erste Phase pushbereit ist. Bis dahin arbeite
  ich lokal mit git.
- Gepusht wird nur `dev`. `main`, Releases und Pages nur mit deiner Freigabe.

**D-08 Zweite Domäne (B9): Empfehlung geändert.**
- NICE NG143 fällt als Grundlage weg; Grund ist die Lizenzlage, siehe D-04.
- Zweite Domäne ist Brustschmerz, das erste Beispiel in PR-F12. Die Kriterien kommen aus Originalpublikationen nach der
  Quellenregel aus D-04.
- Welche Scores verwendet werden und die Quellprüfung entscheiden sich in der Phase von PR-F12. Neue Faktentypen wie
  EKG und Troponin gehören dazu.
- Fieber bei Kindern bleibt möglich, wenn du bei NICE eine Lizenz einholst.

**D-09 Freigabe von STOPP 2 (08.11.2026).** Deine Antwort: „Ja, U1 starten“. Damit gelten [KONZEPT.md](KONZEPT.md) und
die Auslegungen A-31 bis A-48. Die Umsetzung läuft im Freigabemodus A (A-01) bis GO-1.

**D-10 certifi zugelassen (08.11.2026).**
- Die Lizenzprüfung meldete `certifi` 2026.10.23 mit MPL-2.0. Proof nutzt es unverändert als CA-Bündel: für pip-audit
  und ab U7 über httpx.
- Meine Ankündigung nach U1: „Ich empfehle, es zuzulassen. Wenn du nichts anderes sagst, trage ich das so ein.“
- Deine Antwort: „Angelegt, weiter mit U2“, ohne Widerspruch.
- Eingetragen in `tools/license_decisions.toml`, nur für diese Version. Eine neue Version wird wieder gemeldet.

**Stand D-07 (08.11.2026).**
- Deine Antwort: „Angelegt, weiter mit U2“.
- Zu Beginn von U2 war das Repository noch nicht erreichbar.
- Nach U2 fand ich es als `github.com/Ammxri/Proof`: öffentlich, leer, angelegt am 08.11.2026 um 13:52 UTC. GitHub
  unterscheidet bei Namen nicht zwischen Groß- und Kleinschreibung.
- Gepusht wird nur `dev`. Da das Repository leer war, macht GitHub `dev` zum Standardzweig, bis es `main` gibt.

**D-11 Quellen der migrierten Laborregeln (B10): Empfehlung A bestätigt (08.11.2026).** Deine Antwort:
„A: Nachschlagewerke“.
- Für die migrierten Laborregeln sind zusätzlich Nachschlagewerke zugelassen (Art `reference_work`, A-58), je
  Laborabweichung ein Kapitel. Die Bedingungen jedes Kapitels werden geprüft und im Register vermerkt.
- Übernommen werden nur Tatsache und Fundstelle, in eigener Formulierung; kein Text und keine Tabelle.
- Eine Zuordnung des Prototyps, die das Kapitel nicht belegt, wird keine Regel. Die Migrationstabelle nennt den Grund.
- `GENERELL_HOCH` wird begründet ausgelassen. `UR` wird als Harnstoff migriert; die Zuordnungen zu Harnsäure entfallen.
- Für die Fieberregeln und Warnzeichen gilt D-04 unverändert: Originalpublikationen und Leitlinien.

**D-12 Ollamas eigene API für lokale Modelle (B11): Empfehlung A bestätigt (09.11.2026).** Deine Antwort:
„A: Ollama-API“.
- Neben dem OpenAI-Protokoll gibt es die Schnittstellenart `ollama_chat`: `POST /api/chat` auf dem Ollama-Server
  dieses Rechners, mit `think: false`. Das ist eine bewusste **Abweichung** von KONZEPT 4.9 und 5.2, die für Ollama
  nur das OpenAI-Protokoll vorsahen. Die PRD (PR-F07) gibt die Schnittstelle lokaler Modelle nicht vor.
- Nachrichten, Temperatur 0, Seed und Tokengrenze sind in beiden Schnittstellen gleich; die Schnittstelle und der
  Denkschalter stehen im Manifest.
- Prüfmodell bleibt Qwen3 8B (A-77); `providers/qwen-local.yaml` nutzt `ollama_chat`.
