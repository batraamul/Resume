"""Graphics for graphical resume templates: career timeline, bar, column, line, pie and donut charts, rating bars
and dots.

Everything is drawn at 300 dpi with Pillow using the bundled fonts, so the same
PNG is embedded in the Word file and the PDF and both look identical. Charts
are drawn only from recorded data (dates, counts, self-assessed levels); the
same facts always appear as real, selectable text next to the chart (legend or
caption), so nothing is available only inside an image.
"""

from __future__ import annotations

import io
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from ris.domain import dates
from ris.resources import fonts_dir

DPI = 300
_FONT_FILES = {
    ("Calibri", False): "Carlito-Regular.ttf", ("Calibri", True): "Carlito-Bold.ttf",
    ("Cambria", False): "Caladea-Regular.ttf", ("Cambria", True): "Caladea-Bold.ttf",
    ("Arial", False): "LiberationSans-Regular.ttf", ("Arial", True): "LiberationSans-Bold.ttf",
    ("Times New Roman", False): "LiberationSerif-Regular.ttf", ("Times New Roman", True): "LiberationSerif-Bold.ttf",
}


def px(pt: float) -> int:
    return max(1, int(round(pt / 72.0 * DPI)))


@lru_cache(maxsize=64)
def _font(logical: str, bold: bool, size_pt: float) -> ImageFont.FreeTypeFont:
    name = _FONT_FILES.get((logical, bold)) or _FONT_FILES[("Calibri", bold)]
    return ImageFont.truetype(str(fonts_dir() / name), px(size_pt))


