#!/usr/bin/env python3
"""Build a reflowable EPUB 3 from build/flow.json + build/media.

Targets both WeChat Read (微信读书) and Apple Books:
  * EPUB 3.0 package (spec requires version="3.0" for any 3.x content)
  * both nav.xhtml (EPUB 3) and toc.ncx (EPUB 2 fallback) in the spine
  * mimetype stored first, uncompressed
  * one XHTML file per section group, hard cap ~110 KB each
  * no embedded fonts, minimal CSS so readers can override
"""
import json, os, re, shutil, zipfile, hashlib, uuid
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
OUT = os.path.join(ROOT, "dist")
MEDIA = os.path.join(BUILD, "media")

TITLE = "YTC Price Action Trader"
SUBTITLE = "Intraday Swing Trading for the Forex, FX Futures and Emini Futures Markets"
CREATOR = "Lance Beggs"
LANG = "en"
FILE_LIMIT = 80_100           # bytes of XHTML per file (safely below WeChat Read's ~100KB split limit)

SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on",
               "or", "the", "to", "vs", "with", "within", "from", "into"}
NUMWORD = ("One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|Eleven|Twelve|"
           "Thirteen|Fourteen|Fifteen|Sixteen|Seventeen|Eighteen")

def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def titlecase(s):
    words = s.split()
    out = []
    for i, w in enumerate(words):
        if w.isupper() and len(w) > 1:
            lw = w.lower()
            out.append(lw if (0 < i < len(words) - 1 and lw in SMALL_WORDS) else lw.capitalize())
        else:
            out.append(w)
    return " ".join(out)

def norm_sep(t):
    t = re.sub(r"\s+", " ", t).strip()
    # "3.1- Introduction" / "1.5 - Feeback" -> "3.1 – Introduction"
    m = re.match(r"^(\d+(?:\.\d+)*)\s*[-\u2013\u2014]\s*(.+)$", t)
    if m:
        return f"{m.group(1)} \u2013 {m.group(2)}"
    m = re.match(r"^(\d+(?:\.\d+)*)\s+(.+)$", t)
    if m:
        return f"{m.group(1)} \u2013 {m.group(2)}"
    m = re.match(r"^(Chapter\s+(?:%s|\d+))\s*[-\u2013\u2014]\s*(.+)$" % NUMWORD, t, re.I)
    if m:
        return f"{m.group(1)} \u2013 {m.group(2)}"
    return t

# --------------------------------------------------------------- load
nodes = json.load(open(os.path.join(BUILD, "flow.json")))

# ---- merge wrapped headings -------------------------------------------------
merged = []
for n in nodes:
    if n["k"] in ("h_part", "h_chapter", "h_section", "h_sub", "h_small"):
        if merged:
            p = merged[-1]
            if p["k"] == "h_part" and n["k"] == "h_part" and p.get("p") == n.get("p"):
                p["t"] = p["t"] + " " + n["t"]
                continue
            if p["k"] in ("h_chapter", "h_section", "h_sub", "h_small") and n["k"] == p["k"]:
                if p.get("p") == n.get("p") and (n["y"] - p["y"]) < max(1.6 * n.get("size", 12), 20):
                    p["t"] = p["t"] + " " + n["t"]
                    continue
            # 26pt chapter line followed by its second 26pt line ("Chapter Four –" + rest)
            if p["k"] in ("h_chapter", "h_section") and n["k"] in ("h_chapter", "h_section", "h_part"):
                if p.get("p") == n.get("p") and abs(p.get("size", 0) - n.get("size", 0)) < 0.6 \
                        and (n["y"] - p["y"]) < max(1.6 * n.get("size", 12), 20):
                    p["t"] = p["t"] + " " + n["t"]
                    p["k"] = "h_chapter" if "h_chapter" in (p["k"], n["k"]) else p["k"]
                    continue
    merged.append(dict(n))
nodes = merged

