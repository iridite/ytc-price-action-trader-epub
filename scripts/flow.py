#!/usr/bin/env python3
"""Extract reading order + structure from the source PDF into build/flow.json + build/media/."""
import pymupdf, json, re, os, io
import tables as tbl
from PIL import Image

PW, PH = 549.065, 639.442
PAGE = pymupdf.Rect(0, 0, PW, PH)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "source.pdf")
MEDIA = os.path.join(ROOT, "build", "media")
os.makedirs(MEDIA, exist_ok=True)
os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)

doc = pymupdf.open(SRC)
SKIP_PAGES = {1} | set(range(3, 9))     # cover page + printed table of contents

TXT_MAP = {
    "\u201e": "\u2018", "\u201f": "\u2019",
    "\uf0b7": "\u2022", "\uf0a7": "\u2022", "\uf04a": ":)",
    "\uf020": " ", "\u00a0": " ", "\u00ad": "",
}
def fix(t):
    for a, b in TXT_MAP.items():
        t = t.replace(a, b)
    return t

WM = re.compile(r"^w{3}\.forexwinners\.(net|com)$", re.I)

def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# ---------------------------------------------------------------- clustering
def is_callout_box(d, total_drawings):
    # Single 0.72pt stroked outline rectangles around body text callout notes (e.g. p.85, p.195)
    return (d.get("fill") is None
            and round(d.get("width") or 0, 2) == 0.72
            and total_drawings <= 6
            and d["rect"].width >= 80 and d["rect"].height >= 22)

def find_clusters(pno, tol=8.0):
    page = doc[pno]
    drawings = [d for d in page.get_drawings() if 5 < d["rect"].y0 < PH - 10]
    boxes = []
    for d in drawings:
        if is_callout_box(d, len(drawings)):
            continue
        r = pymupdf.Rect(d["rect"]) & PAGE
        if r.is_empty or (r.width < 0.5 and r.height < 0.5):
            continue
        boxes.append(r)
    n = len(boxes)
    if n == 0:
        return []
    par = list(range(n))
    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    inf = [pymupdf.Rect(r.x0 - tol, r.y0 - tol, r.x1 + tol, r.y1 + tol) for r in boxes]
    for i in range(n):
        for j in range(i + 1, n):
            if inf[i].intersects(inf[j]):
                a, b = find(i), find(j)
                if a != b:
                    par[b] = a
    grp = {}
    for i in range(n):
        k = find(i)
        grp[k] = grp.get(k, pymupdf.Rect()).include_rect(boxes[i])
    return [g for g in grp.values() if g.width >= 80 and g.height >= 22]

# ---------------------------------------------------------------- helpers
FONT_ALIAS = {"TimesNewRoman": "Times-Roman", "TimesNewRoman,Bold": "Times-Bold",
              "TimesNewRoman,Italic": "Times-Italic", "TimesNewRoman,BoldItalic": "Times-BoldItalic"}

def canon_font(f):
    return FONT_ALIAS.get(f, f.replace("TimesNewRoman", "Times"))

BULLET_FONTS = ("Courier", "Symbol", "Wingdings")

def is_bullet_line(l):
    if not all(canon_font(sp["f"]) in BULLET_FONTS for sp in l["spans"]):
        return False
    t = "".join(sp["t"] for sp in l["spans"]).strip()
    return t in ("o", "\uf0b7", "\uf0a7", "\u2022")

