"""Graphics for graphical resume templates: career timeline, publications-by-year chart and rating bars.

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
                  muted: str = "#555555") -> bytes:
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
    for i, s in enumerate(series):
        colour = _rgb(palette[i % len(palette)])
        d.rectangle([lx, ly + 2, lx + sw, ly + 2 + sw], fill=colour)
        d.text((lx + sw + px(3), ly - 1), s, font=f_leg, fill=_rgb(text))
        lx += sw + px(3) + int(d.textlength(s, font=f_leg)) + px(12)
    top = ly + sw + px(10)
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


def image_size_pt(data: bytes) -> tuple[float, float]:
    with Image.open(io.BytesIO(data)) as im:
        w, h = im.size
    return w * 72.0 / DPI, h * 72.0 / DPI


_ = _fallback