# ---- repair layout artefacts -------------------------------------------------
# (a) a lone bullet glyph drawn as its own text run
fixed = []
for n in nodes:
    if n["k"] == "p" and n.get("txt", "").strip() in ("\u2022", "o", "\u00b7") and len(n["txt"].strip()) == 1:
        if fixed and fixed[-1]["k"] == "p" and abs(n.get("y", 0) - fixed[-1].get("y", 0)) < 4:
            prev = fixed[-1]
            if not prev["html"].lstrip().startswith("\u2022"):
                prev["html"] = "\u2022 " + prev["html"].lstrip()
                prev["txt"] = "\u2022 " + prev["txt"].lstrip()
            continue
    fixed.append(n)
nodes = fixed

# (b) a sentence broken into several paragraph objects by the original layout
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
TERM = ".!?:;\u201d\u2019)\u2026"
merged_any = True
rounds = 0
while merged_any and rounds < 3:
    merged_any = False
    rounds += 1
    out2 = []
    i2 = 0
    while i2 < len(nodes):
        a = nodes[i2]
        b = nodes[i2 + 1] if i2 + 1 < len(nodes) else None
        if (a["k"] == "p" and b is not None and b["k"] == "p"
                and a.get("p") == b.get("p")
                and abs(a.get("x0", 0) - b.get("x0", 0)) < 10
                and not b.get("txt", "").lstrip().startswith("\u2022")
                and not LIST_MARK.match(b.get("txt", "").lstrip())):
            at = a["txt"].rstrip()
            bt = b["txt"].lstrip()
            joinable = False
            if bt and (bt[0].islower() or bt[0] in ".,;:("):
                joinable = at and at[-1] not in "!?:;\u201d\u2019)"
            if joinable:
                sep = "" if at.endswith("-") else " "
                a["html"] = a["html"].rstrip() + sep + b["html"].lstrip()
                a["txt"] = at + sep + bt
                out2.append(a)
                merged_any = True
                i2 += 2
                continue
        out2.append(a)
        i2 += 1
    nodes = out2

for n in nodes:
    if n["k"] == "h_part":
        t = titlecase(n["t"])
        m = re.match(r"^(Volume\s+\w+)\s+(.*)$", t, re.I)
        n["t"] = f"{m.group(1)} \u2013 {m.group(2)}" if m else t
    elif n["k"] == "h_chapter":
        n["t"] = norm_sep(n["t"])
    elif n["k"] == "h_section":
        n["t"] = norm_sep(n["t"])

# ---- attach captions to figures --------------------------------------------
out = []
for n in nodes:
    if n["k"] == "cap":
        for back in range(1, 4):
            if len(out) - back < 0:
                break
            prev = out[-back]
            if prev["k"] == "fig" and "cap" not in prev:
                prev["cap"] = n["t"]
                break
        else:
            out.append(n)
        continue
    out.append(dict(n))
nodes = out

# ---- group bullet paragraphs into lists -----------------------------------
grouped = []
for n in nodes:
    if n["k"] == "p" and n.get("txt", "").lstrip().startswith("\u2022"):
        body = re.sub(r'^\s*\u2022\s*', '', n["html"])
        if grouped and grouped[-1]["k"] == "ul":
            grouped[-1]["items"].append(body)
        else:
            grouped.append({"k": "ul", "items": [body], "p": n["p"]})
        continue
    grouped.append(n)
nodes = grouped