def get_lines(page):
    out = []
    pending = None
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            if not [s for s in l["spans"] if s["text"].strip()]:
                continue
            spans = [{"t": s["text"], "f": s["font"], "s": round(s["size"], 2),
                      "bb": [round(v, 2) for v in s["bbox"]]} for s in l["spans"]]
            if pending:
                spans[0]["t"] = pending + " " + spans[0]["t"].lstrip()
                pending = None
            # A heading and body text sharing one baseline (Cambria then Times):
            # split, and push the body fragment onto the next line so it does not
            # end up inside the heading.
            cut = next((i + 1 for i in range(len(spans) - 1)
                        if "Cambria" in canon_font(spans[i]["f"])
                        and "Cambria" not in canon_font(spans[i + 1]["f"])
                        and spans[i + 1]["t"].strip()), None)
            if cut:
                pending = "".join(s["t"] for s in spans[cut:]).strip()
                spans = spans[:cut]
            bb = [min(s["bb"][0] for s in spans), min(s["bb"][1] for s in spans),
                  max(s["bb"][2] for s in spans), max(s["bb"][3] for s in spans)]
            out.append({"bbox": [round(v, 2) for v in bb], "spans": spans})
    if pending and out:
        out.append({"bbox": [39.0, out[-1]["bbox"][1] + 13.8, 300.0, out[-1]["bbox"][3] + 13.8],
                    "spans": [{"t": pending, "f": "Times-Roman", "s": 12.0,
                               "bb": [39.0, out[-1]["bbox"][1] + 13.8, 300.0, out[-1]["bbox"][3] + 13.8]}]})
    # a bullet glyph drawn as its own text run: fold it into the item text
    bullets = [l for l in out if is_bullet_line(l)]
    if bullets:
        keep = [l for l in out if not is_bullet_line(l)]
        for b in bullets:
            same = [l for l in keep if abs(l["bbox"][1] - b["bbox"][1]) < 6
                    and l["bbox"][0] > b["bbox"][0] + 2]
            if same:
                tgt = min(same, key=lambda l: l["bbox"][0])
            else:
                below = [l for l in keep if 0 < l["bbox"][1] - b["bbox"][1] < 22]
                tgt = min(below, key=lambda l: l["bbox"][1]) if below else None
            if tgt is None:
                keep.append(b)
                continue
            sp = tgt["spans"][0]
            sp["t"] = "\u2022 " + sp["t"]
            tgt["bbox"][0] = min(tgt["bbox"][0], b["bbox"][0])
        out = keep
    # Group spans within 4pt vertically onto the same baseline before sorting left-to-right,
    # otherwise 0.5pt ascent jitter reorders inline chunks (e.g. "– Body Relaxation & Mind").
    out.sort(key=lambda l: (l["bbox"][1], l["bbox"][0]))
    by_y, base_y = [], None
    for l in out:
        if base_y is None or abs(l["bbox"][1] - base_y) >= 4:
            by_y.append([l])
            base_y = l["bbox"][1]
        else:
            by_y[-1].append(l)
    out = [l for row in by_y for l in sorted(row, key=lambda r: r["bbox"][0])]
    # Nitro exports justified paragraphs as one block per word: fold fragments
    # that share a baseline back into a single line before run grouping.
    folded = []
    for l in out:
        if folded:
            p = folded[-1]
            gap = l["bbox"][0] - p["bbox"][2]
            if abs(l["bbox"][1] - p["bbox"][1]) < 4 and -2 <= gap <= 80:
                head = l["spans"][0]["t"][:1]
                prev = p["spans"][-1]["t"]
                if prev and not prev.endswith((" ", "-")) and head not in (" ", ",", ".", ";", ":", "!", "?", ")", "\u201d", "\u2019"):
                    l["spans"][0]["t"] = " " + l["spans"][0]["t"]
                p["spans"].extend(l["spans"])
                p["bbox"][2] = max(p["bbox"][2], l["bbox"][2])
                p["bbox"][3] = max(p["bbox"][3], l["bbox"][3])
                continue
        folded.append(l)
    return folded

def line_props(l):
    sz = max(s["s"] for s in l["spans"])
    fonts = {canon_font(s["f"]) for s in l["spans"]}
    txt = fix("".join(s["t"] for s in l["spans"]))
    return sz, fonts, txt

def all_bold(fs):
    return all("Bold" in f for f in fs)

def all_italic(fs):
    return all("Italic" in f for f in fs)

def inline_html(spans):
    parts = []
    for s in spans:
        t = fix(s["t"])
        f = canon_font(s["f"])
        b, i = "Bold" in f, "Italic" in f
        k = "bi" if (b and i) else "b" if b else "i" if i else "n"
        if parts and parts[-1][0] == k:
            parts[-1][1] += t
        else:
            parts.append([k, t])
    out = ""
    for k, t in parts:
        e = esc(t)
        if k == "b":    out += f"<strong>{e}</strong>"
        elif k == "i":  out += f"<em>{e}</em>"
        elif k == "bi": out += f"<strong><em>{e}</em></strong>"
        else:           out += e
    return out

CAP_RE = re.compile(r"^(Figure|Table|Chart|Diagram)\s+\d+[\.\d]*\s*[\u2013\u2014:.\-]", re.I)

