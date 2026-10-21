# Random Villain – Marvel Champions

Würfelt einen Villain für das Kartenspiel **Marvel Champions** und zeigt passende Modular-Set-Kombinationen mit Schwierigkeit, Empfehlungen und Packs.

Die Daten stammen aus **VillainTheorys „Every Villain's Best Modular Sets“** (Stand 07/26):
https://www.youtube.com/@VillainTheory/ – alle Rechte an den Inhalten liegen bei VillainTheory.

## Benutzen

`app/index.html` per Doppelklick im Browser öffnen. Keine Installation, kein Server, keine externen Abhängigkeiten.

- **Roll again** würfelt einen Villain (alle Villains inkl. der unveröffentlichten Fear-No-Evil-Villains, keine Custom-Combos), nie zweimal hintereinander denselben.
- Das Feld oben zeigt den Villain und ist zugleich durchsuchbare Auswahl (Name oder Erweiterung tippen, Pfeiltasten, Enter).
- Die Kombinationen sind nach Difficulty sortiert. ✔ = Empfehlung, gold umrandet = DEFAULT MODULAR.
- Pack-Kürzel zeigen beim Überfahren den vollen Namen.
- **Choose this** zeigt die Auswahl als Einzeile, z. B. `Rhino – Hydra Assault (RORS), Ransacked Armory (HOOD)`.

## Projektaufbau

```
app/template.html        Quelltext der App (HTML, CSS, JS)
app/index.html           Build-Ergebnis: Template + eingebettete Daten
data/villains.json       71 Villains, 826 Kombinationen
data/packs.json          Pack-Legende, Hero-Packs, Aliasse
data/unsicher.md         Auffälligkeiten der Quelle und wie sie entschieden wurden
data/extraction_meta.json Rohwerte und Prüfzahlen der Extraktion
manual/corrections.json  manuelle Entscheidungen zu Lücken/Fehlern der Quelle
scripts/extract.py       Extraktion PDF → data/
scripts/validate.py      Schemas und Prüfregeln
scripts/build_check.py   Prüfseite check.html (Tabelle neben PDF-Seite)
scripts/build_app.py     baut app/index.html
tests/test_data.py       pytest-Prüfungen der Daten
```

## Daten neu erzeugen

Die Quell-PDF ist nicht im Repository. Für die Extraktion die PDF „Every Villain's Best Modular Sets by VillainTheory 07 26 [Marvel Champions] [PRINTABLE].pdf“ in den Projektordner legen.

```
pip install -r requirements.txt
python scripts/extract.py        # PDF → data/
python -m pytest -q tests        # Daten prüfen (braucht die PDF)
python scripts/build_check.py    # optional: check.html zum manuellen Abgleich
python scripts/build_app.py      # app/index.html neu bauen
```

Nach Änderungen an `app/template.html` oder `data/` immer `python scripts/build_app.py` ausführen.

## Datenqualität

- Tabellen werden über die Gitterlinien der PDF gelesen. ✔ und Zeilenzahl werden pro Seite unabhängig mit PyMuPDF gegengezählt.
- Ein erneuter Lauf erzeugt byte-identische Dateien.
- Lücken der Quelle (fehlende Pack-Kürzel, uneinheitliche Schreibweisen, Difficulty −3) sind in `data/unsicher.md` dokumentiert und über `manual/corrections.json` entschieden. Jede Korrektur trägt eine Begründung im Feld `correction`.

## Lizenz

Der **Code** (`scripts/`, `tests/`, `app/template.html`, Konfiguration) steht unter der [MIT-Lizenz](LICENSE), © 2026 MJEWebWohnRaum.

Die **Daten** sind davon ausgenommen: Die Inhalte in `data/` und die in `app/index.html` eingebetteten Daten (Kombinationsnamen, Notes, Difficulty, Empfehlungen) stammen aus VillainTheorys „Every Villain's Best Modular Sets“ (https://www.youtube.com/@VillainTheory/) und gehören deren Autor. Marvel Champions ist eine Marke der jeweiligen Rechteinhaber; dieses Projekt ist inoffiziell.

## Stand

Version 0: einzelne lokale HTML-Datei, ohne Login. Geplant: Hosting mit Login, Filter auf die eigene Sammlung, Historie gespielter Villains, JSON-Export.
