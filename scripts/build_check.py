"""Erzeugt check.html: extrahierte Tabellen neben gerenderten PDF-Seiten (check/pages/*.png)."""
import html

import pymupdf

import validate as V

OUT_DIR = V.ROOT / "check" / "pages"
DPI = 110


def render_pages(pdf_path, pages):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    for p in pages:
        doc[p - 1].get_pixmap(dpi=DPI).save(OUT_DIR / f"page-{p:02d}.png")


def fmt_diff(c):
    d = c["difficulty"]
    if d is None:
        return "–"
    return (f"+{d}" if d >= 0 else str(d)) + ("?" if c["difficultySpeculative"] else "")


def row_class(probs, statuses):
    """CSS-Klasse + Text: rot = undokumentiert, gelb = offen, blau = korrigiert, grün = bestätigt."""
    if probs and not statuses:
        return "bad", probs
    if "offen" in statuses:
        return "unsure", probs or ["offen in unsicher.md"]
    if "korrigiert" in statuses:
        return "fixed", probs or ["korrigiert"]
    if "bestätigt" in statuses:
        return "ok", probs or ["bestätigt"]
    return "", probs


def main():
    e = html.escape
    packs = V.load("packs.json")
    villains = V.load("villains.json")
    meta = V.load("extraction_meta.json")
    codes = V.known_codes(packs)
    row_status = V.row_statuses(meta)
    villain_status = V.villain_statuses(meta)
    rows_by_villain = {}
    for v, c, r in V.rows_with_combos(villains, meta):
        rows_by_villain.setdefault(r["villain"], []).append((c, r))
    pages = sorted({p for v in villains for p in v["pdfPages"]})
    render_pages(V.ROOT / meta["source"], pages)

    parts, counts = [], {"bad": 0, "unsure": 0, "fixed": 0, "ok": 0}
    for vi, v in enumerate(villains):
        rows = []
        for c, r in rows_by_villain.get(vi, []):
            cls, probs = row_class(V.combo_problems(c, r, codes), row_status.get((r["page"], c["name"]), set()))
            if cls:
                counts[cls] += 1
            mods = "<br>".join(
                e(m["name"]) + (f"<sup>{e(m['footnote'])}</sup>" if m.get("footnote") else "")
                + (f' <span class="tag">{m["type"]}</span>' if m["type"] != "modular" else "")
                for m in c["modulars"])
            if c.get("modularsNote"):
                mods += f'<br><i class="note">{e(c["modularsNote"])}</i>'
            name = (e(c["name"]) + (f'<br><i class="scheme">{e(c["subtitle"])}</i>' if c.get("subtitle") else "")
                    + "".join(f'<br><span class="scheme">{e(s)}</span>' for s in c.get("mainSchemes", [])))
            final = [m["pack"] or "–" for m in c["modulars"]]
            pk = "<br>".join(e(p) for p in final)
            if final != r["packs"]:
                pk += f'<br><span class="note">PDF: {e(" / ".join(r["packs"]) or "leer")}</span>'
            tags = " ".join(t for t, on in (("✔", c["recommended"]), ("DEFAULT", c["isDefault"])) if on)
            info = "; ".join(probs) + (f" → {c['correction']}" if c.get("correction") else "")
            rows.append(
                f'<tr class="{cls}"><td>S.{r["page"]}</td><td>{name}</td><td>{mods}</td><td>{fmt_diff(c)}</td>'
                f'<td>{e(c["notes"])}</td><td>{pk}</td><td>{tags}</td><td>{e(info)}</td></tr>')
        vcls, vprobs = row_class(V.villain_problems(v), villain_status.get(v["name"], set()))
        vp = f'<p class="{vcls}">{e("; ".join(vprobs))}</p>' if vprobs else ""
        imgs = "".join(f'<img loading="lazy" src="check/pages/page-{p:02d}.png" alt="Seite {p}">' for p in v["pdfPages"])
        extra = "".join(f"<br><b>Required:</b> {e(x)}" for x in v["required"])
        if v.get("starMeaning"):
            extra += f"<br><b>* =</b> {e(v['starMeaning'])}"
        extra += "".join(f"<br><b>Hinweis:</b> {e(x)}" for x in v["pageNotes"])
        extra += "".join(f"<br><b>{e(pl['title'])}:</b> {e(', '.join(pl['modulars']))}" for pl in v.get("extraPools", []))
        badges = (' <span class="spec">UNRELEASED</span>' if not v["released"] else "") + \
                 (' <span class="spec">CUSTOM COMBOS</span>' if v["type"] == "custom-combos" else "")
        parts.append(f"""
<section id="v{vi}">
  <h2>{e(v['name'])}{badges} <small>{e(v['expansion'])} · S. {', '.join(map(str, v['pdfPages']))} · {len(v['combinations'])} Kombinationen</small></h2>
  {vp}
  <p><b>Themes:</b> {e(', '.join(v['themes']))}<br><b>Mechanics:</b> {e(', '.join(v['mechanics']))}{extra}</p>
  <div class="pair">
    <table><thead><tr><th>S.</th><th>Name</th><th>Modular Sets</th><th>Diff.</th><th>Notes</th><th>Packs</th><th></th><th>Prüfung</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table>
    <div class="pdf">{imgs}</div>
  </div>
</section>""")

    toc = " · ".join(f'<a href="#v{i}">{e(v["name"])}</a>' for i, v in enumerate(villains))
    legend = "".join(f"<li><b>{e(p['code'])}</b> = {e(p['name'])}</li>" for p in packs["packs"])
    total = sum(len(v["combinations"]) for v in villains)
    doc = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Extraktion prüfen</title>