def heading_kind(st, fonts, txt):
    sz, em, fam = st
    t = txt.strip()
    if not t:
        return None
    if sz >= 30:
        return "h_part"
    if sz >= 20:
        return "h_chapter" if re.match(r"^Chapter\s+", t, re.I) else "h_section"
    if 13.2 <= sz < 20 and em in ("b", "bi") and fam == "cambria":
        return "h_section"
    # Some 2-part section headings (e.g. 10.4) were typeset at 12.95pt instead of 14pt.
    if 12.5 <= sz < 20 and em in ("b", "bi") and fam == "cambria" \
            and re.match(r"^\d+\.\d+(?!\.\d)(?:\s*[-\u2013\u2014]|\s+[A-Z])", t):
        return "h_section"
    if abs(sz - 12.95) < 0.25 and em in ("b", "bi") and fam == "cambria":
        return None if re.match(r"^Volume\b", t, re.I) else "h_sub"
    if 11.5 <= sz <= 12.6 and em in ("b", "bi") and fam == "cambria":
        return "h_sub"
    if 11.5 <= sz <= 12.6 and em == "i" and len(t) < 90 and t[-1] not in ".,;:":
        # Exclude parenthetical remarks and wrapped continuation lines from headings.
        if t.startswith(("(", "-", "\u2013", "\u2014")) or (t.endswith(")") and "(" not in t):
            return None
        return "h_sub"
    if 9.3 <= sz <= 10.4 and em == "b" and len(t) < 60:
        return "h_small"
    return None

# ---------------------------------------------------------------- media
_counter = [0]
def emit_raster(xref):
    _counter[0] += 1
    name = f"img{_counter[0]:04d}.jpg"
    info = doc.extract_image(xref)
    im = Image.open(io.BytesIO(info["image"]))
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > 1500:
        k = 1500 / max(w, h)
        im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
    im.save(os.path.join(MEDIA, name), "JPEG", quality=88, optimize=True)
    return name, im.size

