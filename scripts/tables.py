"""Rebuild the 8 picture-tables (pattern reference tables) as text + per-row diagrams.

The source PDF draws each pattern diagram wide enough to overlap the adjacent
text column, so a plain page crop reproduces overlapping glyphs. Here the row
text is extracted to HTML and the diagram is re-rendered with the text removed.
"""
import pymupdf, re

PAGE = pymupdf.Rect(0, 0, 549.065, 639.442)
TEXT_COL_X = 376.0          # right text column starts here
_en = [None, None]
_counter = [0]

def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

CELL_W = 345.6          # width of the left cell's row separators

def _is_row_rule(r):
    return r.height < 1.5 and abs(r.width - CELL_W) < 3 and abs(r.x0 - 28.2) < 3

def _bands(page, cluster):
    rules = []
    for d in page.get_drawings():
        r = pymupdf.Rect(d["rect"]) & PAGE
        if _is_row_rule(r) and cluster.contains(pymupdf.Point(r.x0, r.y0)):
            rules.append(r)
    if len(rules) < 3:
        return None
    ys = sorted({round(r.y0, 1) for r in rules})
    edges = [cluster.y0] + [y for y in ys if cluster.y0 + 2 < y < cluster.y1 - 2] + [cluster.y1]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1) if edges[i + 1] - edges[i] > 8]

def _words(page, y0, y1):
    left, right = [], []
    for w in page.get_text("words"):
        x0, wy0, x1, wy1, txt = w[0], w[1], w[2], w[3], w[4]
        cy = (wy0 + wy1) / 2
        if not (y0 <= cy <= y1):
            continue
        (right if x0 >= TEXT_COL_X else left).append((round(wy0, 1), x0, txt))
    def render(items):
        lines = {}
        for wy, x, t in items:
            lines.setdefault((wy, x >= TEXT_COL_X), []).append((x, t))
        out, prev = [], None
        for (wy, _), ws in sorted(lines.items()):
            ws.sort()
            s = " ".join(t for _, t in ws)
            if prev is not None and 0 < wy - prev <= 19:
                out[-1] += ("" if out[-1].endswith("-") else " ") + s
            else:
                out.append(s)
            prev = wy
        return [re.sub(r"\s+", " ", x).strip() for x in out]
    return render(left), render(right)

def _erase_divider(path, clip, zoom, div_x=374.0, half=1.2):
    """The table's column rule falls inside the diagram crop; paint it out."""
    px = (div_x - clip.x0) * zoom
    if px < 2 or px > (clip.x1 - clip.x0) * zoom - 2:
        return
    from PIL import Image, ImageDraw
    im = Image.open(path).convert("RGB")
    d = ImageDraw.Draw(im)
    d.rectangle([px - half * zoom, 0, px + half * zoom, im.size[1]], fill=(255, 255, 255))
    im.save(path)

def build(page_no, cluster, media_dir, emit_png):
    """Return (nodes, note) or (None, None) when the cluster is not a table."""
    global _en
    page = _en[0][page_no]
    bands = _bands(page, cluster)
    if not bands:
        return None, None

    rd = _en[1][page_no]
    for b in rd.get_text("blocks"):
        bb = pymupdf.Rect(b[:4])
        if cluster.contains(pymupdf.Point((bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2)):
            rd.add_redact_annot(bb)
    rd.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                        text=pymupdf.PDF_REDACT_TEXT_REMOVE)

    nodes = []
    for y0, y1 in bands:
        band = pymupdf.Rect(cluster.x0, y0, cluster.x1, y1)
        # diagram = drawings inside the band, excluding cell borders/rules
        u = None
        for d in page.get_drawings():
            r = pymupdf.Rect(d["rect"]) & band
            if r.is_empty or r.width > 300:
                continue
            # cell borders / row rules run along the band edges or column edges
            if r.height < 2 and (abs(r.y0 - y0) < 2 or abs(r.y1 - y1) < 2):
                continue
            if r.width < 2 and any(abs(v) < 2 for v in (r.x0 - 28, r.x1 - 374, r.x1 - 507)):
                continue
            if r.width < 2 and r.height > 0.6 * (y1 - y0):
                continue        # column divider spanning the whole row
            if not band.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2)):
                continue
            u = r if u is None else u | r
        if u is not None:
            u = pymupdf.Rect(u.x0 - 3, max(u.y0 - 3, y0), u.x1 + 3, min(u.y1 + 3, y1))
        if u is not None and (u.width < 40 or u.height < 18):
            u = None            # link underline etc., not a diagram
        left, right = _words(page, y0, y1)
        if u is not None and not u.is_empty:
            _counter[0] += 1
            name = f"ptr{_counter[0]:04d}.png"
            pix = rd.get_pixmap(clip=u, matrix=pymupdf.Matrix(4, 4), alpha=False)
            pix.save(f"{media_dir}/{name}")
            _erase_divider(f"{media_dir}/{name}", u, 4)
            nodes.append({"k": "timg", "src": name, "w": pix.width, "h": pix.height})
        for t in left:
            nodes.append({"k": "tp", "html": _esc(t), "role": "left"})
        for i, t in enumerate(right):
            nodes.append({"k": "tp", "html": _esc(t), "role": "name" if i == 0 else "body"})
    return nodes, None

def init(src):
    _en[0] = pymupdf.open(src)
    _en[1] = pymupdf.open(src)