<style>
body {{ font: 13px/1.4 system-ui, sans-serif; margin: 16px; background: #fff; color: #222; }}
.pair {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; align-items: start; }}
table {{ border-collapse: collapse; width: 100%; }}
td, th {{ border: 1px solid #bbb; padding: 3px 5px; vertical-align: top; }}
th {{ background: #444; color: #fff; text-align: left; }}
tr.bad td, p.bad {{ background: #ffd6d6; }}
tr.fixed td, p.fixed {{ background: #d6e8ff; }}
tr.ok td, p.ok {{ background: #dcf5dc; }}
.tag {{ font-size: 10px; background: #eee; padding: 0 3px; }}
tr.unsure td, p.unsure {{ background: #fff0c2; }}
p.bad, p.unsure, p.fixed, p.ok {{ padding: 4px; }}
.pdf {{ position: sticky; top: 0; }}
.pdf img {{ width: 100%; border: 1px solid #999; margin-bottom: 8px; }}
.scheme, .note {{ color: #555; font-size: 12px; }}
.spec {{ background: #ddd; font-size: 11px; padding: 1px 4px; }}
section {{ border-top: 3px solid #444; margin-top: 24px; }}
small {{ font-weight: normal; color: #666; }}
</style></head><body>
<h1>Extraktion prüfen</h1>
<p>Quelle: {e(meta['source'])} · Seiten {meta['pageRange'][0]}–{meta['pageRange'][1]} · {len(villains)} Villains · {total} Kombinationen ·
<span style="background:#ffd6d6">rot = Prüfregel verletzt, nicht dokumentiert</span> ({counts['bad']}) ·
<span style="background:#fff0c2">gelb = offen</span> ({counts['unsure']}) ·
<span style="background:#d6e8ff">blau = von dir korrigiert</span> ({counts['fixed']}) ·
<span style="background:#dcf5dc">grün = von dir bestätigt</span> ({counts['ok']})</p>
<details><summary>Pack-Legende ({len(packs['packs'])}) · Hero-Packs: {e(', '.join(packs['heroPacks']))} · Aliasse: {e(', '.join(f'{k} = {v}' for k, v in packs['aliases'].items()))} · Kombi-Kürzel: {e(', '.join(packs['combinedCodes']))}</summary><ul>{legend}</ul></details>
<p>{toc}</p>
{''.join(parts)}
</body></html>
"""
    (V.ROOT / "check.html").write_text(doc, encoding="utf-8", newline="\n")
    print(f"check.html: {len(villains)} Villains, Zeilen rot/gelb/blau/grün = "
          f"{counts['bad']}/{counts['unsure']}/{counts['fixed']}/{counts['ok']}, {len(pages)} Seitenbilder")


if __name__ == "__main__":
    main()
