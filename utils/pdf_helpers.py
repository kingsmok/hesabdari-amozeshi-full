"""ابزارهای مشترک ساخت خروجی PDF فارسی."""
from __future__ import annotations

import io
import os
from typing import Iterable, Sequence

from flask import current_app, send_file
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONT_REGISTERED = False
REGULAR_FONT = 'AcademyDejaVu'
BOLD_FONT = 'AcademyDejaVuBold'


def register_pdf_fonts() -> tuple[str, str]:
    """فونت فارسی همراه برنامه را برای ReportLab ثبت می‌کند."""
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return REGULAR_FONT, BOLD_FONT

    font_dir = os.path.join(current_app.static_folder, 'fonts')
    regular_path = os.path.join(font_dir, 'DejaVuSans.ttf')
    bold_path = os.path.join(font_dir, 'DejaVuSans-Bold.ttf')

    pdfmetrics.registerFont(TTFont(REGULAR_FONT, regular_path))
    pdfmetrics.registerFont(TTFont(BOLD_FONT, bold_path))
    _FONT_REGISTERED = True
    return REGULAR_FONT, BOLD_FONT


def fa_text(value) -> str:
    """متن فارسی را برای نمایش صحیح و راست‌به‌چپ در PDF آماده می‌کند."""
    text = '' if value is None else str(value)
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except ImportError:
        # در نصب استاندارد وابستگی‌ها موجودند؛ fallback مانع توقف کل خروجی می‌شود.
        return text


def fa_paragraph(value, style: ParagraphStyle) -> Paragraph:
    # Paragraph کاراکترهای XML را تفسیر می‌کند؛ ابتدا escape می‌کنیم.
    from xml.sax.saxutils import escape
    return Paragraph(escape(fa_text(value)), style)


def pdf_response(buffer: io.BytesIO, filename: str, download: bool = False):
    """فقط پاسخ application/pdf برمی‌گرداند؛ هیچ خروجی تصویری تولید نمی‌شود."""
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype='application/pdf',
        as_attachment=download,
        download_name=filename,
        max_age=0,
    )


def build_table_pdf(
    title: str,
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    filename: str,
    *,
    subtitle: str | None = None,
    landscape_mode: bool = False,
    download: bool = False,
    column_widths: Sequence[float] | None = None,
):
    """ساخت گزارش جدولی استاندارد فارسی و تحویل مستقیم PDF."""
    regular, bold = register_pdf_fonts()
    page_size = landscape(A4) if landscape_mode else A4
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        rightMargin=13 * mm,
        leftMargin=13 * mm,
        topMargin=13 * mm,
        bottomMargin=13 * mm,
        title=title,
        author='Academy Manager Pro',
    )

    title_style = ParagraphStyle(
        'PdfTitle', fontName=bold, fontSize=15, leading=23,
        alignment=TA_CENTER, textColor=colors.HexColor('#0d47a1')
    )
    subtitle_style = ParagraphStyle(
        'PdfSubtitle', fontName=regular, fontSize=8.5, leading=14,
        alignment=TA_CENTER, textColor=colors.HexColor('#607d8b')
    )
    cell_style = ParagraphStyle(
        'PdfCell', fontName=regular, fontSize=8, leading=12,
        alignment=TA_RIGHT, wordWrap='RTL'
    )
    header_style = ParagraphStyle(
        'PdfHeader', fontName=bold, fontSize=8, leading=12,
        alignment=TA_CENTER, textColor=colors.white, wordWrap='RTL'
    )

    elements = [fa_paragraph(title, title_style)]
    if subtitle:
        elements.extend([Spacer(1, 2 * mm), fa_paragraph(subtitle, subtitle_style)])
    elements.append(Spacer(1, 7 * mm))

    rows_list = list(rows)
    table_data = [[fa_paragraph(header, header_style) for header in headers]]
    for row in rows_list:
        table_data.append([fa_paragraph(value, cell_style) for value in row])

    if not rows_list:
        table_data.append([fa_paragraph('موردی برای نمایش وجود ندارد', cell_style)] + [''] * (len(headers) - 1))

    table = Table(table_data, colWidths=column_widths, repeatRows=1, hAlign='CENTER')
    style_commands = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0d47a1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#cfd8dc')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f5f7fa')]),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, colors.HexColor('#002171')),
    ]
    if not rows_list:
        style_commands.append(('SPAN', (0, 1), (-1, 1)))
    table.setStyle(TableStyle(style_commands))
    elements.append(table)
    document.build(elements)
    return pdf_response(buffer, filename, download=download)
