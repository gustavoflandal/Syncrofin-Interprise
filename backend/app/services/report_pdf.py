"""PDF renderer for financial reports with workspace branding.

Renders DRE, DFC, Net Worth and Income/Expenses reports as branded
PDFs, with an optional workspace logo in the header.
"""
import io
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import Paragraph, Table, TableStyle

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 18 * mm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

INK = colors.HexColor("#18181b")
MUTED = colors.HexColor("#71717a")
RULE = colors.HexColor("#e4e4e7")
ACCENT = colors.HexColor("#6366F1")
ALT_ROW = colors.HexColor("#f8f8fa")


def _para(text, size=9.5, color=INK, bold=False, leading=None, align=0):
    style = ParagraphStyle(
        "cell",
        fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=size,
        leading=leading or size * 1.45,
        textColor=color,
        alignment=align,
    )
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def _money(amount, currency="BRL"):
    q = Decimal(str(amount)).quantize(Decimal("0.01"))
    return f"{currency} {q:,.2f}"


class ReportPDFBuilder:
    """Generates branded PDF reports with workspace identity."""

    def __init__(self, workspace, logo_bytes=None):
        self.workspace = workspace
        self.logo_bytes = logo_bytes

    def _draw_header(self, canvas, title, period):
        """Company name, logo, report title, period."""
        y = PAGE_HEIGHT - MARGIN

        if self.logo_bytes:
            try:
                from reportlab.lib.utils import ImageReader
                image = ImageReader(io.BytesIO(self.logo_bytes))
                iw, ih = image.getSize()
                height = 13 * mm
                width = min(height * (iw / ih) if ih else height, 45 * mm)
                canvas.drawImage(
                    image, MARGIN, y - height, width=width, height=height,
                    mask="auto", preserveAspectRatio=True, anchor="sw",
                )
                y -= height + 3 * mm
            except Exception:
                pass

        # Company name
        company = self.workspace.legal_name or self.workspace.name
        canvas.setFont("Helvetica-Bold", 14)
        canvas.setFillColor(INK)
        canvas.drawString(MARGIN, y - 5 * mm, company)
        y -= 9 * mm

        if self.workspace.address:
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(MUTED)
            canvas.drawString(MARGIN, y - 3 * mm, self.workspace.address)
            y -= 6 * mm

        # Report title
        canvas.setFont("Helvetica-Bold", 16)
        canvas.setFillColor(ACCENT)
        canvas.drawString(MARGIN, y - 6 * mm, title)

        # Period on the right
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(PAGE_WIDTH - MARGIN, y - 6 * mm, period)
        y -= 10 * mm

        # Rule
        canvas.setStrokeColor(ACCENT)
        canvas.setLineWidth(1.2)
        canvas.line(MARGIN, y, PAGE_WIDTH - MARGIN, y)
        return y - 8 * mm

    def _draw_footer(self, canvas, page, total_pages):
        """Page number and generation date."""
        y = MARGIN - 3 * mm
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
        canvas.drawString(MARGIN, y, f"Gerado em {now}")
        if total_pages > 1:
            canvas.drawRightString(PAGE_WIDTH - MARGIN, y, f"{page} / {total_pages}")
        # Confidential watermark
        canvas.setFont("Helvetica", 7)
        canvas.drawCentredString(PAGE_WIDTH / 2, y, "Confidencial")

    def build_dre_pdf(self, report, currency="BRL"):
        """Render DRE as PDF."""
        buffer = io.BytesIO()
        c = pdf_canvas.Canvas(buffer, pagesize=A4)
        title = "Demonstrativo de Resultado (DRE)"
        period = f"{report.month:02d}/{report.year}"
        y = self._draw_header(c, title, period)

        # Summary table
        summary_data = [
            [_para("Descrição", bold=True, color=MUTED), _para("Valor", bold=True, color=MUTED, align=TA_RIGHT)],
            [_para("Receita Bruta"), _para(_money(report.gross_revenue, currency), align=TA_RIGHT)],
            [_para("Deduções"), _para(_money(report.deductions, currency), align=TA_RIGHT)],
            [_para("Receita Líquida", bold=True), _para(_money(report.net_revenue, currency), bold=True, align=TA_RIGHT)],
            [_para("Despesas Operacionais"), _para(_money(report.operating_expenses, currency), align=TA_RIGHT)],
            [_para("Resultado", bold=True, color=ACCENT), _para(_money(report.result, currency), bold=True, color=ACCENT, align=TA_RIGHT)],
        ]

        table = Table(summary_data, colWidths=[CONTENT_WIDTH * 0.65, CONTENT_WIDTH * 0.35])
        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
            ("LINEBELOW", (0, -1), (-1, -1), 0.6, RULE),
        ]
        # Alternating row colors
        for i in range(1, len(summary_data)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), ALT_ROW))
        table.setStyle(TableStyle(style))

        _, h = table.wrap(CONTENT_WIDTH, PAGE_HEIGHT)
        if y - h < MARGIN + 20 * mm:
            c.showPage()
            y = PAGE_HEIGHT - MARGIN
        table.drawOn(c, MARGIN, y - h)
        y -= h + 6 * mm

        # Sections detail
        for section in report.sections:
            # Section header
            if y < MARGIN + 30 * mm:
                self._draw_footer(c, 1, 1)
                c.showPage()
                y = PAGE_HEIGHT - MARGIN

            c.setFont("Helvetica-Bold", 11)
            c.setFillColor(INK)
            c.drawString(MARGIN, y - 4 * mm, section.label)
            y -= 8 * mm

            for grp in section.groups:
                if y < MARGIN + 20 * mm:
                    self._draw_footer(c, 1, 1)
                    c.showPage()
                    y = PAGE_HEIGHT - MARGIN

                c.setFont("Helvetica-Bold", 9)
                c.setFillColor(MUTED)
                c.drawString(MARGIN + 4, y - 3 * mm, grp.group_name)
                c.drawRightString(PAGE_WIDTH - MARGIN, y - 3 * mm, _money(grp.subtotal, currency))
                y -= 6 * mm

                for line in grp.lines:
                    if y < MARGIN + 15 * mm:
                        self._draw_footer(c, 1, 1)
                        c.showPage()
                        y = PAGE_HEIGHT - MARGIN
                    c.setFont("Helvetica", 8.5)
                    c.setFillColor(INK)
                    c.drawString(MARGIN + 12, y - 3 * mm, line.label)
                    c.drawRightString(PAGE_WIDTH - MARGIN, y - 3 * mm, _money(line.amount, currency))
                    y -= 5 * mm

                y -= 2 * mm

        self._draw_footer(c, 1, 1)
        c.showPage()
        c.save()
        return buffer.getvalue()

    def build_dfc_pdf(self, report, currency="BRL"):
        """Render DFC as PDF."""
        buffer = io.BytesIO()
        c = pdf_canvas.Canvas(buffer, pagesize=A4)
        title = "Demonstrativo de Fluxo de Caixa (DFC)"
        period = f"{report.month:02d}/{report.year}"
        y = self._draw_header(c, title, period)

        # Opening balance
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(INK)
        c.drawString(MARGIN, y - 4 * mm, "Saldo de Abertura")
        c.drawRightString(PAGE_WIDTH - MARGIN, y - 4 * mm, _money(report.opening_balance, currency))
        y -= 10 * mm

        # Periods table
        rows = [
            [_para("Período", bold=True, color=MUTED),
             _para("Entradas", bold=True, color=MUTED, align=TA_RIGHT),
             _para("Saídas", bold=True, color=MUTED, align=TA_RIGHT),
             _para("Saldo", bold=True, color=MUTED, align=TA_RIGHT)],
        ]
        for p in report.periods:
            rows.append([
                _para(p.date),
                _para(_money(p.inflows, currency), align=TA_RIGHT),
                _para(_money(p.outflows, currency), align=TA_RIGHT),
                _para(_money(p.balance, currency), align=TA_RIGHT),
            ])

        table = Table(rows, colWidths=[
            CONTENT_WIDTH * 0.3, CONTENT_WIDTH * 0.23,
            CONTENT_WIDTH * 0.23, CONTENT_WIDTH * 0.24,
        ])
        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ]
        for i in range(1, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), ALT_ROW))
        table.setStyle(TableStyle(style))

        _, h = table.wrap(CONTENT_WIDTH, PAGE_HEIGHT)
        table.drawOn(c, MARGIN, y - h)
        y -= h + 8 * mm

        # Closing balance
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(ACCENT)
        c.drawString(MARGIN, y - 4 * mm, "Saldo de Fechamento")
        c.drawRightString(PAGE_WIDTH - MARGIN, y - 4 * mm, _money(report.closing_balance, currency))

        self._draw_footer(c, 1, 1)
        c.showPage()
        c.save()
        return buffer.getvalue()

    def build_summary_pdf(self, title, data_rows, currency="BRL", period=""):
        """Render a generic summary (Net Worth or Income/Expenses) as PDF table.

        data_rows: list of (label, value) tuples
        """
        buffer = io.BytesIO()
        c = pdf_canvas.Canvas(buffer, pagesize=A4)
        y = self._draw_header(c, title, period)

        rows = [[_para("Descrição", bold=True, color=MUTED), _para("Valor", bold=True, color=MUTED, align=TA_RIGHT)]]
        for label, value in data_rows:
            rows.append([_para(label), _para(_money(value, currency), align=TA_RIGHT)])

        table = Table(rows, colWidths=[CONTENT_WIDTH * 0.65, CONTENT_WIDTH * 0.35])
        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE),
        ]
        for i in range(1, len(rows)):
            if i % 2 == 0:
                style.append(("BACKGROUND", (0, i), (-1, i), ALT_ROW))
        table.setStyle(TableStyle(style))

        _, h = table.wrap(CONTENT_WIDTH, PAGE_HEIGHT)
        table.drawOn(c, MARGIN, y - h)

        self._draw_footer(c, 1, 1)
        c.showPage()
        c.save()
        return buffer.getvalue()
