# Villains-best

Extraktion von VillainTheorys „Every Villain's Best Modular Sets“ (Marvel Champions, PDF im Projektordner, 72 Seiten) in geprüfte JSON-Dateien. Darauf baut die Web-App „Random Villain“ (`app/`) auf, die nur `data/villains.json` und `data/packs.json` nutzt.

Repo: https://github.com/MJEWebWohnRaum/random-villain (öffentlich). PDF, `check.html`/`check/` und `archiv/` sind per `.gitignore` ausgeschlossen.

## Arbeitsweise

- Mit dem Nutzer auf Deutsch, Du-Form, kurz, Wichtigstes zuerst.
- Korrektheit der Daten ist das Wichtigste. Nicht raten: Unklares kommt nach `data/unsicher.md` (Seite + Begründung) und wird dem Nutzer vorgelegt.
- Abweichungen von der PDF nur über `manual/corrections.json` (Entscheidungen des Nutzers), nie direkt in `data/`.
- `data/` wird vollständig vom Skript erzeugt, nicht von Hand bearbeiten.

## Befehle

```
pip install -r requirements.txt                        # pdfplumber, pymupdf, pytest, jsonschema
python scripts/extract.py [--pages 1-4] [--out DIR]    # schreibt data/*
python -m pytest -q -rxs tests                         # Prüfung
python scripts/build_check.py                          # check.html + check/pages/*.png
python scripts/build_app.py                            # app/index.html aus app/template.html + data/
```

Nach jeder Änderung: extract → pytest → build_check. Ein erneuter Lauf erzeugt byte-identische Dateien (per Test geprüft). Korrekturen werden nur bei vollem Lauf (Seiten 1–72) angewendet.

## Dateien

- `scripts/extract.py` – Extraktor. pdfplumber liest die Tabellen über die echten Gitterlinien (`find_tables`), Zellen zeilenweise mit Schriftstil (fett/kursiv). Überschriften zwischen zwei Tabellen: ≥14pt = Erweiterung, ≥11.75pt = Villain, sonst Themes/Mechanics/Hinweise. Tabelle ohne Villain-Überschrift = Fortsetzung des vorigen Villains. Danach Nachprüfungen, Korrekturen, Endstruktur.
- `scripts/validate.py` – JSON-Schemas und Prüfregeln, gemeinsam für Tests und `check.html`.
- `scripts/build_check.py` – `check.html`: pro Villain extrahierte Tabelle neben dem Seitenbild. Farben: rot = Regel verletzt und undokumentiert, gelb = offen, blau = vom Nutzer korrigiert, grün = vom Nutzer bestätigt.
- `tests/test_data.py` – Schema; Regeln (genau 1 DEFAULT, Difficulty −2..+4, Sets = Packs, bekannte Kürzel, keine leeren Felder/Duplikate, > 600 Kombinationen, jede Seite zugeordnet); unabhängige Gegenzählung mit PyMuPDF (✔ und Difficulty-Werte pro Seite); Determinismus; Fixtures aus echten Seiten; Regressionen; Nutzerkorrekturen. Regelverstöße mit Status „korrigiert“/„bestätigt“ gelten als bestanden, „offen“ als xfail, undokumentierte schlagen fehl.
- `manual/corrections.json` – Nutzerentscheidungen: `fixes` (Packs/Sets einer Zeile, mit Prüfung des PDF-Werts `pdfPacks`), `accepted` (PDF-Wert bestätigt), `packSpelling`, `setSpelling`, `packAliases`, `combinedCodes`, `nemesisSets`.
- `data/villains.json`, `data/packs.json` – finale Daten.
- `data/unsicher.md` – alle Auffälligkeiten mit Status offen/korrigiert/bestätigt.
- `data/extraction_meta.json` – Rohwerte je Zeile (PDF-Packs, Seite), PyMuPDF-Zählungen je Seite, alle Issues mit Status, SHA-256 der PDF.
- `app/template.html` – Quelltext der App; `app/index.html` ist Build-Ergebnis (nicht von Hand bearbeiten), wird mit eingecheckt, damit es per Doppelklick läuft.
- `scripts/build_app.py` – bettet die JSON als `<script type="application/json">` ein (`fetch` geht bei `file://` nicht).
- `archiv/zweitversuch/` – unabhängiger zweiter Extraktionsversuch, nur zur Referenz (enthält Fehler, z. B. MG-Legendenname, geratene Packs).

## Datenstruktur

