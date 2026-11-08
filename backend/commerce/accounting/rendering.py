"""Fill the supplied, sanitized layouts; exports are unsigned preparation copies."""

from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import load_workbook
from openpyxl.styles import Alignment
from openpyxl.utils import get_column_letter
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parent


def amount_words(value):
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    integer = int(amount)
    if not 0 <= amount < Decimal("1000000000000"):
        raise ValueError("Amount is outside the document range")
    ones = ("", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
    teens = (
        "десять",
        "одиннадцать",
        "двенадцать",
        "тринадцать",
        "четырнадцать",
        "пятнадцать",
        "шестнадцать",
        "семнадцать",
        "восемнадцать",
        "девятнадцать",
    )
    tens = (
        "",
        "",
        "двадцать",
        "тридцать",
        "сорок",
        "пятьдесят",
        "шестьдесят",
        "семьдесят",
        "восемьдесят",
        "девяносто",
    )
    hundreds = (
        "",
        "сто",
        "двести",
        "триста",
        "четыреста",
        "пятьсот",
        "шестьсот",
        "семьсот",
        "восемьсот",
        "девятьсот",
    )
    ranks = (
        ("", "", ""),
        ("тысяча", "тысячи", "тысяч"),
        ("миллион", "миллиона", "миллионов"),
        ("миллиард", "миллиарда", "миллиардов"),
    )
    groups = []
    for rank, forms in enumerate(ranks):
        group = (integer // (1000**rank)) % 1000
        if not group:
            continue
        tail = group % 100
        units = ("", "одна", "две", *ones[3:]) if rank == 1 else ones
        words = [hundreds[group // 100]]
        words += [teens[tail - 10]] if 10 <= tail < 20 else [tens[tail // 10], units[tail % 10]]
        form = 2 if 11 <= tail <= 14 else 0 if tail % 10 == 1 else 1 if 2 <= tail % 10 <= 4 else 2
        words.append(forms[form])
        groups.insert(0, " ".join(w for w in words if w))
    text = " ".join(groups) or "ноль"
    cents = int((amount - integer) * 100)
    return f"{text.capitalize()} тенге {cents:02d} тиын"


def notice(doc):
    prefix = "ДЕМО. " if doc.snapshot.get("paymentMode") != "production" else ""
    state = {"draft": "ЧЕРНОВИК", "released": "ПОДГОТОВЛЕННАЯ КОПИЯ", "voided": "ОТМЕНЁН"}[
        doc.state
    ]
    extra = " Не подтверждает приём наличных." if doc.kind == "cash_order" else ""
    return f"{prefix}{state}. Без подписей / ЭЦП. Не зарегистрирован в ИС ЭСФ.{extra}"


def workbook(doc):
    wb = load_workbook(ROOT / "templates" / f"{doc.kind}.xlsx")
    ws = wb.active
    buyer = {}
    if doc.snapshot.get("buyerEncrypted"):
        from .private_data import unseal

        buyer = unseal(
            doc.snapshot["buyerEncrypted"], context=f"buyer:{doc.booking_id}:{doc.number}"
        )
        # The selected buyer only: other occupants' identities never enter an export.
        if doc.kind == "invoice":
            ws["A18"] = "Грузополучатель: {buyer_consignee}"
            ws["A20"] = "Получатель: {buyer_name_address}"
            ws["A21"] = "ИИН получателя: {buyer_iin}"
            ws["A22"] = "ИИК получателя: {buyer_iban}, в банке {buyer_bank}, БИК {buyer_bik}"
        elif doc.kind == "act":
            ws["E9"] = "{buyer_details}"
            ws["AQ9"] = "{buyer_iin}"
    values = {
        **doc.snapshot,
        "notice": notice(doc),
        "amount_words": amount_words(doc.snapshot["amount"]),
        **({"guest": buyer["fullName"]} if buyer else {}),
        **{f"buyer_{field}": buyer.get(field, "") for field in ("iin", "iban", "bank", "bik")},
        "buyer_consignee": ", ".join(
            buyer.get(field, "") for field in ("fullName", "iin", "address") if buyer.get(field)
        ),
        "buyer_name_address": ", ".join(
            buyer.get(field, "") for field in ("fullName", "address") if buyer.get(field)
        ),
        "buyer_details": ", ".join(
            buyer.get(field, "") for field in ("fullName", "address", "phone") if buyer.get(field)
        ),
    }
    for row in ws:
        for cell in row:
            if not isinstance(cell.value, str) or "{" not in cell.value:
                continue
            template = cell.value
            # Template placeholders are controlled source, never executable formulas.
            if template.startswith("{") and template.endswith("}") and template.count("{") == 1:
                value = values.get(template[1:-1], "")
            else:
                value = template.format_map(values)
            cell.value = value
            if isinstance(value, str):
                cell.data_type = "s"
            cell.alignment = Alignment(
                horizontal=cell.alignment.horizontal,
                vertical="center",
                wrap_text=True,
                textRotation=cell.alignment.textRotation,
            )
    ws.oddHeader.center.text = notice(doc)
    ws.oddHeader.center.size = 8
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 1
    ws.print_options.horizontalCentered = True
    return wb


def xlsx_bytes(doc):
    stream = BytesIO()
    workbook(doc).save(stream)
    return stream.getvalue()


def pdf_bytes(doc):
    ws = workbook(doc).active
    fonts = ROOT.parent / "fonts"
    if "TynysNoto" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("TynysNoto", str(fonts / "NotoSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("TynysNotoBold", str(fonts / "NotoSans-Bold.ttf")))
    size = landscape(A4)
    output = BytesIO()
    canvas = Canvas(output, pagesize=size)
    canvas.setTitle(doc.number)
    canvas.setAuthor("Tynys")
    width, height = size
    header = Paragraph(
        escape(notice(doc)),
        ParagraphStyle(
            "documentNotice",
            fontName="TynysNotoBold",
            fontSize=9,
            leading=12,
            textColor="#8c1f1a",
        ),
    )
    _, header_height = header.wrap(width - 44, height)
    header.drawOn(canvas, 22, height - 16 - header_height)
    table_top = height - 16 - header_height - 12
    columns = [0.0]
    for col in range(1, ws.max_column + 1):
        dim = ws.column_dimensions.get(get_column_letter(col))
        columns.append(columns[-1] + ((dim.width if dim and dim.width else 8.43) * 7 + 5) * 0.75)
    rows = [0.0]
    for row in range(1, ws.max_row + 1):
        rows.append(rows[-1] + (ws.row_dimensions[row].height or 15))
    scale = min((width - 44) / columns[-1], (table_top - 25) / rows[-1])
    canvas.translate(22, table_top)
    canvas.scale(scale, scale)
    merged = {(r.min_row, r.min_col): r for r in ws.merged_cells.ranges}
    for row in ws:
        for cell in row:
            if cell.value is None:
                continue
            region = merged.get((cell.row, cell.column))
            last_col, last_row = (
                (region.max_col, region.max_row) if region else (cell.column, cell.row)
            )
            # Excel lets unwrapped text occupy adjacent empty cells. Preserve that
            # layout for the source forms' explanatory labels in the PDF export.
            if not region and isinstance(cell.value, str) and not cell.alignment.wrap_text:
                while last_col < ws.max_column and ws.cell(cell.row, last_col + 1).value is None:
                    last_col += 1
            x, y = columns[cell.column - 1], -rows[last_row]
            w, h = columns[last_col] - x, rows[last_row] - rows[cell.row - 1]
            canvas.setStrokeColorRGB(0.3, 0.3, 0.3)
            canvas.setLineWidth(0.4)
            for side, points in [
                (cell.border.left, (x, y, x, y + h)),
                (cell.border.right, (x + w, y, x + w, y + h)),
                (cell.border.top, (x, y + h, x + w, y + h)),
                (cell.border.bottom, (x, y, x + w, y)),
            ]:
                if side and side.style:
                    canvas.line(*points)
            font = "TynysNotoBold" if cell.font.bold else "TynysNoto"
            canvas.saveState()
            if cell.alignment.textRotation in (90, 180):
                canvas.translate(x, y)
                canvas.rotate(90)
                x, y, w, h = 0, -w, h, w
            text = str(cell.value)
            text = escape(text).replace("\n", "<br/>")
            alignment = {"center": TA_CENTER, "right": TA_RIGHT}.get(
                cell.alignment.horizontal, TA_LEFT
            )
            font_size = min(float(cell.font.sz or 10), 11)
            while True:
                style = ParagraphStyle(
                    "cell",
                    fontName=font,
                    fontSize=font_size,
                    leading=font_size * 1.16,
                    alignment=alignment,
                    textColor="#172e26",
                )
                para = Paragraph(text, style)
                _, ph = para.wrap(max(w - 4, 1), max(h - 2, 1))
                if ph <= h - 2 or font_size <= 5:
                    break
                font_size -= 0.5
            para.drawOn(canvas, x + 2, y + max(1, (h - ph) / 2))
            canvas.restoreState()
    canvas.showPage()
    canvas.save()
    return output.getvalue()
