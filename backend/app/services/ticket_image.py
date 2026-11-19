"""The saved/downloaded ticket: a PNG styled like a real ticket, with a main section, a
perforated tear line with notches, and a tear-off stub holding the entry QR code.

The QR payload is exactly what the app shows (JSON with code/order/event), so the door scanner
reads a saved image the same way. Generated on demand, never stored.
"""
import io
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"

W, H = 1080, 1920
CARD_X, CARD_W = 70, 940
CARD_Y = 110
RADIUS = 40
NOTCH = 34

BG = (12, 10, 18)
PAPER = (251, 248, 242)
INK = (24, 20, 32)
MUTED = (120, 112, 132)
PRIMARY = (168, 85, 247)
PRIMARY_DARK = (88, 28, 135)
SUCCESS = (22, 163, 74)


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONTS / f"Inter-{weight}.otf"), size)
    except OSError:
        return ImageFont.load_default(size=size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while draw.textlength(lines[-1] + "…", font=font) > width and " " in lines[-1]:
            lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] += "…"
    return lines


def _fit(draw, text: str, font, width: int) -> str:
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def _background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    glow = Image.new("RGB", (W, H), BG)
    g = ImageDraw.Draw(glow)
    g.ellipse((-300, -200, 900, 900), fill=PRIMARY_DARK)
    g.ellipse((500, 1300, 1500, 2300), fill=(60, 20, 100))
    return Image.blend(img, glow.filter(ImageFilter.GaussianBlur(220)), 0.85)


def _cover(cover: bytes | None, size: tuple[int, int]) -> Image.Image:
    if cover:
        try:
            with Image.open(io.BytesIO(cover)) as im:
                im.load()
                return ImageOps.fit(im.convert("RGB"), size, Image.LANCZOS)
        except Exception:
            pass
    # No cover (or unreadable): a brand gradient.
    grad = Image.new("RGB", size, PRIMARY)
    d = ImageDraw.Draw(grad)
    for y in range(size[1]):
        t = y / size[1]
        d.line([(0, y), (size[0], y)], fill=(int(168 - 90 * t), int(85 - 60 * t), int(247 - 120 * t)))
    return grad


def _qr(payload: str, size: int) -> Image.Image:
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=1, box_size=10)
    q.add_data(payload)
    q.make(fit=True)
    return q.make_image(fill_color=INK, back_color=PAPER).convert("RGB").resize((size, size), Image.NEAREST)