def emit_vector(page, rect, zoom=3.0):
    _counter[0] += 1
    name = f"vec{_counter[0]:04d}.png"
    r = pymupdf.Rect(rect.x0 - 4, rect.y0 - 4, rect.x1 + 4, rect.y1 + 4) & PAGE
    pix = page.get_pixmap(clip=r, matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    pix.save(os.path.join(MEDIA, name))
    return name, (pix.width, pix.height)

# ---------------------------------------------------------------- per page
def style_sig(l):
    """(size, emphasis-class, family) - emphasis is a majority vote so that a
    line carrying an inline bold/italic run keeps the paragraph's class."""
    sz = max(s["s"] for s in l["spans"])
    nb = ni = nn = 0
    for s in l["spans"]:
        f = canon_font(s["f"])
        n = len(s["t"])
        if "Bold" in f and "Italic" in f:
            nb += n; ni += n
        elif "Bold" in f:
            nb += n
        elif "Italic" in f:
            ni += n
        else:
            nn += n
    tot = max(sum(len(x["t"]) for x in l["spans"]), 1)
    bf, itf = nb / tot, ni / tot
    if bf > 0.6 and itf > 0.6:
        em = "bi"
    elif bf > 0.6:
        em = "b"
    elif itf > 0.6:
        em = "i"
    else:
        em = "n"
    fam = "cambria" if any("Cambria" in canon_font(s["f"]) for s in l["spans"]) else "times"
    return (round(sz, 1), em, fam)

LIST_MARK = re.compile(
    r"^(?:"
    r"[a-zA-Z][\)\.]|"             # a) b. A) B.
    r"\([a-zA-Z]\)|"              # (a) (b) (A)
    r"\d{1,3}[\)\.]|"             # 1) 2. 12)
    r"\(\d{1,3}\)|"               # (1) (2) (12)
    r"[ivxIVX]{1,4}[\)\.]|"       # i) ii. iv) VI)
    r"\([ivxIVX]{1,4}\)"          # (i) (ii) (iv)
    r")\s"
)

def starts_list_item(l):
    sp = l["spans"][0]
    if canon_font(sp["f"]) in ("Symbol", "Wingdings", "Courier"):
        return True
    t = "".join(x["t"] for x in l["spans"]).lstrip()
    return t.startswith("\u2022") or bool(LIST_MARK.match(t))

def build_runs(lines):
    """Group consecutive lines into vertically contiguous runs.

    Lines join when the style matches, or when the previous line ends mid-sentence
    and this one continues it - a justified line whose tail word is entirely bold
    or italic ("... Swing High or" / "Low.") changes the majority-vote emphasis
    without starting a new paragraph."""
    runs = []
    for l in lines:
        sig = style_sig(l)
        if runs:
            r = runs[-1]
            sz = max(sig[0], r["sig"][0])
            pitch = l["bbox"][1] - r["lines"][-1]["bbox"][1]
            prev_txt = "".join(x["t"] for x in r["lines"][-1]["spans"]).rstrip()
            cur_txt = "".join(x["t"] for x in l["spans"]).lstrip()
            pitch_ok = -2 < pitch < max(1.75 * sz, 18)
            x_ok = l["bbox"][0] > r["x0"] - 5
            unfinished = bool(prev_txt) and prev_txt[-1] not in '.!?:;"\u201d\u2019)]}\u2014\u2013\u2026'
            short_emph = len(cur_txt) <= 24 and sig[1] in ("b", "i", "bi")
            continues = cur_txt[:1].islower() or short_emph
            same_size = abs(sig[0] - r["sig"][0]) < 0.4
            # A line that continues the previous sentence needs no indent test:
            # continuation lines legitimately start left of the run's first line.
            # A size change means a heading or a different block, never a wrap.
            cont = pitch_ok and ((r["sig"] == sig and x_ok)
                                 or (unfinished and continues and same_size))
            if cont and starts_list_item(l):
                cont = False
            if cont:
                r["lines"].append(l)
                continue
        runs.append({"sig": sig, "x0": l["bbox"][0], "lines": [l]})
    return runs

def page_nodes(pno):
    page = doc[pno]
    lines = get_lines(page)
    rasters = []
    for inf in page.get_image_info(xrefs=True):
        b = pymupdf.Rect(inf["bbox"])
        if b.y0 > PH - 2 or b.y1 < 2 or b.y0 < -2:
            continue
        if b.width < 100 or b.height < 30:
            continue
        rasters.append((b, inf["xref"]))
    rasters.sort(key=lambda x: (x[0].y0, x[0].x0))
    clusters = [g for g in find_clusters(pno)
                if not any(g.intersects(pymupdf.Rect(b.x0 - 6, b.y0 - 6, b.x1 + 6, b.y1 + 6)) for b, _ in rasters)]
    covered = [b for b, _ in rasters] + list(clusters)

    def covered_by(bb):
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        return any(c.x0 - 2 <= cx <= c.x1 + 2 and c.y0 - 2 <= cy <= c.y1 + 2 for c in covered)

    page_drw = [d for d in page.get_drawings() if 5 < d["rect"].y0 < PH - 10]
    callout_rects = [d["rect"] for d in page_drw if is_callout_box(d, len(page_drw))]

    keep = [l for l in lines
            if not WM.match(fix("".join(s["t"] for s in l["spans"])).replace(" ", ""))
            and not covered_by(l["bbox"])
            and fix("".join(s["t"] for s in l["spans"])).strip()]

    # Fold small raster bullet icons (<=10x10 px, e.g. 6x6 square ■ bullets exported by Nitro)
    # into the following text line on the same baseline as a bullet item.
    b_imgs = [pymupdf.Rect(inf["bbox"]) for inf in page.get_image_info(xrefs=True)
              if inf["width"] <= 10 and inf["height"] <= 10 and 2 < inf["bbox"][1] < PH - 10
              and not covered_by(inf["bbox"])]
    for bi in b_imgs:
        bi_mid = (bi.y0 + bi.y1) / 2
        same = [l for l in keep if l["bbox"][1] - 3 <= bi_mid <= l["bbox"][3] + 1 and l["bbox"][0] > bi.x0 - 2]
        if same:
            tgt = min(same, key=lambda l: (l["bbox"][1], l["bbox"][0]))
        else:
            below = [l for l in keep if 0 < l["bbox"][1] - bi.y0 < 22 and l["bbox"][0] > bi.x0 - 2]
            tgt = min(below, key=lambda l: l["bbox"][1]) if below else None
        if tgt and not tgt["spans"][0]["t"].startswith("\u2022 "):
            tgt["spans"][0]["t"] = "\u2022 " + tgt["spans"][0]["t"]
            tgt["bbox"][0] = min(tgt["bbox"][0], bi.x0)

    # split at figures: keep runs from flowing across a figure
    figitems = [{"k": "fig", "y": b.y0, "src": ("raster", xref)} for b, xref in rasters] + \
               [{"k": "fig", "y": g.y0, "src": ("vector", g)} for g in clusters]
    figitems.sort(key=lambda x: x["y"])

    segments, cur = [], []
    fi = 0
    for l in keep:
        while fi < len(figitems) and figitems[fi]["y"] < l["bbox"][1]:
            if cur:
                segments.append(cur)
                cur = []
            segments.append([figitems[fi]])
            fi += 1
        cur.append(l)
    if cur:
        segments.append(cur)
    while fi < len(figitems):
        segments.append([figitems[fi]])
        fi += 1

    runs = []
    for seg in segments:
        if seg and isinstance(seg[0], dict) and seg[0].get("k") == "fig":
            runs.append(("fig", seg[0]))
        else:
            for r in build_runs(seg):
                runs.append(("run", r))

    out = []
    for kind, payload in runs:
        if kind == "fig":
            k, pl = payload["src"]
            if k == "vector":
                tnodes, _ = tbl.build(pno, pl, MEDIA, None)
                if tnodes:
                    for t in tnodes:
                        t["p"] = pno + 1
                        t["y"] = payload["y"]
                    out.extend(tnodes)
                    continue
            name, size = (emit_raster(pl) if k == "raster" else emit_vector(page, pl))
            out.append({"k": "fig", "src": name, "w": size[0], "h": size[1],
                        "p": pno + 1, "y": payload["y"]})
            continue
        r = payload
        sz = r["sig"][0]
        txt = " ".join(fix("".join(s["t"] for s in l["spans"])).strip() for l in r["lines"]).strip()
        txt = re.sub(r"\s+", " ", txt)
        bb0 = r["lines"][0]["bbox"]
        if CAP_RE.match(txt) and bb0[0] > 80 and len(txt) < 300:
            out.append({"k": "cap", "t": txt, "p": pno + 1, "y": bb0[1]})
            continue
        hk = None if starts_list_item(r["lines"][0]) else heading_kind(r["sig"], set(), txt)
        in_c = any(c.contains(pymupdf.Point((bb0[0] + max(l["bbox"][2] for l in r["lines"])) / 2, (bb0[1] + max(l["bbox"][3] for l in r["lines"])) / 2)) for c in callout_rects)
        if hk:
            node = {"k": hk, "t": txt, "p": pno + 1, "y": bb0[1], "x": r["x0"], "size": sz}
            if in_c:
                node["callout"] = True
            out.append(node)
            continue
        html_parts = []
        for i, l in enumerate(r["lines"]):
            if i:
                prevtxt = "".join(s["t"] for s in r["lines"][i - 1]["spans"]).rstrip()
                html_parts.append("" if prevtxt.endswith("-") else " ")
            html_parts.append(inline_html(l["spans"]))
        node = {"k": "p", "html": "".join(html_parts), "txt": txt,
                "x0": r["x0"], "x1": max(l["bbox"][2] for l in r["lines"]),
                "p": pno + 1, "y": bb0[1], "size": sz}
        if in_c:
            node["callout"] = True
        out.append(node)
    return out

def strip_tags(h):
    return re.sub(r"<[^>]+>", "", h)

# ---------------------------------------------------------------- main
RAW = os.path.join(ROOT, "build", "raw_pages.json")

def load_raw():
    if "--force" not in os.sys.argv and os.path.exists(RAW):
        print("reusing", RAW)
        return json.load(open(RAW))
    pages = {}
    for pno in range(doc.page_count):
        if pno + 1 in SKIP_PAGES:
            continue
        pages[str(pno + 1)] = page_nodes(pno)
        if (pno + 1) % 100 == 0:
            print("  page", pno + 1, flush=True)
    json.dump(pages, open(RAW, "w"))
    return pages

def main():
    raw = load_raw()
    nodes = []
    for pno in range(doc.page_count):
        if str(pno + 1) in raw:
            nodes.extend(raw[str(pno + 1)])

    # ---- cross page paragraph merge
    merged = 0
    i = 0
    while i < len(nodes) - 1:
        a, b = nodes[i], nodes[i + 1]
        if a["k"] == "p" and b["k"] == "p" and a["p"] != b["p"]:
            lastn = [n for n in nodes[:i + 1] if n["k"] == "p"]
            firstn = [n for n in nodes[:i + 2] if n["k"] == "p"]
            a_is_last = lastn and lastn[-1] is a
            b_is_first = firstn and firstn[-1] is b
            at = strip_tags(a["html"]).rstrip()
            bt = strip_tags(b["html"]).lstrip()
            if a_is_last and b_is_first and bt and bt[0].islower() and at and \
                    at[-1] not in '.!?:;"\u201d\u2019)]}\u2014\u2013\u2026' and \
                    abs(a["x0"] - b["x0"]) < 3:
                sep = "" if at.endswith("-") else " "
                a["html"] = a["html"].rstrip() + sep + b["html"].lstrip()
                a["txt"] = at + sep + bt
                a["p"] = b["p"]
                nodes.pop(i + 1)
                merged += 1
                continue
        i += 1
    print("merged across pages:", merged)

    json.dump(nodes, open(os.path.join(ROOT, "build", "flow.json"), "w"))
    from collections import Counter
    print("nodes:", len(nodes), Counter(n["k"] for n in nodes))

if __name__ == "__main__":
    tbl.init(SRC)
    main()