# --------------------------------------------------------------- structure
XHTML_HEAD = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{lang}" xml:lang="{lang}">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="../css/style.css"/>
</head>
<body>
"""
XHTML_TAIL = "</body>\n</html>\n"

class File:
    def __init__(self, fid, name, title):
        self.id, self.name, self.title = fid, name, title
        self.body = []
        self.size = len(XHTML_HEAD.format(lang=LANG, title=esc(title)).encode()) + len(XHTML_TAIL.encode())
    def add(self, html):
        self.body.append(html)
        self.size += len(html.encode()) + 1

files, toc = [], []      # toc: (level, title, file, anchor)

def new_file(prefix, title):
    idx = sum(1 for f in files if f.name.startswith(prefix)) + 1
    f = File(f"{prefix}-{idx:02d}", f"{prefix}-{idx:02d}.xhtml", title)
    files.append(f)
    return f

def render(n, anchor=None):
    k = n["k"]
    if k == "fig":
        img = esc(n["src"])
        alt = esc(n.get("cap") or "")
        wh = f' width="{n["w"]}" height="{n["h"]}"'
        if n.get("cap"):
            # caption as a block-level <p>: renderers that ignore figcaption
            # (WeChat Read's own HTML tree) otherwise run it into the image.
            return (f'<figure class="fig"><img src="../media/{img}" alt="{alt}"{wh}/>'
                    f'<p class="figcap">{alt}</p></figure>')
        return f'<figure class="fig"><img src="../media/{img}" alt=""{wh}/></figure>'
    if k == "timg":
        img = esc(n["src"])
        return (f'<figure class="fig"><img src="../media/{img}" alt="" '
                f'width="{n["w"]}" height="{n["h"]}"/></figure>')
    if k == "tp":
        cls = {"name": ' class="pname"', "body": ' class="pbody"', "left": ' class="pleft"'}[n["role"]]
        return f"<p{cls}>{n['html']}</p>"
    if k == "ul":
        items = "".join(f"<li>{x}</li>" for x in n["items"])
        return f'<ul class="b">{items}</ul>'
    if k == "cap":
        return f'<p class="figcap">{esc(n["t"])}</p>'
    if k == "p":
        cls = ""
        x0 = n.get("x0", 0)
        if x0 > 104:
            cls = ' class="i3"'
        elif x0 > 88:
            cls = ' class="i2"'
        elif x0 > 50:
            cls = ' class="i1"'
        return f"<p{cls}>{n['html']}</p>"
    if k == "h_part":
        return f'<h1 class="part">{esc(n["t"])}</h1>'
    if k == "h_chapter":
        return f'<h1 class="chap">{esc(n["t"])}</h1>'
    if k == "h_section":
        a = f' id="{anchor}"' if anchor else ""
        return f'<h2{a}>{esc(n["t"])}</h2>'
    if k == "h_sub":
        a = f' id="{anchor}"' if anchor else ""
        return f'<h3{a}>{esc(n["t"])}</h3>'
    if k == "h_small":
        return f'<h4>{esc(n["t"])}</h4>'
    return ""

# ---- front matter (everything before the first volume title page) ----------
i = 0
while i < len(nodes) and nodes[i]["k"] != "h_part":
    i += 1
front = nodes[:i]
if front:
    f = new_file("front", "About the Author")
    for n in front:
        if n["k"] == "h_section":
            toc.append((1, n["t"], f, None))
            f.add(f'<h1>{esc(n["t"])}</h1>')
        else:
            f.add(render(n))

# ---- volumes / chapters / sections ----------------------------------------
sec_no = 0
sub_no = 0
chap_f = None
cur_f = None
NUM_SEC_RE = re.compile(r"^\d+\.\d+(?!\.\d)\b")
NUM_SUB_RE = re.compile(r"^\d+\.\d+\.\d+")

def emit_chapter(chap_nodes):
    global sec_no, sub_no
    head = chap_nodes[0]
    # Segment chapter into atomic TOC-anchored units so we can look ahead before
    # exceeding FILE_LIMIT and only ever split at a real nav entry (never mid-section).
    units = [{"title": head["t"], "items": [(None, None, None, render(head))], "only_sec_head": False, "is_sec": False}]
    for m in chap_nodes[1:]:
        t = (m.get("t") or "").strip()
        if m["k"] == "h_section" and NUM_SEC_RE.match(t):
            sec_no += 1
            anchor = f"s{sec_no}"
            units.append({"title": m["t"], "items": [(3, anchor, m["t"], render(m, anchor))], "only_sec_head": True, "is_sec": True})
        elif m["k"] == "h_sub" and NUM_SUB_RE.match(t):
            sub_no += 1
            anchor = f"x{sub_no}"
            if units[-1]["only_sec_head"]:
                # Keep an immediately following x.y.z subsection attached to its parent h_section.
                units[-1]["items"].append((4, anchor, m["t"], render(m, anchor)))
                units[-1]["only_sec_head"] = False
            else:
                units.append({"title": m["t"], "items": [(4, anchor, m["t"], render(m, anchor))], "only_sec_head": False, "is_sec": False})
        else:
            units[-1]["items"].append((None, None, None, render(m)))
            units[-1]["only_sec_head"] = False

    def unit_bytes(u):
        return sum(len(html.encode()) + 1 for _, _, _, html in u["items"])

    f = new_file("ch", head["t"])
    toc.append((2, head["t"], f, None))
    for idx_u, u in enumerate(units):
        need = unit_bytes(u)
        if u["is_sec"]:
            # If the whole section fits in one file, avoid stranding its intro in the previous file.
            j_u = idx_u + 1
            sec_total = need
            while j_u < len(units) and not units[j_u]["is_sec"]:
                sec_total += unit_bytes(units[j_u])
                j_u += 1
            if sec_total + 400 <= FILE_LIMIT:
                need = sec_total
        if len(f.body) > 1 and f.size + need > FILE_LIMIT:
            f = new_file("ch", u["title"])
        for lv, anchor, title, html in u["items"]:
            if lv is not None:
                toc.append((lv, title, f, anchor))
            f.add(html)
    return f

while i < len(nodes):
    n = nodes[i]
    if n["k"] == "h_part":
        f = new_file("part", n["t"])
        toc.append((1, n["t"], f, None))
        f.add(f'<h1 class="part">{esc(n["t"])}</h1>')
        chap_f = cur_f = None
        i += 1
        continue
    if n["k"] == "h_chapter":
        j = i + 1
        while j < len(nodes) and nodes[j]["k"] not in ("h_part", "h_chapter"):
            j += 1
        cur_f = chap_f = emit_chapter(nodes[i:j])
        i = j
        continue
    if cur_f is None:
        cur_f = new_file("ch", n.get("t", TITLE))
        toc.append((2, "Front matter", cur_f, None))
    cur_f.add(render(n))
    i += 1

# --------------------------------------------------------------- assets
def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)

CSS = """@charset "utf-8";
html, body { margin: 0; padding: 0; }
body { padding: 0 0.55em; line-height: 1.55; text-align: justify;
       -webkit-hyphens: auto; hyphens: auto;
       overflow-wrap: break-word; word-wrap: break-word; }