`villains.json` (Liste, PDF-Reihenfolge):
- Villain: `name` (Großbuchstaben wie PDF), `expansion`, `type` (villain/custom-combos), `released`, `themes[]`, `mechanics[]`, `required[]`, `starMeaning`?, `pageNotes[]`, `extraPools[]`?, `pdfPages[]`, `combinations[]`.
- Kombination: `name`, `subtitle`?, `modulars[]`, `modularsNote`?, `mainSchemes[]`?, `difficulty` (Zahl oder null), `difficultySpeculative`, `notes`, `recommended`, `isDefault`, `correction`? (Begründung, falls vom Nutzer korrigiert).
- Modular: `name` (PDF-Text), `pack`, `type` (modular/nemesis/choice), `canonical` (vereinheitlichte Schreibweise zum Gruppieren/Anzeigen), `footnote`? (Sternchen, Anzahl erhalten).

`packs.json`: `packs` (18 aus Legende S. 1), `heroPacks` (28 Kürzel), `unclearCodes`, `spellingFixes`, `aliases` (FEAR → FNE), `combinedCodes` (CW + SS, CW / SS → CW, SS).

## PDF-Fakten (verifiziert)

- ✔ ist ein Textzeichen (Font NotoColorEmoji), keine Grafik; Seiten enthalten keine Bilder.
- Mehrere Sets/Packs pro Zelle: eine Zeile je Eintrag, n-tes Pack ↔ n-tes Set.
- Kursiv in der Modular-Zelle = Erklärtext → `modularsNote`; kursiv im Namensfeld = `subtitle`.
- Umbrochene Platzhalter („A random MojoMania / modular set“) = ein Eintrag mit `type: choice`.
- Civil War (S. 55–62): fett = Name, normal = `mainSchemes[]`. S. 55/56 haben keine Difficulty-Spalte (`difficulty: null`).
- Sternchen an Set-Namen (S. 8, 12) → `footnote`, Bedeutung in `starMeaning`.
- S. 37 hat zwei Villains (Spiral, Mojo); The Hood läuft über S. 24/25.
- S. 63–72 „[UNRELEASED / SPECULATIVE]“ → `released: false`; „+2?“ → `difficultySpeculative: true`.
- Difficulty −3 kommt 7× vor (vom Nutzer bestätigt), obwohl die Einleitung −2..+4 nennt.
- Ligaturen (ﬁ→fi) expandiert, Whitespace normalisiert.

## Nutzerentscheidungen (2026-10-21)

- Packs ergänzt: Vibranium Order (+ Black Order/MTS), Anti-Mutant Army (APOC, APOC), A New Prelate (Deathstrike = Nemesis, WOLV.), Illusions of Betrayal S. 54 (CW, CW), Captain Venom (+ APOC), Stealth Mission (+ APOC, abgeleitet), Self-Propelled Goblin Glider (+ GG), Stone Cold Stunner (HOOD, APOC).
- Schreibweisen: SP//DR, MAGNETO, Cape-Killers. FEAR = Fear No Evil (FNE).
- Bestätigt: alle −3-Werte, fehlende DEFAULT-Zeilen (The Hood, Custom Combos, 8 unveröffentlichte Villains), fehlende Themes/Mechanics der Custom Combos, Platzhalter-Sets.

## App (Version 0)

- Eine Datei, kein Framework, keine externen Abhängigkeiten, dunkles UI.
- JS in drei Bereichen getrennt: Daten (`displayName`, `expansionName`, `packName`, `noteTags`, `sortedCombinations`, `choiceLine`), Zufall (`rollPool`, `pickRandom`), Darstellung (`render*`, Combobox).
- Entscheidungen des Nutzers: Combobox mit Suche; Sortierung nach Difficulty (Gleichstand: PDF-Reihenfolge); unveröffentlichte Villains normal drin (auch beim Würfeln, mit Hinweis); Custom-Combos wählbar, aber nicht gewürfelt.
- Später geplant (nur Vorschlag, nicht gebaut): Vercel-Hosting mit Login, Sammlungsfilter pro User (über `canonical`/Pack-Kürzel), Historie für gewichtetes Würfeln, JSON-Export, Veröffentlichung nur mit Erlaubnis/Quellenangabe für VillainTheory.

## Stand

- Daten fertig: 71 Villains, 826 Kombinationen, 0 offene Punkte, 1066 Tests grün.
- 2026-10-21: App Version 0 gebaut, erster Commit.
