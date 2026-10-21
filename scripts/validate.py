"""Gemeinsame Prüfregeln für pytest und check.html."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
NO_DEFAULT_RE = re.compile(r"DOES NOT NORMALLY CONTAIN", re.I)
RESOLVED = {"korrigiert", "bestätigt"}

_STR = {"type": "string", "minLength": 1}
_STRS = {"type": "array", "items": _STR}

MODULAR_SCHEMA = {
    "type": "object",
    "required": ["name", "pack", "type", "canonical"],
    "additionalProperties": False,
    "properties": {
        "name": _STR,
        "pack": {"type": ["string", "null"], "minLength": 1},
        "type": {"enum": ["modular", "nemesis", "choice"]},
        "canonical": _STR,
        "footnote": {"type": "string", "pattern": r"^\*+$"},
    },
}

COMBO_SCHEMA = {
    "type": "object",
    "required": ["name", "modulars", "difficulty", "difficultySpeculative", "notes", "recommended", "isDefault"],
    "additionalProperties": False,
    "properties": {
        "name": _STR,
        "subtitle": _STR,
        "modulars": {"type": "array", "minItems": 1, "items": MODULAR_SCHEMA},
        "modularsNote": _STR,
        "mainSchemes": _STRS,
        "difficulty": {"type": ["integer", "null"]},
        "difficultySpeculative": {"type": "boolean"},
        "notes": {"type": "string"},
        "recommended": {"type": "boolean"},
        "isDefault": {"type": "boolean"},
        "correction": _STR,
    },
}

VILLAIN_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["name", "expansion", "type", "released", "themes", "mechanics", "required", "pageNotes",
                     "pdfPages", "combinations"],
        "additionalProperties": False,
        "properties": {
            "name": _STR,
            "expansion": _STR,
            "type": {"enum": ["villain", "custom-combos"]},
            "released": {"type": "boolean"},
            "themes": _STRS,
            "mechanics": _STRS,
            "required": _STRS,
            "starMeaning": _STR,
            "pageNotes": _STRS,
            "extraPools": {"type": "array", "items": {
                "type": "object", "required": ["title", "modulars"], "additionalProperties": False,
                "properties": {"title": _STR, "modulars": {"type": "array", "minItems": 1, "items": _STR}}}},
            "pdfPages": {"type": "array", "minItems": 1, "items": {"type": "integer", "minimum": 2}},
            "combinations": {"type": "array", "minItems": 1, "items": COMBO_SCHEMA},
        },
    },
}

PACKS_SCHEMA = {
    "type": "object",
    "required": ["packs", "heroPacks", "unclearCodes", "spellingFixes", "aliases", "combinedCodes"],
    "additionalProperties": False,
    "properties": {
        "packs": {"type": "array", "minItems": 1, "items": {
            "type": "object", "required": ["code", "name"], "additionalProperties": False,
            "properties": {"code": _STR, "name": _STR}}},
        "heroPacks": _STRS,
        "unclearCodes": _STRS,
        "spellingFixes": {"type": "object", "additionalProperties": _STR},
        "aliases": {"type": "object", "additionalProperties": _STR},
        "combinedCodes": {"type": "object", "additionalProperties": {"type": "array", "minItems": 2, "items": _STR}},
    },
}


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def known_codes(packs):
    """Gültige Kürzel = Legende + Hero-Packs + vom Nutzer geklärte Aliasse/Kombi-Kürzel."""
    legend = {p["code"] for p in packs["packs"]}
    ok = legend | set(packs["heroPacks"])
    ok |= {k for k, v in packs["aliases"].items() if v in legend}
    ok |= {k for k, v in packs["combinedCodes"].items() if set(v) <= legend}
    return ok


def combo_problems(combo, raw, codes):
    """Probleme einer Zeile (leer = ok). raw = Rohwerte der Zeile aus extraction_meta.json."""
    probs = []
    d = combo["difficulty"]
    if raw["hasDifficultyColumn"]:
        if d is None or not -2 <= d <= 4:
            probs.append(f"Difficulty außerhalb −2..+4: {d}")
    elif d is not None:
        probs.append("Difficulty ohne Difficulty-Spalte")
    if len(combo["modulars"]) != len(raw["packs"]):
        probs.append(f"{len(combo['modulars'])} Modular-Sets, aber {len(raw['packs'])} Packs in der PDF")
    for m in combo["modulars"]:
        if m["pack"] is None:
            probs.append(f"Kein Pack für „{m['name']}“")
        elif m["pack"] not in codes:
            probs.append(f"Unbekanntes Pack-Kürzel „{m['pack']}“")
    for field in ("name", "notes"):
        if not combo[field].strip():
            probs.append(f"Leeres Feld {field}")
    return probs


def villain_problems(villain):
    probs = []
    defaults = sum(c["isDefault"] for c in villain["combinations"])
    no_default_note = any(NO_DEFAULT_RE.search(i) for i in villain["pageNotes"])
    if defaults != 1 and not (defaults == 0 and no_default_note):
        probs.append(f"{defaults} DEFAULT-Zeilen (erwartet 1)")
    names = [c["name"] for c in villain["combinations"]]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        probs.append(f"Doppelte Kombinationsnamen: {dupes}")
    for f in ("themes", "mechanics"):
        if not villain[f]:
            probs.append(f"Keine {f}")
    return probs


def row_statuses(meta):
    """(Seite, Zeilenname) -> Menge der Issue-Status."""
    out = {}
    for i in meta["issues"]:
        if i["row"]:
            out.setdefault((i["page"], i["row"]), set()).add(i["status"])
    return out


def villain_statuses(meta):
    """Villain-Name -> Menge der Issue-Status (nur Villain-weite Issues)."""
    out = {}
    for i in meta["issues"]:
        if i.get("villain") and not i["row"]:
            out.setdefault(i["villain"], set()).add(i["status"])
    return out


def rows_with_combos(villains, meta):
    """(villain, combo, raw) in PDF-Reihenfolge."""
    return [(villains[r["villain"]], villains[r["villain"]]["combinations"][r["combination"]], r)
            for r in meta["rows"]]