h1, h2, h3, h4 { text-align: left; line-height: 1.3; page-break-after: avoid; break-after: avoid; }
h1.part { font-size: 1.9em; text-align: center; margin: 30% 0 0 0; letter-spacing: 0.04em; }
body.coverpage { padding: 0; margin: 0; }
div.cover { margin: 0; padding: 0; text-align: center; }
div.cover img { max-width: 100%; height: auto; }
h1.chap { font-size: 1.55em; margin: 1.6em 0 1em 0; }
h2 { font-size: 1.28em; margin: 1.7em 0 0.7em 0; }
h3 { font-size: 1.1em; margin: 1.4em 0 0.55em 0; font-style: italic; }
h4 { font-size: 1em; margin: 1.2em 0 0.4em 0; }
p { margin: 0 0 0.75em 0; text-indent: 0; }
p.i1 { margin-left: 1.1em; }
p.i2 { margin-left: 2.2em; }
p.i3 { margin-left: 3.3em; }
ul.b { margin: 0 0 0.75em 0; padding-left: 1.5em; }
ul.b li { margin: 0.25em 0; }
figure.fig { margin: 1.1em 0; padding: 0; text-align: center; page-break-inside: avoid; break-inside: avoid; }
figure.fig img { max-width: 100%; height: auto; }
figure.fig figcaption { font-size: 0.86em; font-style: italic; text-align: center;
                        margin-top: 0.45em; line-height: 1.35; }
