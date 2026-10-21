"""Extrahiert Packs und Villain-Kombinationen aus der VillainTheory-PDF nach data/.

Aufruf:  python scripts/extract.py [--pages 1-4] [--out DIR]
Deterministisch: gleicher Input -> byte-identische Dateien.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pdfplumber
import pymupdf

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CORRECTIONS = ROOT / "manual" / "corrections.json"
CHECK = "✔"  # ✔
SPECULATIVE = "[UNRELEASED / SPECULATIVE]"
COLUMNS = {"Name": "name", "Name + Main Schemes": "name+schemes", "Modular Sets": "mods",
           "Difficulty": "diff", "Main Schemes": "schemes", "Notes": "notes", "Packs": "packs"}
DEFAULT_RE = re.compile(r"^DEFAULT MODULARS?$")
DIFF_RE = re.compile(r"^([+-]?)(\d)(\?)?$")
NO_DEFAULT_RE = re.compile(r"DOES NOT NORMALLY CONTAIN", re.I)
KEY_LINE_RE = re.compile(r"^[A-Z][A-Za-z ]+:")
# Nicht in der Legende, aber erkennbar kein Hero-Pack -> unsicher.md
SUSPECT_CODES = {"FEAR": "Nicht in der Legende; die Legende führt Fear No Evil als „FNE“."}


def find_pdf():
    pdfs = sorted(ROOT.glob("*.pdf"))
    if len(pdfs) != 1:
        sys.exit(f"Erwarte genau eine PDF im Projektordner, gefunden: {pdfs}")
    return pdfs[0]


def norm(text):
    """Whitespace auf einfache Leerzeichen normalisieren."""
    return re.sub(r"\s+", " ", text or "").strip()


def styled_lines(page, bbox):
    """Textzeilen in bbox mit Stil (bold/italic nach Mehrheit der Zeichen)."""
    if bbox is None:
        return []
    out = []
    for line in page.crop(bbox).extract_text_lines():
        chars = [c for c in line["chars"] if c["text"].strip()]
        text = norm(line["text"])
        if not text or not chars:
            continue
        fonts = [c["fontname"] for c in chars]
        out.append({
            "text": text,
            "bold": sum("Bold" in f for f in fonts) * 2 > len(fonts),
            "italic": sum("Italic" in f for f in fonts) * 2 > len(fonts),
            "size": round(chars[0]["size"], 1),
            "top": line["top"],
        })
    return out


# ---------------------------------------------------------------- Legende (Seite 1)

def parse_legend(page):
    """Zwei Spalten 'CODE = Name'. Spaltengrenze = x0 des am weitesten links stehenden Codes der rechten Spalte."""
    words = page.extract_words()
    eqs = [w for w in words if w["text"] == "="]
    if not eqs:
        raise RuntimeError("Legende: keine '='-Zeichen gefunden")
    top_min = min(w["top"] for w in eqs) - 2
    mid = (min(w["x0"] for w in eqs) + max(w["x0"] for w in eqs)) / 2
    right_codes = []
    for eq in (w for w in eqs if w["x0"] > mid):
        before = [w for w in words if abs(w["top"] - eq["top"]) < 2 and w["x1"] <= eq["x0"]]
        right_codes.append(max(before, key=lambda w: w["x1"])["x0"])
    split = min(right_codes) - 1
    lines = {}
    for w in words:
        if w["top"] >= top_min:
            col = 0 if w["x0"] < split else 1
            lines.setdefault((col, round(w["top"])), []).append(w)
    packs = []
    for col in (0, 1):
        for key in sorted(k for k in lines if k[0] == col):
            text = " ".join(w["text"] for w in sorted(lines[key], key=lambda w: w["x0"]))
            m = re.match(r"^([A-Za-z/]+) = (.+)$", norm(text))
            if m:
                packs.append({"code": m.group(1), "name": m.group(2)})
    return packs


# ---------------------------------------------------------------- Überschriften

def merge_info_lines(lines):
    """Umbrochene Info-Zeilen zusammenführen (z. B. NOTE über zwei Zeilen, '(Crime, …)')."""
    out = []
    for ln in lines:
        t = ln["text"]
        prev = out[-1] if out else None
        continues = (prev is not None and prev["size"] == ln["size"]
                     and not KEY_LINE_RE.match(t) and not re.match(r"^(\d+\.|●)", t)
                     and (t.startswith("(") or not re.search(r"[.:!)]$", prev["text"])))
        if continues:
            prev["text"] = f"{prev['text']} {t}"
        else:
            out.append(dict(ln))
    return out


def apply_headings(lines, state, page_no, issues):
    """Verarbeitet Überschriften-Zeilen; liefert neuen Villain oder None (= Fortsetzung)."""
    villain = None
    info = []
    for ln in lines:
        t, size = ln["text"], ln["size"]
        if size >= 14:
            if t == SPECULATIVE:
                continue
            state["expansion"] = t
        elif size >= 11.75:
            name = t
            speculative = SPECULATIVE in name
            name = norm(name.replace(SPECULATIVE, ""))
            m = re.match(r"^(.*?)\s*\[PAGE #(\d+)\]$", name)
            if m:
                name = m.group(1)
                cur = state.get("villain")
                if int(m.group(2)) > 1 and cur and cur["name"] == name:
                    continue  # Fortsetzung desselben Villains
            villain = {"name": name, "expansion": state["expansion"], "speculative": speculative,
                       "themes": [], "mechanics": [], "info": [], "pools": [], "pdfPages": [page_no],
                       "combinations": []}
        else:
            info.append(ln)
    target = villain or state.get("villain")
    for ln in merge_info_lines(info):
        m = re.match(r"^(Themes|Mechanics):\s*(.*)$", ln["text"])
        if m and target is not None:
            target[m.group(1).lower()] = [norm(x) for x in m.group(2).split(",") if norm(x)]
        elif target is not None:
            target["info"].append(ln["text"])
        else:
            issues.append({"page": page_no, "row": None, "reason": f"Textzeile ohne Villain: {ln['text']!r}"})
    return villain


# ---------------------------------------------------------------- Tabellenzeilen

def parse_row(page, row, cols, page_no, issues):
    cells = {key: styled_lines(page, bbox) for key, bbox in zip(cols, row.cells) if key}
    combo = {}
    if "name+schemes" in cells:
        lines = cells["name+schemes"]
        name_lines = [l["text"] for l in lines if l["bold"]]
        schemes = [l["text"] for l in lines if not l["bold"]]
        subtitle = []
    else:
        # kursive Zeilen im Namensfeld sind Untertitel (z. B. “Guess I am a menace.”)
        name_lines = [l["text"] for l in cells.get("name", []) if not l["italic"]]
        subtitle = [l["text"] for l in cells.get("name", []) if l["italic"]]
        schemes = [l["text"] for l in cells.get("schemes", [])]
    name_full = norm(" ".join(name_lines + subtitle))
    name = norm(" ".join(name_lines).replace(CHECK, ""))
    combo["name"] = name
    if subtitle:
        combo["subtitle"] = norm(" ".join(subtitle).replace(CHECK, ""))

    mod_lines = [l["text"] for l in cells.get("mods", []) if not l["italic"]]
    packs_raw = [l["text"] for l in cells.get("packs", [])]
    choice = len(packs_raw) == 1 and len(mod_lines) > 1 and bool(re.search(r"modular sets?$", " ".join(mod_lines)))
    if choice:
        # umbrochene Platzhalter-Angabe („A random MojoMania / modular set“) ist ein Eintrag
        mod_lines = [norm(" ".join(mod_lines))]
        issues.append({"page": page_no, "row": norm(" ".join(name_lines).replace(CHECK, "")),
                       "reason": f"Platzhalter statt konkretem Modular-Set: „{mod_lines[0]}“ ({packs_raw[0]})."})
    mod_note = norm(" ".join(l["text"] for l in cells.get("mods", []) if l["italic"]))
    packs = [l["text"] for l in cells.get("packs", [])]
    modulars = []
    for i, text in enumerate(mod_lines):
        m = re.match(r"^(.*?)(\*+)$", text)
        entry = {"name": m.group(1) if m else text,
                 "pack": packs[i] if len(packs) == len(mod_lines) else None}
        if m:
            entry["footnote"] = m.group(2)
        if choice:
            entry["_choice"] = True
        modulars.append(entry)
    if len(mod_lines) != len(packs):
        issues.append({"page": page_no, "row": name,
                       "reason": f"{len(mod_lines)} Modular-Set-Zeile(n) {mod_lines}, aber {len(packs)} Pack(s) {packs}. "
                                 "Zuordnung unklar, Packs nicht zugeordnet."})
    combo["modulars"] = modulars
    if mod_note:
        combo["modularsNote"] = mod_note
    if schemes:
        combo["mainSchemes"] = schemes

    difficulty, tentative = None, False
    if "diff" in cells:
        diff_txt = norm(" ".join(l["text"] for l in cells["diff"]))
        m = DIFF_RE.match(diff_txt)
        if m:
            difficulty = int(m.group(1) + m.group(2))
            tentative = bool(m.group(3))
            if not -2 <= difficulty <= 4:
                issues.append({"page": page_no, "row": name,
                               "reason": f"Difficulty {diff_txt} liegt außerhalb −2..+4 (steht so in der PDF)."})
        else:
            issues.append({"page": page_no, "row": name, "reason": f"Difficulty nicht lesbar: {diff_txt!r}"})
    combo["difficulty"] = difficulty
    combo["difficultyTentative"] = tentative
    combo["notes"] = norm(" ".join(l["text"] for l in cells.get("notes", [])))
    combo["recommended"] = CHECK in name_full
    combo["isDefault"] = bool(DEFAULT_RE.match(name))
    return combo, {"page": page_no, "packs": packs, "hasDifficultyColumn": "diff" in cells}


def header_columns(page, table):
    """Spaltenschlüssel aus der Kopfzeile + Zusatztext unter Spaltennamen (z. B. Fußnoten-Legende)."""
    cols, extra = [], []
    for bbox in table.rows[0].cells:
        lines = [l["text"] for l in styled_lines(page, bbox)]
        cols.append(COLUMNS.get(lines[0]) if lines else None)
        if lines and lines[0] in COLUMNS:
            extra += [f"{lines[0]}: {t}" for t in lines[1:]]
    return cols, extra


def parse_page(page, page_no, state, villains, raw_rows, issues):
    tables = sorted(page.find_tables(), key=lambda t: t.bbox[1])
    all_lines = styled_lines(page, (0, 0, page.width, page.height))
    prev_bottom = 0
    if not tables:
        issues.append({"page": page_no, "row": None, "reason": "Keine Tabelle erkannt."})
    for table in tables:
        top, bottom = table.bbox[1], table.bbox[3]
        heads = [l for l in all_lines if prev_bottom <= l["top"] < top - 1]
        prev_bottom = bottom
        cols, extra = header_columns(page, table)
        is_combo = cols[0] in ("name", "name+schemes") and "mods" in cols and "packs" in cols
        new = apply_headings(heads, state, page_no, issues)
        if new:
            villains.append(new)
            state["villain"] = new
        villain = state.get("villain")
        if villain is None:
            issues.append({"page": page_no, "row": None, "reason": "Tabelle ohne Villain-Überschrift."})
            continue
        if page_no not in villain["pdfPages"]:
            villain["pdfPages"].append(page_no)
        if not is_combo:
            # Nebentabelle (z. B. Thunderbolts-Liste) als Auswahl-Pool übernehmen
            title = norm(" ".join(l["text"] for l in styled_lines(page, table.rows[0].cells[0] or table.rows[0].bbox)))
            items = [norm(c) for r in table.extract()[1:] for c in r if norm(c)]
            villain["pools"].append({"title": title, "modulars": items})
            continue
        villain["info"] += extra
        if [c for c in cols if c is None]:
            issues.append({"page": page_no, "row": None, "reason": f"Unbekannte Spalte in Kopfzeile: {cols}"})
        for row in table.rows[1:]:
            combo, raw = parse_row(page, row, cols, page_no, issues)
            villain["combinations"].append(combo)
            raw_rows.append({"villain": len(villains) - 1, "combination": len(villain["combinations"]) - 1,
                             "name": combo["name"], **raw})


# ---------------------------------------------------------------- Nachprüfungen

def subsequence(a, b):
    it = iter(b)
    return all(ch in it for ch in a)


def post_checks(villains, raw_rows, legend_codes, issues):
    for v in villains:
        defaults = sum(c["isDefault"] for c in v["combinations"])
        no_default_note = any(NO_DEFAULT_RE.search(i) for i in v["info"])
        if defaults != 1 and not (defaults == 0 and no_default_note):
            issues.append({"page": v["pdfPages"][0], "row": None, "villain": v["name"],
                           "reason": f"{v['name']}: {defaults} DEFAULT-Zeilen in der PDF (erwartet 1), "
                                     "und kein Hinweis „does not normally contain“."})
        names = [c["name"] for c in v["combinations"]]
        for d in sorted({n for n in names if names.count(n) > 1}):
            issues.append({"page": v["pdfPages"][0], "row": d, "villain": v["name"],
                           "reason": f"Kombinationsname doppelt bei {v['name']}."})
        for f in ("themes", "mechanics"):
            if not v[f]:
                issues.append({"page": v["pdfPages"][0], "row": None, "villain": v["name"],
                               "reason": f"{v['name']}: keine „{f.capitalize()}:“-Zeile in der PDF."})

    codes = {}
    for r in raw_rows:
        for p in r["packs"]:
            codes.setdefault(p, []).append(r)
    hero, unclear = [], []
    for code in sorted(codes):
        if code in legend_codes:
            continue
        pages = sorted({r["page"] for r in codes[code]})
        reason = SUSPECT_CODES.get(code)
        if reason is None and re.search(r" [+/] ", code):
            reason = "Mehrere Kürzel in einer Zelle (Auswahl aus mehreren Packs)."
        if reason is None and not re.match(r"^[A-Z0-9][A-Za-z0-9./ -]*$", code):
            reason = "Sieht nicht wie ein Pack-Kürzel aus."
        if reason:
            unclear.append(code)
            for r in codes[code]:
                issues.append({"page": r["page"], "row": r["name"], "reason": f"Pack-Kürzel „{code}“: {reason}"})
        else:
            hero.append(code)
    for a in hero:
        for b in hero:
            if a < b and (a.casefold() == b.casefold() or (abs(len(a) - len(b)) == 1 and
                          (subsequence(a, b) or subsequence(b, a)))):
                pa = sorted({r["page"] for r in codes[a]})
                pb = sorted({r["page"] for r in codes[b]})
                issues.append({"page": min(pa + pb), "row": None,
                               "reason": f"Hero-Pack-Kürzel „{a}“ (S. {pa}) und „{b}“ (S. {pb}) sind vermutlich dasselbe Pack. Nicht vereinheitlicht."})
    return hero, unclear


# ---------------------------------------------------------------- Korrekturen & Endstruktur

SMALL_WORDS = {"of", "in", "to", "and", "the", "a", "on", "at", "for"}
NAME_ALIASES = {"Guerilla Tactics": "Guerrilla Tactics", "The Black Order": "Black Order"}


def canonical(name):
    """Vereinheitlichter Set-Name zum Gruppieren (Apostroph, kleine Wörter, „Nemesis Set“). name bleibt PDF-Text."""
    s = name.replace("’", "'")
    s = NAME_ALIASES.get(s, s)
    s = " ".join(w.lower() if i and w.lower() in SMALL_WORDS else w for i, w in enumerate(s.split(" ")))
    if s.endswith("Nemesis"):
        s += " Set"
    return s


def apply_corrections(villains, raw_rows, issues, corr):
    """Manuelle Korrekturen anwenden; jedes Issue bekommt status offen/korrigiert/bestätigt."""
    for it in issues:
        it["status"], it["resolution"] = "offen", None

    def resolve(match, status, reason):
        hits = [it for it in issues
                if all(it.get(k) == match[k] for k in ("page", "row", "villain") if k in match)
                and match.get("reasonContains", "") in it["reason"]]
        if not hits:
            sys.exit(f"Korrektur passt zu keinem Eintrag in unsicher.md: {match}")
        for it in hits:
            it["status"], it["resolution"] = status, reason

    for fx in corr["fixes"]:
        rows = [r for r in raw_rows if r["page"] == fx["page"] and r["name"] == fx["row"]]
        if len(rows) != 1:
            sys.exit(f"Korrektur: Zeile nicht eindeutig gefunden: S. {fx['page']} {fx['row']}")
        r = rows[0]
        if r["packs"] != fx["pdfPacks"]:
            sys.exit(f"Korrektur {fx['row']}: PDF-Packs {r['packs']} != erwartet {fx['pdfPacks']}")
        combo = villains[r["villain"]]["combinations"][r["combination"]]
        if "modulars" in fx:
            combo["modulars"] = [{"name": n, "pack": p} for n, p in fx["modulars"]]
        else:
            if len(fx["packs"]) != len(combo["modulars"]):
                sys.exit(f"Korrektur {fx['row']}: {len(fx['packs'])} Packs für {len(combo['modulars'])} Sets")
            for m, p in zip(combo["modulars"], fx["packs"]):
                m["pack"] = p
        combo["correction"] = fx["reason"]
        resolve({"page": fx["page"], "row": fx["row"]}, "korrigiert", fx["reason"])
    for wrong, sp in corr["packSpelling"].items():
        for v in villains:
            for c in v["combinations"]:
                for m in c["modulars"]:
                    if m["pack"] == wrong:
                        m["pack"] = sp["code"]
        resolve({"reasonContains": f"„{wrong}“"}, "korrigiert", f"{wrong} → {sp['code']}. {sp['reason']}")
    for code, a in corr["packAliases"].items():
        resolve({"reasonContains": f"„{code}“"}, "bestätigt", f"{code} = {a['code']}. {a['reason']}")
    for code, c in corr["combinedCodes"].items():
        resolve({"reasonContains": f"„{code}“"}, "bestätigt", c["reason"])
    for acc in corr["accepted"]:
        resolve(acc, "bestätigt", acc["reason"])


def finalize(villains, corr):
    """Interne Felder in die Endstruktur überführen (feste Feldreihenfolge)."""
    out = []
    for v in villains:
        required, notes, star = [], [], None
        for line in v["info"]:
            m = re.match(r"^Required Modular Sets?(?: \(([^)]*)\))?:\s*(.*)$", line)
            s = re.match(r"^Modular Sets: \* = (.*)$", line)
            if m:
                required.append(m.group(2) + (f" ({m.group(1)})" if m.group(1) else ""))
            elif s:
                star = s.group(1)
            else:
                notes.append(line)
        combos = []
        for c in v["combinations"]:
            mods = []
            for m in c["modulars"]:
                canon = canonical(m["name"])
                kind = ("choice" if m.get("_choice") or re.search(r"\bmod(ular)? sets?\b", m["name"], re.I) else
                        "nemesis" if "Nemesis" in canon or canon in corr["nemesisSets"] else "modular")
                entry = {"name": m["name"], "pack": m["pack"], "type": kind, "canonical": canon}
                if m.get("footnote"):
                    entry["footnote"] = m["footnote"]
                mods.append(entry)
            nc = {"name": c["name"]}
            if c.get("subtitle"):
                nc["subtitle"] = c["subtitle"]
            nc["modulars"] = mods
            for k in ("modularsNote", "mainSchemes"):
                if k in c:
                    nc[k] = c[k]
            nc.update({"difficulty": c["difficulty"], "difficultySpeculative": c["difficultyTentative"],
                       "notes": c["notes"], "recommended": c["recommended"], "isDefault": c["isDefault"]})
            if c.get("correction"):
                nc["correction"] = c["correction"]
            combos.append(nc)
        nv = {"name": v["name"], "expansion": v["expansion"],
              "type": "custom-combos" if v["name"].startswith("CUSTOM ") else "villain",
              "released": not v["speculative"], "themes": v["themes"], "mechanics": v["mechanics"],
              "required": required}
        if star:
            nv["starMeaning"] = star
        nv["pageNotes"] = notes
        if v["pools"]:
            nv["extraPools"] = v["pools"]
        nv["pdfPages"] = v["pdfPages"]
        nv["combinations"] = combos
        out.append(nv)
    return out


# ---------------------------------------------------------------- Ausgabe

def count_checkmarks(pdf_path, first, last):
    """Unabhängige Zählung mit PyMuPDF: ✔ und Difficulty-Werte (z. B. „+2“, „0?“) pro Seite, dazu Bilder."""
    doc = pymupdf.open(pdf_path)

    def difficulty_tokens(page):
        # nur Werte, deren Mitte unter einer „Difficulty“-Überschrift liegt (Zahlen in Notes zählen nicht)
        words = page.get_text("words")
        heads = [w for w in words if w[4].replace("ﬁ", "fi") == "Difficulty"]
        return sum(1 for w in words if DIFF_RE.match(w[4]) and any(
            abs((w[0] + w[2]) / 2 - (h[0] + h[2]) / 2) < 25 and w[1] > h[3] for h in heads))

    return {str(i): {"checkmarks": doc[i - 1].get_text("text").count(CHECK),
                     "difficultyTokens": difficulty_tokens(doc[i - 1]),
                     "images": len(doc[i - 1].get_images(full=True))}
            for i in range(first, last + 1)}


def parse_range(spec, n_pages):
    if not spec:
        return 1, n_pages
    a, _, b = spec.partition("-")
    return int(a), int(b or a)


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_unsicher(path, issues, villains, first, last):
    lines = ["# Unsichere Zuordnungen", "",
             f"Automatisch erzeugt von `scripts/extract.py` (Seiten {first}–{last}). Nichts davon wurde geraten. "
             "Änderungen gegenüber der PDF stammen nur aus `manual/corrections.json`.", ""]
    tentative = [c for v in villains for c in v["combinations"] if c["difficultySpeculative"]]
    if tentative:
        lines += [f"Hinweis: {len(tentative)} Difficulty-Werte stehen in der PDF mit „?“ (z. B. „+2?“). "
                  "Gespeichert als Zahl + `difficultySpeculative: true`.", ""]
    for status, title in (("offen", "Offen"), ("korrigiert", "Von dir korrigiert"), ("bestätigt", "Von dir bestätigt")):
        group = sorted((i for i in issues if i["status"] == status), key=lambda i: i["page"])
        lines += [f"## {title} ({len(group)})", ""]
        if not group:
            lines.append("Keine.")
        for it in group:
            where = f"**S. {it['page']}**" + (f" – {it['row']}" if it["row"] else "")
            res = f" → {it['resolution']}" if it["resolution"] else ""
            lines.append(f"- {where}: {it['reason']}{res}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", help="Seitenbereich, z. B. 1-4 (Standard: alle)")
    ap.add_argument("--out", type=Path, default=DATA, help="Zielordner (Standard: data/)")
    args = ap.parse_args()
    out = args.out

    pdf_path = find_pdf()
    out.mkdir(parents=True, exist_ok=True)
    issues, villains, raw_rows = [], [], []
    with pdfplumber.open(pdf_path) as pdf:
        first, last = parse_range(args.pages, len(pdf.pages))
        legend = parse_legend(pdf.pages[0])
        state = {"expansion": None, "villain": None}
        for page_no in range(max(first, 2), last + 1):
            parse_page(pdf.pages[page_no - 1], page_no, state, villains, raw_rows, issues)

    legend_codes = {p["code"] for p in legend}
    hero, unclear = post_checks(villains, raw_rows, legend_codes, issues)
    corr = json.loads(CORRECTIONS.read_text(encoding="utf-8"))
    if (first, last) == (1, 72):
        apply_corrections(villains, raw_rows, issues, corr)
    else:
        for it in issues:
            it["status"], it["resolution"] = "offen", None
    villains = finalize(villains, corr)
    pages_by_canon = {}
    for v in villains:
        for c in v["combinations"]:
            for m in c["modulars"]:
                pages_by_canon.setdefault(m["canonical"], set()).update(v["pdfPages"])
    for name in sorted(pages_by_canon):
        if name + "s" in pages_by_canon:
            issues.append({"page": min(pages_by_canon[name] | pages_by_canon[name + "s"]), "row": None,
                           "status": "offen", "resolution": None,
                           "reason": f"Set-Name „{name}“ (S. {sorted(pages_by_canon[name])}) und „{name}s“ "
                                     f"(S. {sorted(pages_by_canon[name + 's'])}) sind vermutlich dasselbe Set. Nicht vereinheitlicht."})
    full = (first, last) == (1, 72)
    for wrong, sp in corr["setSpelling"].items() if full else []:
        for v in villains:
            for c in v["combinations"]:
                for m in c["modulars"]:
                    if m["canonical"] == wrong:
                        m["canonical"] = sp["canonical"]
        for it in issues:
            if f"„{wrong}“" in it["reason"]:
                it["status"], it["resolution"] = "korrigiert", f"canonical {wrong} → {sp['canonical']}. {sp['reason']}"
    spelling = {k: sp["code"] for k, sp in corr["packSpelling"].items()} if full else {}
    write_json(out / "packs.json", {
        "packs": legend, "heroPacks": [h for h in hero if h not in spelling],
        "unclearCodes": unclear, "spellingFixes": {k: v for k, v in spelling.items() if k in hero},
        "aliases": {k: a["code"] for k, a in corr["packAliases"].items() if k in unclear},
        "combinedCodes": {k: c["codes"] for k, c in corr["combinedCodes"].items() if k in unclear},
    })
    write_json(out / "villains.json", villains)
    write_json(out / "extraction_meta.json", {
        "source": pdf_path.name,
        "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
        "pageRange": [first, last],
        "pages": count_checkmarks(pdf_path, first, last),
        "rows": raw_rows,
        "issues": issues,
    })
    write_unsicher(out / "unsicher.md", issues, villains, first, last)

    n = sum(len(v["combinations"]) for v in villains)
    print(f"Seiten {first}-{last}: {len(villains)} Villains, {n} Kombinationen, {len(issues)} unsichere Stellen")


if __name__ == "__main__":
    main()
