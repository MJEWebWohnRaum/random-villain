import hashlib
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import validate as V  # noqa: E402

ROOT = V.ROOT
PACKS = V.load("packs.json")
VILLAINS = V.load("villains.json")
META = V.load("extraction_meta.json")
CODES = V.known_codes(PACKS)
FIRST, LAST = META["pageRange"]
FULL_RUN = FIRST == 1 and LAST == 72
ROW_STATUS = V.row_statuses(META)
VILLAIN_STATUS = V.villain_statuses(META)
ROWS = V.rows_with_combos(VILLAINS, META)


def by_name(name):
    matches = [v for v in VILLAINS if v["name"].casefold() == name.casefold()]
    assert len(matches) == 1, f"{name}: {len(matches)} Treffer"
    return matches[0]


def combo(villain, name):
    found = [c for c in villain["combinations"] if c["name"] == name]
    assert len(found) == 1, f"{villain['name']} / {name}: {len(found)} Treffer"
    return found[0]


def mods(c):
    return [(m["name"], m["pack"]) for m in c["modulars"]]


def judge(probs, statuses):
    """Keine Probleme -> ok. Probleme nur mit geklärten Issues -> ok. Offene Issues -> xfail. Sonst Fehler."""
    if not probs:
        return
    if statuses and statuses <= V.RESOLVED:
        return
    if "offen" in statuses:
        pytest.xfail("offen in unsicher.md: " + "; ".join(probs))
    pytest.fail("nicht dokumentiert: " + "; ".join(probs))


# ---------------------------------------------------------------- Schema & Grundregeln

def test_schema_villains():
    jsonschema.validate(VILLAINS, V.VILLAIN_SCHEMA)


def test_schema_packs():
    jsonschema.validate(PACKS, V.PACKS_SCHEMA)


def test_pack_codes_unique():
    codes = [p["code"] for p in PACKS["packs"]] + PACKS["heroPacks"] + PACKS["unclearCodes"]
    assert len(codes) == len(set(codes))


def test_legend_names_are_clean():
    """Kein Fließtext aus S. 1 im Pack-Namen (Fehler des Zweitversuchs bei MG)."""
    assert all("Other entries" not in p["name"] for p in PACKS["packs"])


def test_meta_rows_cover_all_combinations():
    assert len(ROWS) == sum(len(v["combinations"]) for v in VILLAINS)


@pytest.mark.parametrize("villain", VILLAINS, ids=lambda v: v["name"])
def test_villain_rules(villain):
    judge(V.villain_problems(villain), VILLAIN_STATUS.get(villain["name"], set()))


@pytest.mark.parametrize("villain,combo,raw", ROWS,
                         ids=[f"S{r['page']}-{v['name']}-{c['name']}" for v, c, r in ROWS])
def test_combination_rules(villain, combo, raw):
    judge(V.combo_problems(combo, raw, CODES), ROW_STATUS.get((raw["page"], combo["name"]), set()))


def test_corrections_only_where_documented():
    """Packs weichen nur dort von der PDF ab, wo eine begründete Korrektur in unsicher.md steht."""
    for _, c, r in ROWS:
        packs = [m["pack"] for m in c["modulars"]]
        pdf = [PACKS["spellingFixes"].get(p, p) for p in r["packs"]]
        if packs != pdf and None not in packs:
            assert "correction" in c, c["name"]
            assert "korrigiert" in ROW_STATUS[(r["page"], c["name"])], c["name"]


def test_total_combinations_over_600():
    if not FULL_RUN:
        pytest.skip(f"Teilextraktion (Seiten {FIRST}-{LAST})")
    assert len(ROWS) > 600


def test_every_page_assigned():
    assigned = {p for v in VILLAINS for p in v["pdfPages"]}
    assert set(range(max(FIRST, 2), LAST + 1)) <= assigned


def test_pdf_unchanged():
    assert hashlib.sha256((ROOT / META["source"]).read_bytes()).hexdigest() == META["sha256"]


# ---------------------------------------------------------------- Unabhängige Gegenzählung (PyMuPDF)

@pytest.mark.parametrize("page", range(max(FIRST, 2), LAST + 1))
def test_checkmarks_match_page(page):
    """✔-Zählung aus PyMuPDF == als recommended markierte Zeilen der Seite."""
    info = META["pages"][str(page)]
    assert info["images"] == 0, "Seite enthält Bilder – Häkchen könnten Grafiken sein"
    assert sum(c["recommended"] for _, c, r in ROWS if r["page"] == page) == info["checkmarks"]