p.pname { font-weight: bold; margin: 0.9em 0 0.25em 0; }
p.pbody { margin: 0 0 0.6em 0; }
p.pleft { font-size: 0.92em; margin: 0 0 0.4em 0; }
p.figcap { font-size: 0.86em; font-style: italic; text-align: center; margin: 0.3em 0 1.1em 0; }
strong { font-weight: bold; }
em { font-style: italic; }
nav#toc ol { list-style: none; margin: 0; padding-left: 0.9em; }
nav#toc > ol { padding-left: 0; }
nav#toc li { margin: 0.28em 0; }
nav#toc a { text-decoration: none; }
"""

CONTAINER = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles>
<rootfile full-path="EPUB/content.opf" media-type="application/oebps-package+xml"/>
</rootfiles>
</container>
"""

def build_tree():
    root = {"level": 0, "kids": [], "title": "", "href": ""}
    stack = [root]
    for lv, title, f, anchor in toc:
        node = {"level": lv, "title": title, "kids": [],
                "href": f"text/{f.name}" + (f"#{anchor}" if anchor else "")}
        while len(stack) > 1 and stack[-1]["level"] >= lv:
            stack.pop()
        stack[-1]["kids"].append(node)
        stack.append(node)
    return root

def build_nav():
    root = build_tree()
    def ol(node):
        if not node["kids"]:
            return ""
        parts = ["<ol>"]
        for k in node["kids"]:
            sub = ol(k)
            parts.append(f'<li><a href="{esc(k["href"])}">{esc(k["title"])}</a>{sub}</li>')
        parts.append("</ol>")
        return "".join(parts)
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<!DOCTYPE html>',
           f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{LANG}" xml:lang="{LANG}">',
           '<head><meta charset="utf-8"/><title>Contents</title>',
           '<link rel="stylesheet" type="text/css" href="css/style.css"/></head>',
           '<body>',
           '<nav epub:type="toc" id="toc"><h1>Contents</h1>',
           ol(root),
           '</nav>',
           '<nav epub:type="landmarks" id="landmarks" hidden="hidden"><h2>Landmarks</h2><ol>',
           '<li><a epub:type="cover" href="text/cover.xhtml">Cover</a></li>',
           '<li><a epub:type="toc" href="nav.xhtml">Contents</a></li>',
           f'<li><a epub:type="bodymatter" href="text/{files[0].name}">{esc(files[0].title)}</a></li>',
           '</ol></nav>',
           '</body></html>']
    return "\n".join(out)

def build_ncx():
    root = build_tree()
    counter = [0]
    buf = ['<?xml version="1.0" encoding="utf-8"?>',
           '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">',
           '<head>',
           f'<meta name="dtb:uid" content="{BOOK_ID}"/>',
           f'<meta name="dtb:depth" content="{max(lv for lv, *_ in toc)}"/>',
           '<meta name="dtb:totalPageCount" content="0"/>',
           '<meta name="dtb:maxPageNumber" content="0"/>',
           '</head>',
           f'<docTitle><text>{esc(TITLE)}</text></docTitle>',
           f'<docAuthor><text>{esc(CREATOR)}</text></docAuthor>',
           '<navMap>']
    def emit(node):
        for k in node["kids"]:
            counter[0] += 1
            n = counter[0]
            buf.append(f'<navPoint id="np{n}" playOrder="{n}"><navLabel><text>{esc(k["title"])}</text></navLabel><content src="{esc(k["href"])}"/>')
            emit(k)
            buf.append("</navPoint>")
    emit(root)
    buf.append("</navMap></ncx>")
    return "\n".join(buf)

