"""Deterministic retained invoice PDF rendering for ADR 0091."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase.pdfdoc import TimeStamp
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK = colors.HexColor("#18211D")
MUTED = colors.HexColor("#56605A")
ACCENT = colors.HexColor("#1F604B")
ACCENT_PALE = colors.HexColor("#E7F0EC")
RULE = colors.HexColor("#C7CCC8")
HEADER = colors.HexColor("#EEF1EE")


def _text(value: object) -> str:
    return escape(str(value or "").strip())


def _multiline(value: object) -> str:
    return _text(value).replace("\n", "<br/>")


def _date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.strftime('%b')} {parsed.day}, {parsed.year}"


def _quantity(value: object) -> str:
    try:
        rendered = format(Decimal(str(value)), "f")
    except (InvalidOperation, ValueError):
        return _text(value)
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _address(identity: Mapping[str, object]) -> str:
    lines = [_text(identity.get("address_line_1")), _text(identity.get("address_line_2"))]
    city = _text(identity.get("city"))
    region = _text(identity.get("region"))
    postal = _text(identity.get("postal_code"))
    locality = " ".join(part for part in (region, postal) if part)
    if city and locality:
        locality = f"{city}, {locality}"
    elif city:
        locality = city
    country = _text(identity.get("country_code"))
    return "<br/>".join(part for part in (*lines, locality, country) if part)


def _issued_timestamp(value: str) -> TimeStamp:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    parsed = parsed.astimezone(UTC)
    stamp = TimeStamp(invariant=1)
    stamp.t = parsed.timestamp()
    stamp.lt = parsed.utctimetuple()
    stamp.YMDhms = (parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second)
    stamp.dhh = stamp.dmm = 0
    stamp.tzname = "UTC"
    return stamp


def render_invoice_pdf(
    *,
    number: str,
    invoice_date: str,
    due_date: str,
    issued_at: str,
    currency: str,
    reference: str,
    notes: str,
    issuer: Mapping[str, object],
    customer: Mapping[str, object],
    lines: Sequence[Mapping[str, object]],
    subtotal: str,
    tax_total: str,
    total: str,
) -> bytes:
    """Render one immutable, byte-deterministic US Letter invoice."""

    output = BytesIO()
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="InvoiceHeading", parent=styles["Heading2"], fontSize=12, leading=15, textColor=INK))
    styles.add(
        ParagraphStyle(
            name="InvoiceLabel", parent=styles["BodyText"], fontSize=7.5, leading=9, textColor=MUTED, spaceAfter=2
        )
    )
    styles.add(ParagraphStyle(name="InvoiceValue", parent=styles["BodyText"], fontSize=9.5, leading=12, textColor=INK))
    styles.add(ParagraphStyle(name="InvoiceAmount", parent=styles["InvoiceValue"], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="InvoiceSmall", parent=styles["BodyText"], fontSize=8.5, leading=11, textColor=INK))
    styles.add(
        ParagraphStyle(
            name="InvoiceAmountDue", parent=styles["InvoiceAmount"], fontSize=14, leading=17, textColor=ACCENT
        )
    )

    issuer_name = _text(issuer.get("legal_name"))
    issuer_address = _address(issuer)
    issuer_email = _text(issuer.get("billing_email"))
    issuer_phone = _text(issuer.get("phone"))
    issuer_tax = _text(issuer.get("tax_registration"))
    customer_name = _text(customer.get("legal_name") or customer.get("display_name"))
    customer_contact = _text(customer.get("contact_name"))
    customer_address = _address(customer)
    customer_email = _text(customer.get("billing_email"))
    customer_phone = _text(customer.get("phone"))
    customer_website = _text(customer.get("website"))

    story: list[Flowable] = []
    story.append(
        Table(
            [["", ""]],
            colWidths=(4.65 * inch, 2.35 * inch),
            rowHeights=(4,),
            style=(("BACKGROUND", (0, 0), (-1, -1), ACCENT),),
        )
    )
    story.append(Spacer(1, 14))
    heading = Table(
        [
            [
                Paragraph(
                    f"<b>{issuer_name}</b><br/><font color='#56605A' size='8'>INVOICE</font>", styles["InvoiceHeading"]
                ),
                Paragraph(f"<b>{_text(number)}</b>", styles["InvoiceHeading"]),
            ]
        ],
        colWidths=(4.65 * inch, 2.35 * inch),
    )
    heading.setStyle(
        TableStyle(
            (
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            )
        )
    )
    story.extend((heading, Spacer(1, 15)))

    metadata = Table(
        [
            [
                Paragraph("Invoice date", styles["InvoiceLabel"]),
                Paragraph("Due date", styles["InvoiceLabel"]),
                Paragraph("Currency", styles["InvoiceLabel"]),
                Paragraph("Reference", styles["InvoiceLabel"]),
            ],
            [
                Paragraph(_date(invoice_date), styles["InvoiceValue"]),
                Paragraph(_date(due_date), styles["InvoiceValue"]),
                Paragraph(_text(currency), styles["InvoiceValue"]),
                Paragraph(_text(reference) or "-", styles["InvoiceValue"]),
            ],
        ],
        colWidths=(1.45 * inch, 1.45 * inch, 1.05 * inch, 3.05 * inch),
    )
    metadata.setStyle(
        TableStyle(
            (
                ("BACKGROUND", (0, 0), (-1, 0), HEADER),
                ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, RULE),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            )
        )
    )
    story.extend((metadata, Spacer(1, 17)))

    issuer_details = "<br/>".join(part for part in (issuer_address, issuer_email, issuer_phone) if part)
    if issuer_tax:
        issuer_details = "<br/>".join(part for part in (issuer_details, f"Tax ID: {issuer_tax}") if part)
    customer_details = "<br/>".join(
        part
        for part in (
            f"<b>{customer_name}</b>",
            customer_contact,
            customer_address,
            customer_email,
            customer_phone,
            customer_website,
        )
        if part
    )
    parties = Table(
        [
            [Paragraph("From", styles["InvoiceLabel"]), Paragraph("Bill to", styles["InvoiceLabel"])],
            [
                Paragraph(f"<b>{issuer_name}</b><br/>{issuer_details}", styles["InvoiceValue"]),
                Paragraph(customer_details, styles["InvoiceValue"]),
            ],
        ],
        colWidths=(3.5 * inch, 3.5 * inch),
    )
    parties.setStyle(
        TableStyle(
            (
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            )
        )
    )
    story.extend((parties, Spacer(1, 16)))

    line_rows = [
        [
            Paragraph("Description", styles["InvoiceLabel"]),
            Paragraph("Qty", styles["InvoiceLabel"]),
            Paragraph("Unit", styles["InvoiceLabel"]),
            Paragraph("Rate", styles["InvoiceLabel"]),
            Paragraph("Tax", styles["InvoiceLabel"]),
            Paragraph("Amount", styles["InvoiceLabel"]),
        ]
    ]
    for line in lines:
        line_rows.append(
            [
                Paragraph(_text(line.get("description")), styles["InvoiceValue"]),
                Paragraph(_quantity(line.get("quantity")), styles["InvoiceAmount"]),
                Paragraph(_text(line.get("unit")) or "-", styles["InvoiceAmount"]),
                Paragraph(_text(line.get("unit_amount")), styles["InvoiceAmount"]),
                Paragraph(_text(line.get("tax")), styles["InvoiceAmount"]),
                Paragraph(_text(line.get("total")), styles["InvoiceAmount"]),
            ]
        )
    line_table = Table(
        line_rows, repeatRows=1, colWidths=(2.7 * inch, 0.55 * inch, 0.65 * inch, 0.85 * inch, 0.7 * inch, 0.85 * inch)
    )
    line_table.setStyle(
        TableStyle(
            (
                ("BACKGROUND", (0, 0), (-1, 0), HEADER),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#8D9690")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, RULE),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            )
        )
    )
    story.extend((line_table, Spacer(1, 12)))

    totals = Table(
        [
            [
                Paragraph("Subtotal", styles["InvoiceLabel"]),
                Paragraph(f"{_text(currency)} {_text(subtotal)}", styles["InvoiceAmount"]),
            ],
            [
                Paragraph("Tax", styles["InvoiceLabel"]),
                Paragraph(f"{_text(currency)} {_text(tax_total)}", styles["InvoiceAmount"]),
            ],
            [
                Paragraph("Total", styles["InvoiceValue"]),
                Paragraph(f"<b>{_text(currency)} {_text(total)}</b>", styles["InvoiceAmount"]),
            ],
            [
                Paragraph("Amount due", styles["InvoiceValue"]),
                Paragraph(f"<b>{_text(currency)} {_text(total)}</b>", styles["InvoiceAmountDue"]),
            ],
        ],
        colWidths=(1.0 * inch, 1.6 * inch),
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            (
                ("LINEABOVE", (0, 2), (-1, 2), 0.8, MUTED),
                ("BACKGROUND", (0, 3), (-1, 3), ACCENT_PALE),
                ("BOX", (0, 3), (-1, 3), 0.5, ACCENT),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            )
        )
    )
    story.extend((totals, Spacer(1, 16)))

    payment = _multiline(issuer.get("payment_instructions"))
    if not payment:
        payment = f"Payment is due by {_date(due_date)}. Contact {issuer_email} for payment details."
    detail_cells: list[list[Flowable]] = []
    if notes.strip():
        detail_cells.append(
            [
                Paragraph("Project notes", styles["InvoiceHeading"]),
                Paragraph(_multiline(notes), styles["InvoiceSmall"]),
            ]
        )
    detail_cells.append([Paragraph("Payment", styles["InvoiceHeading"]), Paragraph(payment, styles["InvoiceSmall"])])
    if len(detail_cells) == 1:
        story.extend(detail_cells[0])
        story.append(Spacer(1, 10))
    else:
        detail_table = Table([detail_cells], colWidths=(3.35 * inch, 3.35 * inch))
        detail_table.setStyle(
            TableStyle(
                (
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 12),
                    ("LEFTPADDING", (1, 0), (1, 0), 12),
                    ("RIGHTPADDING", (1, 0), (1, 0), 0),
                    ("LINEBEFORE", (1, 0), (1, 0), 0.5, RULE),
                )
            )
        )
        story.append(detail_table)

    document = SimpleDocTemplate(
        output,
        pagesize=LETTER,
        rightMargin=54,
        leftMargin=54,
        topMargin=42,
        bottomMargin=48,
        title=f"Invoice {number}",
        author=issuer_name,
        subject=f"Invoice {number} from {issuer_name}",
        creator="TekDocs",
    )
    timestamp = _issued_timestamp(issued_at)

    def invariant_canvas(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["invariant"] = 1
        canvas = Canvas(*args, **kwargs)
        canvas._doc._timeStamp = timestamp
        canvas.setCreator("TekDocs")
        return canvas

    def footer(canvas, doc):  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(54, 26, f"{issuer_name} · Invoice {number}")
        canvas.drawRightString(558, 26, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, canvasmaker=invariant_canvas, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