@pytest.mark.parametrize("page", range(max(FIRST, 2), LAST + 1))
def test_row_count_matches_difficulty_tokens(page):
    """Zeilen pro Seite == Difficulty-Werte unter der „Difficulty“-Überschrift laut PyMuPDF."""
    rows = [(c, r) for _, c, r in ROWS if r["page"] == page]
    if not any(r["hasDifficultyColumn"] for _, r in rows):
        pytest.skip("Tabelle ohne Difficulty-Spalte")
    assert sum(c["difficulty"] is not None for c, _ in rows) == META["pages"][str(page)]["difficultyTokens"]


# ---------------------------------------------------------------- Determinismus

def test_rerun_is_identical(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "scripts" / "extract.py"),
                    "--pages", f"{FIRST}-{LAST}", "--out", str(tmp_path)],
                   check=True, capture_output=True)
    for name in ("packs.json", "villains.json", "extraction_meta.json", "unsicher.md"):
        assert (tmp_path / name).read_bytes() == (V.DATA / name).read_bytes(), name


# ---------------------------------------------------------------- Fixtures aus echten Seiten

def test_legend_page1():
    legend = {p["code"]: p["name"] for p in PACKS["packs"]}
    assert len(legend) == 18
    assert legend["CORE"] == "Marvel Champion Core Set"
    assert legend["MG"] == "Mutant Genesis Campaign Expansion"
    assert legend["FNE"] == "Fear No Evil"
    assert {"NOVA", "SP//DR", "MAGNETO"} <= set(PACKS["heroPacks"])
    assert not {"SP//dr", "MAGNTO"} & set(PACKS["heroPacks"])


def test_rhino():
    rhino = by_name("Rhino")
    assert rhino["expansion"] == "CORE SET"
    assert rhino["pdfPages"] == [2]
    assert len(rhino["combinations"]) == 15
    wab = combo(rhino, '"We are Breaking!"')
    assert mods(wab) == [("Symbiotic Strength", "SM")]
    assert (wab["difficulty"], wab["recommended"]) == (2, False)
    hh = combo(rhino, "Hydra Heist")
    assert mods(hh) == [("Hydra Assault", "RORS"), ("Ransacked Armory", "HOOD")]
    assert (hh["difficulty"], hh["recommended"]) == (2, True)
    default = [c for c in rhino["combinations"] if c["isDefault"]]
    assert [mods(c) for c in default] == [[("Bomb Scare", "CORE")]]


def test_ultron():
    ultron = by_name("Ultron")
    assert len(ultron["combinations"]) == 14
    default = [c for c in ultron["combinations"] if c["isDefault"]]
    assert [m["name"] for c in default for m in c["modulars"]] == ["Under Attack"]


def test_klaw_order_and_counts():
    klaw = by_name("Klaw")
    names = [c["name"] for c in klaw["combinations"]]
    assert names[0] == "Guards, Guards!" and names[-1] == "Boost Card Highscore"
    assert sum(c["recommended"] for c in klaw["combinations"]) == 5


# Sonderfälle, jeweils am Seitenbild geprüft

def test_two_villains_on_page_37():
    assert [v["name"] for v in VILLAINS if 37 in v["pdfPages"]] == ["SPIRAL", "MOJO"]
    assert len(by_name("Mojo")["combinations"]) == 4
    assert sum(c["isDefault"] for c in by_name("Spiral")["combinations"]) == 0


def test_hood_spans_two_pages():
    hood = by_name("The Hood")
    assert hood["pdfPages"] == [24, 25]
    assert all(len(c["modulars"]) == 7 for c in hood["combinations"])


def test_ebony_maw_12pt_heading():
    assert by_name("Ebony Maw")["expansion"] == "THE MAD TITAN’S SHADOW CAMPAIGN EXPANSION"


def test_italic_modular_note_separated():
    c = combo(by_name("Mansion Attack"), "Passing the Torch")
    assert mods(c) == [("Infinity Gauntlet", "MTS")]
    assert c["modularsNote"].startswith("(Due to the Permanent keyword")


def test_civil_war_name_and_schemes():
    c = combo(by_name("Iron Man"), "Solving Time Travel")
    assert c["mainSchemes"] == ["Cut Off Support (1B)", "No Going Back (2B)"]
    assert c["difficulty"] == -3
    reg = combo(by_name("Custom Registration Combos"), "Registration Avengers")
    assert reg["recommended"] and reg["difficulty"] is None
    assert reg["mainSchemes"] == ["Cut Off Support (1B)", "Mighty Avengers (2B)"]