@lru_cache(maxsize=8)
def _fallback(size_pt: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(fonts_dir() / "DejaVuSans.ttf"), px(size_pt))


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _mix(hex_colour: str, other: str, t: float) -> tuple[int, int, int]:
    a, b = _rgb(hex_colour), _rgb(other)
    return tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3))  # type: ignore[return-value]


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, dpi=(DPI, DPI))
    return buf.getvalue()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int, max_lines: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and draw.textlength(last + "…", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    # A single word wider than the column is shrunk by character truncation.
    out = []
    for ln in lines:
        while ln and draw.textlength(ln, font=font) > max_w:
            ln = ln[:-2] + "…"
        out.append(ln)
    return out


def _dotted_v(draw: ImageDraw.ImageDraw, x: int, y0: int, y1: int, colour, dot: int = 4, gap: int = 7) -> None:
    y = y0
    while y < y1:
        draw.line([(x, y), (x, min(y + dot, y1))], fill=colour, width=3)
        y += dot + gap


# --------------------------------------------------------------------------- rating bars


@lru_cache(maxsize=256)
def rating_bar(level: int, width_pt: float, height_pt: float, fill: str, track: str, segments: int = 5) -> bytes:
    """A discrete rating bar (``level`` of ``segments`` filled). Discrete steps avoid false precision."""
    w, h = px(width_pt), px(height_pt)
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    gap = max(2, int(h * 0.35))
    seg_w = (w - gap * (segments - 1)) / segments
    radius = max(1, int(h * 0.35))
    for i in range(segments):
        x0 = int(round(i * (seg_w + gap)))
        x1 = int(round(x0 + seg_w))
        colour = _rgb(fill) if i < level else _rgb(track)
        d.rounded_rectangle([x0, 0, x1, h - 1], radius=radius, fill=colour)
    return _png(img)


# --------------------------------------------------------------------------- career timeline


def _fmt(d: str) -> str:
    return dates.format_date(d, "mon_year") if d else ""


def timeline(points: list[tuple[str, str, str, bool, float]], width_pt: float, height_pt: float,
             palette: tuple[str, ...], font: str = "Calibri", text: str = "#1F1F1F", axis: str = "#7F8C8D",
             years_label: str = "Years in post") -> bytes:
    """Career timeline: one column per organisation, bar height = years in post.

    ``points`` are (label, start, end, is_current, years) in chronological order.
    """
    W, H = px(width_pt), px(height_pt)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    n = max(1, len(points))
    f_label = _font(font, True, 8.6 if n <= 6 else 7.6)
    f_date = _font(font, False, 7.4 if n <= 6 else 6.6)
    f_val = _font(font, True, 7.6 if n <= 6 else 6.8)
    f_axis = _font(font, False, 7.0)
    left, right = px(4), px(30)
    label_h = int(f_label.size * 1.2 * 2) + px(3)
    date_h = int(f_date.size * 1.25 * 2) + px(6)
    y_base = H - date_h
    top = label_h + px(4)
    plot_h = y_base - top - px(12)
    slot = (W - left - right) / n
    bar_w = int(min(slot * 0.56, px(48)))
    max_years = max((p[4] for p in points), default=1.0) or 1.0
    for i, (lab, start, end, current, years) in enumerate(points):
        colour = _rgb(palette[i % len(palette)])
        cx = int(left + slot * i + slot / 2)
        # organisation label (top, wrapped to two lines)
        lines = _wrap(d, lab, f_label, int(slot * 0.94), 2)
        ly = px(1)
        for ln in lines:
            tw = d.textlength(ln, font=f_label)
            d.text((cx - tw / 2, ly), ln, font=f_label, fill=colour)
            ly += int(f_label.size * 1.2)
        # bar
        bh = max(int(plot_h * (years / max_years)), px(6))
        x0, x1 = cx - bar_w // 2, cx + bar_w // 2
        d.rectangle([x0, y_base - bh, x1, y_base], fill=colour)
        # value above bar
        val = f"{years:g} yr" + ("" if years == 1 else "s")
        vw = d.textlength(val, font=f_val)
        vy = y_base - bh - int(f_val.size * 1.25)
        d.text((cx - vw / 2, vy), val, font=f_val, fill=colour)
        # dotted guide from label to value
        _dotted_v(d, cx, ly + px(2), vy - px(2), _mix(palette[i % len(palette)], "#FFFFFF", 0.35))
        # dates below the axis
        dy = y_base + px(5)
        for ln in (f"{_fmt(start)} –", "Present" if current else (_fmt(end) or "—")):
            tw = d.textlength(ln, font=f_date)
            d.text((cx - tw / 2, dy), ln, font=f_date, fill=colour)
            dy += int(f_date.size * 1.25)
    # time axis with arrowhead
    ax = _rgb(axis)
    t = px(2.2)
    d.rectangle([left, y_base - t // 2, W - right + px(6), y_base + t // 2], fill=ax)
    ah = px(4.5)
    tip = W - right + px(14)
    d.polygon([(tip, y_base), (tip - ah * 1.6, y_base - ah), (tip - ah * 1.6, y_base + ah)], fill=ax)
    # vertical "years" arrow on the right
    vx = W - px(10)
    d.rectangle([vx - px(1.4), top + px(8), vx + px(1.4), y_base - px(4)], fill=_rgb(text))
    d.polygon([(vx, top), (vx - px(4), top + px(9)), (vx + px(4), top + px(9))], fill=_rgb(text))
    lbl = Image.new("RGBA", (int(d.textlength(years_label, font=f_axis)) + 4, int(f_axis.size * 1.3)), (255, 255, 255, 0))
    ImageDraw.Draw(lbl).text((2, 0), years_label, font=f_axis, fill=_rgb(text))
    lbl = lbl.rotate(90, expand=True)
    ly0 = max(top, (top + y_base) // 2 - lbl.height // 2)
    img.paste(lbl, (vx - px(7) - lbl.width, ly0), lbl)
    return _png(img)


# --------------------------------------------------------------------------- publications by year


def stacked_years(points: list[tuple[str, str, float]], series: list[str], width_pt: float, height_pt: float,
                  palette: tuple[str, ...], font: str = "Calibri", text: str = "#1F1F1F", grid: str = "#E3E7EA",
                  muted: str = "#555555", legend: bool = True) -> bytes:
    """Stacked column chart: ``points`` are (year, series name, count)."""
    W, H = px(width_pt), px(height_pt)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_tick = _font(font, False, 7.2)
    f_val = _font(font, True, 7.4)
    f_leg = _font(font, False, 7.6)
    years = sorted({p[0] for p in points}, key=int)
    if not years:
        return _png(img)
    totals = {y: sum(c for yy, _, c in points if yy == y) for y in years}
    vmax = max(totals.values()) or 1
    step = 1 if vmax <= 6 else (2 if vmax <= 12 else 5)
    top_val = ((int(vmax) + step - 1) // step) * step
    # legend row
    lx = px(30)
    ly = px(2)
    sw = px(7)
    for i, s in enumerate(series if legend else []):
        colour = _rgb(palette[i % len(palette)])
        d.rectangle([lx, ly + 2, lx + sw, ly + 2 + sw], fill=colour)
        d.text((lx + sw + px(3), ly - 1), s, font=f_leg, fill=_rgb(text))
        lx += sw + px(3) + int(d.textlength(s, font=f_leg)) + px(12)
    top = (ly + sw + px(10)) if legend else px(10)
    left = px(26)
    bottom = H - int(f_tick.size * 1.6) - px(3)
    right = W - px(4)
    plot_h = bottom - top
    # grid and y ticks
    for v in range(0, top_val + 1, step):
        y = bottom - int(plot_h * v / top_val)
        d.line([(left, y), (right, y)], fill=_rgb(grid), width=2)
        tw = d.textlength(str(v), font=f_tick)
        d.text((left - px(4) - tw, y - f_tick.size // 2 - 2), str(v), font=f_tick, fill=_rgb(muted))
    slot = (right - left) / len(years)
    bw = int(min(slot * 0.58, px(28)))
    for i, y in enumerate(years):
        cx = int(left + slot * i + slot / 2)
        yb = bottom
        for si, s in enumerate(series):
            c = sum(cnt for yy, ss, cnt in points if yy == y and ss == s)
            if not c:
                continue
            h = int(plot_h * c / top_val)
            d.rectangle([cx - bw // 2, yb - h, cx + bw // 2, yb], fill=_rgb(palette[si % len(palette)]))
            yb -= h
        if totals[y]:
            val = f"{int(totals[y])}"
            tw = d.textlength(val, font=f_val)
            d.text((cx - tw / 2, yb - int(f_val.size * 1.25)), val, font=f_val, fill=_rgb(text))
        tw = d.textlength(y, font=f_tick)
        d.text((cx - tw / 2, bottom + px(2)), y, font=f_tick, fill=_rgb(muted))
    d.line([(left, bottom), (right, bottom)], fill=_rgb(muted), width=3)
    return _png(img)


# --------------------------------------------------------------------------- rating dots


@lru_cache(maxsize=256)
def rating_dots(level: int, width_pt: float, height_pt: float, fill: str, track: str, dots: int = 5) -> bytes:
    """``level`` of ``dots`` filled circles — an alternative to segmented bars."""
    w, h = px(width_pt), px(height_pt)
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    size = min(h, int(w / (dots * 1.6)))
    gap = (w - size * dots) / max(1, dots - 1) if dots > 1 else 0
    gap = min(gap, size * 0.9)
    y0 = (h - size) // 2
    for i in range(dots):
        x0 = int(round(i * (size + gap)))
        d.ellipse([x0, y0, x0 + size - 1, y0 + size - 1], fill=_rgb(fill) if i < level else _rgb(track))
    return _png(img)


# --------------------------------------------------------------------------- horizontal bars


def hbars(points: list[tuple[str, float, str]], width_pt: float, palette: tuple[str, ...], font: str = "Calibri",
          text: str = "#1F1F1F", muted: str = "#555555", track: str = "#E8ECEF", row_pt: float = 15.0,
          single_colour: bool = False) -> bytes:
    """Horizontal bar chart: ``points`` are (label, value, value label); height follows the number of rows."""
    n = max(1, len(points))
    W, H = px(width_pt), px(row_pt * n + 4)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_lab = _font(font, False, 8.0)
    f_val = _font(font, True, 7.8)
    label_w = int(W * 0.34)
    val_w = int(max((d.textlength(v, font=f_val) for _, _, v in points), default=0)) + px(6)
    x0 = label_w + px(6)
    x1 = W - val_w - px(2)
    vmax = max((v for _, v, _ in points), default=1.0) or 1.0
    row = px(row_pt)
    bar_h = int(row * 0.52)
    for i, (lab, val, vlab) in enumerate(points):
        colour = _rgb(palette[0 if single_colour else i % len(palette)])
        cy = px(2) + row * i + row // 2
        lines = _wrap(d, lab, f_lab, label_w, 1)
        tw = d.textlength(lines[0], font=f_lab) if lines else 0
        d.text((label_w - tw, cy - f_lab.size // 2 - 2), lines[0] if lines else "", font=f_lab, fill=_rgb(text))
        bw = max(px(2), int((x1 - x0) * (val / vmax)))
        d.rectangle([x0, cy - bar_h // 2, x0 + bw, cy + bar_h // 2], fill=colour)
        d.text((x0 + bw + px(3), cy - f_val.size // 2 - 2), vlab, font=f_val, fill=_rgb(muted))
    return _png(img)


# --------------------------------------------------------------------------- pie and donut


def pie(points: list[tuple[str, float]], width_pt: float, height_pt: float, palette: tuple[str, ...],
        font: str = "Calibri", text: str = "#1F1F1F", muted: str = "#555555", donut: bool = False,
        centre: str = "", unit: str = "") -> bytes:
    """Pie or donut chart of part-to-whole data, with a legend giving each part's value and percentage."""
    W, H = px(width_pt), px(height_pt)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    total = sum(v for _, v in points if v > 0) or 1.0
    f_leg = _font(font, False, 8.0)
    f_pct = _font(font, True, 8.0)
    f_centre = _font(font, True, 11.0)
    dia = min(H - px(6), int(W * 0.42))
    cx0, cy0 = px(4), (H - dia) // 2
    box = [cx0, cy0, cx0 + dia, cy0 + dia]
    angle = -90.0
    for i, (_, v) in enumerate(points):
        if v <= 0:
            continue
        sweep = 360.0 * v / total
        d.pieslice(box, angle, angle + sweep, fill=_rgb(palette[i % len(palette)]), outline="white", width=px(1.2))
        angle += sweep
    if donut:
        hole = int(dia * 0.30)
        d.ellipse([box[0] + hole, box[1] + hole, box[2] - hole, box[3] - hole], fill="white")
        if centre:
            tw = d.textlength(centre, font=f_centre)
            d.text((cx0 + dia / 2 - tw / 2, cy0 + dia / 2 - f_centre.size * 0.62), centre, font=f_centre,
                   fill=_rgb(text))
    # legend
    lx = cx0 + dia + px(14)
    line_h = int(f_leg.size * 1.55)
    ly = max(px(2), (H - line_h * len(points)) // 2)
    sw = px(7)
    for i, (lab, v) in enumerate(points):
        colour = _rgb(palette[i % len(palette)])
        d.rectangle([lx, ly + 3, lx + sw, ly + 3 + sw], fill=colour)
        pct = f"{100 * v / total:.0f}%"
        val = f"{v:g}{(' ' + unit) if unit else ''}"
        d.text((lx + sw + px(4), ly), pct, font=f_pct, fill=colour)
        pw = d.textlength("100%", font=f_pct) + px(6)
        room = W - (lx + sw + px(4) + pw) - px(2)
        lines = _wrap(d, f"{lab} ({val})", f_leg, int(room), 1)
        d.text((lx + sw + px(4) + pw, ly), lines[0] if lines else "", font=f_leg, fill=_rgb(text))
        ly += line_h
    return _png(img)


# --------------------------------------------------------------------------- columns and lines over time


def columns(points: list[tuple[str, float]], width_pt: float, height_pt: float, colour: str, font: str = "Calibri",
            text: str = "#1F1F1F", grid: str = "#E3E7EA", muted: str = "#555555") -> bytes:
    """Single-series column chart (for example, total publications per year)."""
    return stacked_years([(lab, "Total", v) for lab, v in points], ["Total"], width_pt, height_pt, (colour,), font=font,
                         text=text, grid=grid, muted=muted, legend=False)


def line(points: list[tuple[str, float]], width_pt: float, height_pt: float, colour: str, font: str = "Calibri",
         text: str = "#1F1F1F", grid: str = "#E3E7EA", muted: str = "#555555") -> bytes:
    """Line chart with marked, labelled points (for example, publications per year or cumulative totals)."""
    W, H = px(width_pt), px(height_pt)
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    f_tick = _font(font, False, 7.2)
    f_val = _font(font, True, 7.4)
    if not points:
        return _png(img)
    vmax = max(v for _, v in points) or 1
    step = 1 if vmax <= 6 else (2 if vmax <= 12 else (5 if vmax <= 40 else 10))
    top_val = ((int(vmax) + step - 1) // step) * step or step
    top, left = px(10), px(26)
    bottom = H - int(f_tick.size * 1.6) - px(3)
    right = W - px(8)
    plot_h = bottom - top
    for v in range(0, top_val + 1, step):
        y = bottom - int(plot_h * v / top_val)
        d.line([(left, y), (right, y)], fill=_rgb(grid), width=2)
        tw = d.textlength(str(v), font=f_tick)
        d.text((left - px(4) - tw, y - f_tick.size // 2 - 2), str(v), font=f_tick, fill=_rgb(muted))
    slot = (right - left) / len(points)
    xy = [(int(left + slot * i + slot / 2), bottom - int(plot_h * v / top_val)) for i, (_, v) in enumerate(points)]
    if len(xy) > 1:
        d.line(xy, fill=_rgb(colour), width=px(1.6), joint="curve")
    r = px(2.4)
    for (x, y), (lab, v) in zip(xy, points, strict=True):
        d.ellipse([x - r, y - r, x + r, y + r], fill=_rgb(colour))
        val = f"{v:g}"
        tw = d.textlength(val, font=f_val)
        d.text((x - tw / 2, y - r - int(f_val.size * 1.3)), val, font=f_val, fill=_rgb(text))
        tw = d.textlength(lab, font=f_tick)
        d.text((x - tw / 2, bottom + px(2)), lab, font=f_tick, fill=_rgb(muted))
    d.line([(left, bottom), (right, bottom)], fill=_rgb(muted), width=3)
    return _png(img)


def image_size_pt(data: bytes) -> tuple[float, float]:
    with Image.open(io.BytesIO(data)) as im:
        w, h = im.size
    return w * 72.0 / DPI, h * 72.0 / DPI


_ = _fallback
