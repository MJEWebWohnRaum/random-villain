"""Baut app/index.html: bettet data/villains.json und data/packs.json in app/template.html ein.

Aufruf:  python scripts/build_app.py
Die JSON-Dateien bleiben die einzige Datenquelle; index.html ist ein reines Build-Ergebnis.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = "/*__DATA__*/"


def main():
    template = (ROOT / "app" / "template.html").read_text(encoding="utf-8")
    assert template.count(PLACEHOLDER) == 1, "Platzhalter fehlt oder ist mehrfach vorhanden"
    data = {
        "villains": json.loads((ROOT / "data" / "villains.json").read_text(encoding="utf-8")),
        "packs": json.loads((ROOT / "data" / "packs.json").read_text(encoding="utf-8")),
    }
    # kompakt; „</“ maskieren, damit kein Text das <script>-Tag schließen kann
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    out = ROOT / "app" / "index.html"
    out.write_text(template.replace(PLACEHOLDER, payload), encoding="utf-8", newline="\n")
    n = sum(len(v["combinations"]) for v in data["villains"])
    print(f"{out.relative_to(ROOT)}: {len(data['villains'])} Villains, {n} Kombinationen, {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