def test_footnote_markers():
    c = combo(by_name("Crossbones"), "Here to Slay")
    assert [(m["name"], m.get("footnote")) for m in c["modulars"]] == [
        ("Ransacked Armory", "**"), ("Military Grade", "*"), ("Mutant Slayers", None)]
    assert by_name("Crossbones")["starMeaning"] == "a weapon within the mod set"
    assert by_name("Red Skull")["starMeaning"] == "a side scheme"


def test_released_flag():
    unreleased = [v["name"] for v in VILLAINS if not v["released"]]
    assert unreleased[0] == "BULLSEYE" and unreleased[-1] == "KINGPIN" and len(unreleased) == 10
    assert all(v["released"] for v in VILLAINS if v["pdfPages"][0] < 63)


def test_italic_subtitle_separated():
    c = combo(by_name("Stop the Presses!"), "Spider-Man Finally Snaps")
    assert c["subtitle"] == "“Guess I am a menace.”"


def test_red_skull_mechanics_not_merged_with_hint():
    rs = by_name("Red Skull")
    assert rs["mechanics"] == ["Side Schemes", "Attachments"]
    assert "Remember to separate the side schemes for the side deck!" in rs["pageNotes"]


def test_wrapped_placeholder_is_one_choice():
    c = combo(by_name("Magog"), "DEFAULT MODULAR")
    assert c["modulars"] == [{"name": "A random MojoMania modular set", "pack": "MOJO",
                              "type": "choice", "canonical": "A random MojoMania modular set"}]
    assert c["modularsNote"] == "(Crime, Fantasy, Horror, Sci-Fi, Sitcom, Western)"


# Übernommene Struktur des Zweitversuchs

def test_required_and_pools():
    assert by_name("Taskmaster")["required"] == ["Hydra Patrol"]
    assert by_name("Crossbones")["required"] == ["Experimental Weapons (for Side Deck)"]
    pools = by_name("Thunderbolts")["extraPools"]
    assert len(pools) == 1 and len(pools[0]["modulars"]) == 15 and pools[0]["modulars"][-1] == "Deadly Duo"
    assert [v["name"] for v in VILLAINS if v["type"] == "custom-combos"] == [
        "CUSTOM REGISTRATION COMBOS", "CUSTOM RESISTANCE COMBOS"]


def test_canonical_unifies_spelling_only():
    names = {m["canonical"] for v in VILLAINS for c in v["combinations"] for m in c["modulars"]}
    assert "Guerilla Tactics" not in names and "Down To Earth" not in names
    assert "Winter Soldier's Nemesis Set" in names and "Winter Soldier’s Nemesis" not in names


# Korrekturen des Nutzers (manual/corrections.json, 2026-10-21)

def test_user_corrections():
    assert mods(combo(by_name("Klaw"), "Vibranium Order")) == [("Children of Thanos", "MTS"), ("Black Order", "MTS")]
    assert mods(combo(by_name("Tower Defense (Proxima/Corvus)"), "Anti-Mutant Army")) == [
        ("Infinites", "APOC"), ("Genosha", "APOC")]
    prelate = combo(by_name("Unus"), "A New Prelate")
    assert prelate["modulars"][0] == {"name": "Deathstrike", "pack": "WOLV.", "type": "nemesis",
                                      "canonical": "Deathstrike"}
    assert [m["pack"] for m in combo(by_name("Captain America"), "Captain Venom")["modulars"]] == ["SM", "VENOM", "APOC"]
    assert [m["pack"] for m in combo(by_name("Spider-Woman"), "Self-Propelled Goblin Glider")["modulars"]] == [
        "NEXT", "GG", "GG"]
    assert mods(combo(by_name("Hammerhead"), "Stone Cold Stunner")) == [
        ("Beasty Boys", "HOOD"), ("Dystopian Nightmare", "APOC")]
    assert PACKS["aliases"] == {"FEAR": "FNE"}
    assert PACKS["combinedCodes"]["CW + SS"] == ["CW", "SS"]
    assert all(m["type"] == "nemesis" for v in VILLAINS for c in v["combinations"]
               for m in c["modulars"] if m["name"] == "Deathstrike")


def test_spelling_fixes():
    used = {m["pack"] for v in VILLAINS for c in v["combinations"] for m in c["modulars"]}
    assert not {"SP//dr", "MAGNTO"} & used
    capes = {m["canonical"] for v in VILLAINS for c in v["combinations"] for m in c["modulars"] if "Cape" in m["name"]}
    assert capes == {"Cape-Killers"}


def test_nothing_open():
    if not FULL_RUN:
        pytest.skip("Teilextraktion")
    assert [i for i in META["issues"] if i["status"] == "offen"] == []