# --------------------------------------------------------------- write
def main():
    global BOOK_ID
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    src = os.path.join(OUT, "_src")
    os.makedirs(os.path.join(src, "META-INF"), exist_ok=True)
    os.makedirs(os.path.join(src, "EPUB", "text"), exist_ok=True)
    os.makedirs(os.path.join(src, "EPUB", "css"), exist_ok=True)
    os.makedirs(os.path.join(src, "EPUB", "media"), exist_ok=True)

    # cover: take the full-page image embedded in the PDF front page
    import pymupdf
    _doc = pymupdf.open(os.path.join(ROOT, "source.pdf"))
    _best = max(_doc[0].get_image_info(xrefs=True), key=lambda i: i["width"] * i["height"])
    _info = _doc.extract_image(_best["xref"])
    # WeChat Read shelf uses 128:185 (~0.692) aspect ratio. Raw cover (492x636, ~0.774)
    # is wider than the shelf card, causing WeChat to center-crop the sides.
    # Pad top and bottom with native header/footer background colors to prevent any cropping.
    from PIL import Image
    import io
    _raw_cov = Image.open(io.BytesIO(_info["image"]))
    _tw, _th = _raw_cov.width, int(round(_raw_cov.width / (128 / 185))) # 492 x 711
    _pad_top = (_th - _raw_cov.height) // 2
    _top_c = _raw_cov.getpixel((_raw_cov.width // 2, 0))
    _bot_c = _raw_cov.getpixel((_raw_cov.width // 2, _raw_cov.height - 1))
    _padded_cov = Image.new("RGB", (_tw, _th), _top_c)
    _padded_cov.paste(_raw_cov, (0, _pad_top))
    _bot_rect = Image.new("RGB", (_tw, _th - _raw_cov.height - _pad_top), _bot_c)
    _padded_cov.paste(_bot_rect, (0, _pad_top + _raw_cov.height))
    _padded_cov.save(os.path.join(src, "EPUB", "media", "cover.jpg"), quality=95)
    _cov_w, _cov_h = _tw, _th
    used = set()
    for f in files:
        used.update(re.findall(r"\.\./media/([\w.\-]+)", "".join(f.body)))
    for name in sorted(used):
        shutil.copy(os.path.join(MEDIA, name), os.path.join(src, "EPUB", "media", name))

    # xhtml
    for f in files:
        write(os.path.join(src, "EPUB", "text", f.name),
              XHTML_HEAD.format(lang=LANG, title=esc(f.title)) + "\n".join(f.body) + "\n" + XHTML_TAIL)
    write(os.path.join(src, "EPUB", "text", "cover.xhtml"),
          XHTML_HEAD.format(lang=LANG, title=esc(TITLE)).replace("<body>", '<body class="coverpage">') +
          f'<div class="cover"><img src="../media/cover.jpg" alt="Cover" width="{_cov_w}" height="{_cov_h}"/></div>\n' +
          XHTML_TAIL)

    # opf
    mod = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = []
    manifest.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')
    manifest.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    manifest.append('<item id="css" href="css/style.css" media-type="text/css"/>')
    manifest.append('<item id="cover_xhtml" href="text/cover.xhtml" media-type="application/xhtml+xml"/>')
    manifest.append('<item id="cover_img" href="media/cover.jpg" media-type="image/jpeg" properties="cover-image"/>')
    for name in sorted(used):
        mt = "image/png" if name.endswith(".png") else "image/jpeg"
        manifest.append(f'<item id="{name.replace(".", "_")}" href="media/{name}" media-type="{mt}"/>')
    for f in files:
        manifest.append(f'<item id="{f.name.replace(".", "_")}" href="text/{f.name}" media-type="application/xhtml+xml"/>')
    spine = ['<itemref idref="cover_xhtml"/>', '<itemref idref="nav"/>']
    spine += [f'<itemref idref="{f.name.replace(".", "_")}"/>' for f in files]

    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{LANG}" prefix="ibooks: http://vocabulary.itunes.apple.com/rdf/ibooks/vocabulary-extensions-1.0/">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{BOOK_ID}</dc:identifier>
<dc:title id="title">{esc(TITLE)}</dc:title>
<meta refines="#title" property="title-type">main</meta>
<dc:title id="subtitle">{esc(SUBTITLE)}</dc:title>
<meta refines="#subtitle" property="title-type">subtitle</meta>
<dc:creator id="creator">{esc(CREATOR)}</dc:creator>
<meta refines="#creator" property="role" scheme="marc:relators">aut</meta>
<meta refines="#creator" property="file-as">Beggs, Lance</meta>
<dc:language>{LANG}</dc:language>
<dc:date>2010-01-01</dc:date>
<dc:publisher>YourTradingCoach.com</dc:publisher>
<dc:subject>Finance</dc:subject>
<dc:subject>Trading</dc:subject>
<dc:subject>Technical analysis</dc:subject>
<dc:description>Price action trading: market analysis, the YTC Price Action Trader strategy, trade examples and trading business management.</dc:description>
<dc:rights>Copyright 2010 Lance Beggs. All rights reserved.</dc:rights>
<meta name="cover" content="cover_img"/>
<meta property="dcterms:modified">{mod}</meta>
<meta property="schema:accessMode">textual</meta>
<meta property="schema:accessMode">visual</meta>
<meta property="schema:accessModeSufficient">textual</meta>
<meta property="schema:accessibilityFeature">structuralNavigation</meta>
<meta property="schema:accessibilityFeature">tableOfContents</meta>
<meta property="schema:accessibilityFeature">readingOrder</meta>
<meta property="schema:accessibilityHazard">none</meta>
<meta property="schema:accessibilitySummary">Reflowable text with captioned images; no text is conveyed by images alone except scanned charts, which are duplicated by surrounding prose.</meta>
</metadata>
<manifest>
{chr(10).join(manifest)}
</manifest>
<spine toc="ncx">
{chr(10).join(spine)}
</spine>
<guide>
<reference type="toc" title="Contents" href="nav.xhtml"/>
<reference type="cover" title="Cover" href="text/cover.xhtml"/>
<reference type="text" title="Start" href="text/{files[0].name}"/>
</guide>
</package>
"""
    write(os.path.join(src, "EPUB", "content.opf"), opf)
    write(os.path.join(src, "EPUB", "nav.xhtml"), build_nav())
    write(os.path.join(src, "EPUB", "toc.ncx"), build_ncx())
    write(os.path.join(src, "EPUB", "css", "style.css"), CSS)
    write(os.path.join(src, "META-INF", "container.xml"), CONTAINER)

    # zip
    out_path = os.path.join(OUT, "YTC Price Action Trader.epub")
    with zipfile.ZipFile(out_path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for base, _, names in os.walk(src):
            for nm in sorted(names):
                p = os.path.join(base, nm)
                rel = os.path.relpath(p, src).replace(os.sep, "/")
                ct = zipfile.ZIP_STORED if rel.endswith((".jpg", ".png")) else zipfile.ZIP_DEFLATED
                z.write(p, rel, compress_type=ct)
    print("files:", len(files), "media:", len(used), "toc:", len(toc))
    print("epub:", out_path, round(os.path.getsize(out_path) / 1048576, 2), "MB")
    big = [f for f in files if f.size > FILE_LIMIT * 1.25]
    if big:
        print("!! oversized files:", [(f.name, f.size) for f in big])

BOOK_ID = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, "ytc-price-action-trader/" + CREATOR))

if __name__ == "__main__":
    main()