def render_ticket(*, event_title: str, start: datetime, timezone_name: str | None, venue: str, address: str,
                  city: str, tier: str, quantity: int, holder: str, ticket_code: str, order_id: str,
                  event_id: str, status: str, checked_in_at: datetime | None = None, fast_lane: bool = False,
                  cover: bytes | None = None) -> bytes:
    img = _background()
    card_h = H - CARD_Y - 150
    # Card with rounded corners (mask) on the background.
    card = Image.new("RGB", (CARD_W, card_h), PAPER)
    d = ImageDraw.Draw(card)

    # ── Cover band ─────────────────────────────────────────────────────────────
    cover_h = 420
    card.paste(_cover(cover, (CARD_W, cover_h)), (0, 0))
    shade = Image.new("L", (CARD_W, cover_h), 0)
    sd = ImageDraw.Draw(shade)
    for y in range(cover_h):
        sd.line([(0, y), (CARD_W, y)], fill=int(170 * max(0, (y - cover_h * 0.35) / (cover_h * 0.65))))
    card.paste(Image.new("RGB", (CARD_W, cover_h), (10, 6, 16)), (0, 0), shade)
    d.text((48, 40), "turnup", font=_font("Black", 52), fill=(255, 255, 255))
    admit = f"ADMIT {quantity}"
    af = _font("Black", 34)
    aw = int(d.textlength(admit, font=af)) + 48
    d.rounded_rectangle((CARD_W - 48 - aw, 40, CARD_W - 48, 100), radius=30, fill=PRIMARY)
    d.text((CARD_W - 48 - aw + 24, 51), admit, font=af, fill=(255, 255, 255))
    if fast_lane:
        ff = _font("Black", 30)
        fw = int(d.textlength("FAST LANE", font=ff)) + 40
        d.rounded_rectangle((CARD_W - 48 - fw, 116, CARD_W - 48, 168), radius=26, fill=(255, 255, 255))
        d.text((CARD_W - 48 - fw + 20, 125), "FAST LANE", font=ff, fill=PRIMARY_DARK)

    # ── Main section ───────────────────────────────────────────────────────────
    x, y = 56, cover_h + 44
    tf = _font("Black", 60)
    for line in _wrap(d, event_title, tf, CARD_W - 112, 3):
        d.text((x, y), line, font=tf, fill=INK)
        y += 72
    y += 24
    tz = ZoneInfo(timezone_name) if timezone_name else ZoneInfo("Africa/Lagos")
    local = (start if start.tzinfo else start.replace(tzinfo=timezone.utc)).astimezone(tz)
    where = address if (not city or city.lower() in address.lower()) else f"{address}, {city}"
    grid = [[("DATE", local.strftime("%a %d %b %Y")), ("TIME", local.strftime("%I:%M %p").lstrip("0"))],
            [("VENUE", venue)],
            [("ADDRESS", where)],
            [("TICKET", f"{tier} × {quantity}"), ("HOLDER", holder)]]
    lf, vf = _font("Bold", 24), _font("Bold", 36)
    full_w = CARD_W - 112
    col_w = (full_w - 40) // 2
    for row in grid:
        for j, (label, value) in enumerate(row):
            cx = x + j * (col_w + 40)
            d.text((cx, y), label, font=lf, fill=MUTED)
            d.text((cx, y + 32), _fit(d, value or "", vf, full_w if len(row) == 1 else col_w), font=vf, fill=INK)
        y += 100

    # ── Perforation ────────────────────────────────────────────────────────────
    perf_y = max(y + 30, card_h - 560)
    for px in range(NOTCH + 20, CARD_W - NOTCH - 20, 34):
        d.line([(px, perf_y), (px + 18, perf_y)], fill=(200, 192, 208), width=4)

    # ── Stub ───────────────────────────────────────────────────────────────────
    qr_size = 360
    qy = perf_y + 70
    payload = json.dumps({"code": ticket_code, "order": order_id, "event": event_id}, separators=(",", ":"))
    card.paste(_qr(payload, qr_size), (56, qy))
    sx = 56 + qr_size + 44
    d.text((sx, qy), "SCAN AT THE DOOR", font=_font("Black", 30), fill=PRIMARY_DARK)
    code_f = _font("Medium", 30)
    parts = ticket_code.upper().split("-")
    lines = [" ".join(parts[:2]), " ".join(parts[2:4]), " ".join(parts[4:])] if len(parts) == 5 else textwrap.wrap(ticket_code.upper(), 14)
    cy = qy + 56
    for ln in lines:
        d.text((sx, cy), ln, font=code_f, fill=INK)
        cy += 40
    d.text((sx, cy + 18), "ORDER", font=lf, fill=MUTED)
    d.text((sx, cy + 48), order_id[:8].upper(), font=_font("Bold", 34), fill=INK)
    badge, colour = ("CHECKED IN", MUTED) if checked_in_at else (("VALID", SUCCESS) if status == "confirmed" else (status.upper(), MUTED))
    bf = _font("Black", 30)
    bw = int(d.textlength(badge, font=bf)) + 40
    by = qy + qr_size - 56
    d.rounded_rectangle((sx, by, sx + bw, by + 56), radius=12, outline=colour, width=4)
    d.text((sx + 20, by + 10), badge, font=bf, fill=colour)
    d.text((56, qy + qr_size + 30), "One scan admits everyone on this ticket. Don't share it publicly.",
           font=_font("Medium", 24), fill=MUTED)

    # Rounded card + perforation notches cut out of the sides.
    mask = Image.new("L", (CARD_W, card_h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, CARD_W - 1, card_h - 1), radius=RADIUS, fill=255)
    md.ellipse((-NOTCH, perf_y - NOTCH, NOTCH, perf_y + NOTCH), fill=0)
    md.ellipse((CARD_W - NOTCH, perf_y - NOTCH, CARD_W + NOTCH, perf_y + NOTCH), fill=0)
    shadow = Image.new("L", (W, H), 0)
    shadow.paste(mask, (CARD_X + 10, CARD_Y + 18))
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(18)).point(lambda v: v * 0.6))
    img.paste(card, (CARD_X, CARD_Y), mask)

    foot = ImageDraw.Draw(img)
    ft = "Saved from Turnup · show this at the door"
    ff = _font("Medium", 26)
    foot.text(((W - foot.textlength(ft, font=ff)) / 2, H - 100), ft, font=ff, fill=(200, 190, 215))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()
