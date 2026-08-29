"""Deterministic retained invoice PDF rendering for ADR 0091."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _text(value: object) -> str:
    return escape(str(value or "").strip())


def _address(identity: Mapping[str, object]) -> str:
    first = "<br/>".join(
        part for part in (_text(identity.get("address_line_1")), _text(identity.get("address_line_2"))) if part
    )
    locality = ", ".join(
        part
        for part in (
            _text(identity.get("city")),
            _text(identity.get("region")),
            _text(identity.get("postal_code")),
            _text(identity.get("country_code")),
        )
        if part
    )
    return "<br/>".join(part for part in (first, locality) if part)


def render_invoice_pdf(
    *,
    number: str,
    invoice_date: str,
    due_date: str,
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
    styles.add(
        ParagraphStyle(
            name="InvoiceLabel",
            parent=styles["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#56605A"),
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="InvoiceValue",
            parent=styles["BodyText"],
            fontSize=10,
            leading=13,
        )
    )
    styles.add(
        ParagraphStyle(
            name="InvoiceAmount",
            parent=styles["BodyText"],
            fontSize=10,
            leading=13,
            alignment=TA_RIGHT,
        )
    )
    story: list[Flowable] = []
    heading = Table(
        [
            [Paragraph("Invoice", styles["Title"]), Paragraph(_text(number), styles["Heading2"])],
        ],
        colWidths=(3.2 * inch, 3.8 * inch),
    )
    heading.setStyle(TableStyle((("ALIGN", (1, 0), (1, 0), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"))))
    story.extend((heading, Spacer(1, 18)))

    metadata = Table(
        [
            [
                Paragraph("Invoice date", styles["InvoiceLabel"]),
                Paragraph("Due date", styles["InvoiceLabel"]),
                Paragraph("Currency", styles["InvoiceLabel"]),
                Paragraph("Reference", styles["InvoiceLabel"]),
            ],
            [
                Paragraph(_text(invoice_date), styles["InvoiceValue"]),
                Paragraph(_text(due_date), styles["InvoiceValue"]),
                Paragraph(_text(currency), styles["InvoiceValue"]),
                Paragraph(_text(reference) or "-", styles["InvoiceValue"]),
            ],
        ],
        colWidths=(1.45 * inch, 1.45 * inch, 1.05 * inch, 3.05 * inch),
    )
    metadata.setStyle(
        TableStyle(
            (
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF1EE")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#A6ADA8")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#C7CCC8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            )
        )
    )
    story.extend((metadata, Spacer(1, 18)))

    issuer_name = _text(issuer.get("legal_name"))
    issuer_details = _address(issuer)
    issuer_email = _text(issuer.get("billing_email"))
    customer_name = _text(customer.get("legal_name") or customer.get("display_name"))
    parties = Table(
        [
            [Paragraph("From", styles["InvoiceLabel"]), Paragraph("Bill to", styles["InvoiceLabel"])],
            [
                Paragraph(f"<b>{issuer_name}</b><br/>{issuer_details}<br/>{issuer_email}", styles["InvoiceValue"]),
                Paragraph(f"<b>{customer_name}</b>", styles["InvoiceValue"]),
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
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            )
        )
    )
    story.extend((parties, Spacer(1, 18)))

    line_rows = [
        [
            Paragraph("Description", styles["InvoiceLabel"]),
            Paragraph("Quantity", styles["InvoiceLabel"]),
            Paragraph("Unit", styles["InvoiceLabel"]),
            Paragraph("Net", styles["InvoiceLabel"]),
            Paragraph("Tax", styles["InvoiceLabel"]),
            Paragraph("Total", styles["InvoiceLabel"]),
        ]
    ]
    for line in lines:
        line_rows.append(
            [
                Paragraph(_text(line.get("description")), styles["InvoiceValue"]),
                Paragraph(_text(line.get("quantity")), styles["InvoiceAmount"]),
                Paragraph(_text(line.get("unit_amount")), styles["InvoiceAmount"]),
                Paragraph(_text(line.get("net")), styles["InvoiceAmount"]),
                Paragraph(_text(line.get("tax")), styles["InvoiceAmount"]),
                Paragraph(_text(line.get("total")), styles["InvoiceAmount"]),
            ]
        )
    line_table = Table(
        line_rows,
        repeatRows=1,
        colWidths=(2.45 * inch, 0.72 * inch, 0.85 * inch, 0.75 * inch, 0.68 * inch, 0.83 * inch),
    )
    line_table.setStyle(
        TableStyle(
            (
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E4E9E5")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#8D9690")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C0C7C2")),
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
        ],
        colWidths=(1.0 * inch, 1.5 * inch),
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            (
                ("LINEABOVE", (0, 2), (-1, 2), 0.8, colors.HexColor("#48514C")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            )
        )
    )
    story.extend((totals, Spacer(1, 18)))
    if notes.strip():
        story.extend((Paragraph("Notes", styles["Heading3"]), Paragraph(_text(notes), styles["InvoiceValue"])))

    document = SimpleDocTemplate(
        output,
        pagesize=LETTER,
        rightMargin=54,
        leftMargin=54,
        topMargin=48,
        bottomMargin=48,
        title=f"Invoice {number}",
        author="TekDocs",
    )

    def invariant_canvas(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["invariant"] = 1
        return Canvas(*args, **kwargs)

    def footer(canvas, doc):  # type: ignore[no-untyped-def]
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#56605A"))
        canvas.drawString(54, 26, f"Invoice {number}")
        canvas.drawRightString(558, 26, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, canvasmaker=invariant_canvas, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
