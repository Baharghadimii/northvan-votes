"""Printable cards with a QR code, for the all-candidates meetings.

Eight to a Letter sheet, cut along the guides. Deliberately plain: a card that
looks like campaign material would be the wrong thing to leave on a seat at a
candidates meeting.
"""

from pathlib import Path

import qrcode
from qrcode.image.pil import PilImage
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT = Path(__file__).parent / "northvanvotes-cards.pdf"
QR_PNG = Path(__file__).parent / "qr.png"
URL = "https://northvanvotes.ca"

INK = HexColor("#1b1915")
MUTED = HexColor("#5c564b")
ACCENT = HexColor("#0f5f54")
RULE = HexColor("#cbc2b0")


def make_qr() -> Path:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,  # survives a crease
        box_size=14,
        border=1,
    )
    qr.add_data(URL)
    qr.make(fit=True)
    img = qr.make_image(image_factory=PilImage, fill_color="#1b1915", back_color="white")
    img.save(QR_PNG)
    return QR_PNG


def draw_card(c: canvas.Canvas, x: float, y: float, w: float, h: float, qr: Path) -> None:
    pad = 7 * mm
    qr_size = 26 * mm

    c.drawImage(str(qr), x + pad, y + h - pad - qr_size, qr_size, qr_size)

    tx = x + pad + qr_size + 6 * mm
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(tx, y + h - pad - 9, "North Van Votes")

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.6)
    for i, line in enumerate([
        "All 59 candidates, sorted by issue.",
        "Read what each one actually said",
        "about housing, traffic or schools —",
        "in their own words, with sources.",
    ]):
        c.drawString(tx, y + h - pad - 23 - i * 9.6, line)

    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(tx, y + pad + 11, "northvanvotes.ca")

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.4)
    c.drawString(tx, y + pad + 2, "Free · no ads · not affiliated with any candidate")


def main() -> None:
    qr = make_qr()
    c = canvas.Canvas(str(OUT), pagesize=letter)
    page_w, page_h = letter

    cols, rows = 2, 4
    margin = 12 * mm
    cw = (page_w - 2 * margin) / cols
    ch = (page_h - 2 * margin) / rows

    for r in range(rows):
        for col in range(cols):
            x = margin + col * cw
            y = page_h - margin - (r + 1) * ch
            draw_card(c, x, y, cw, ch, qr)
            c.setStrokeColor(RULE)
            c.setLineWidth(0.4)
            c.setDash(2, 3)
            c.rect(x, y, cw, ch, stroke=1, fill=0)

    c.setDash()
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawString(margin, margin - 5 * mm, "Cut along the dotted lines. 8 cards per sheet.")
    c.showPage()
    c.save()
    QR_PNG.unlink(missing_ok=True)
    print(f"  {OUT.name} — 8 cards per sheet, QR points to {URL}")


if __name__ == "__main__":
    main()
