"""Write batch concentrations into an Excel template.

Sheet ``XRF``
    Row 1 is the header.
    A1 is ``Sample``.
    Each following header is an element symbol, in the configuration's curve order.
    The first scan is written on row 2, one row per scan.
    For the bronze configuration the columns are A Sample, B Fe, C Cu, D Zn,
    so the first concentration is cell B2.

Existing sheets, formulas, and cells outside those columns are left in place.
A shorter batch clears the previous values in those columns from row 2 down.
"""

from __future__ import annotations

from openpyxl import Workbook, load_workbook

from xrfdesk.batch import DONE, ScanResult

SHEET = "XRF"


def fill_workbook(template: str, destination: str, results: list[ScanResult], elements: list[str]) -> None:
    workbook = load_workbook(template)
    sheet = workbook[SHEET] if SHEET in workbook.sheetnames else workbook.create_sheet(SHEET, 0)
    headers = ["Sample", *elements]
    for column, header in enumerate(headers, start=1):
        if sheet.cell(1, column).value in (None, ""):
            sheet.cell(1, column).value = header
    columns = _header_columns(sheet)
    sample_column = columns.get("sample")
    if sample_column is None:
        sample_column = 1
        sheet.cell(1, 1).value = "Sample"
        columns["sample"] = 1
    for element in elements:
        if element.lower() not in columns:
            column = sheet.max_column + 1
            sheet.cell(1, column).value = element
            columns[element.lower()] = column
    used = [columns["sample"], *[columns[element.lower()] for element in elements]]
    last = max(sheet.max_row, 1 + len(results))
    for row in range(2, last + 1):
        for column in used:
            sheet.cell(row, column).value = None
    for offset, result in enumerate(results):
        row = 2 + offset
        sheet.cell(row, columns["sample"]).value = result.sample
        if result.status != DONE:
            continue
        for element in elements:
            value = result.concentrations.get(element)
            if value is None:
                continue
            sheet.cell(row, columns[element.lower()]).value = round(value, 4)
    workbook.save(destination)


def new_template(path: str, elements: list[str]) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = SHEET
    sheet["A1"] = "Sample"
    for column, element in enumerate(elements, start=2):
        sheet.cell(1, column).value = element
    notes = workbook.create_sheet("Notes")
    notes["A1"] = "Batch writes one row per scan on sheet XRF, starting at row 2."
    notes["A2"] = "Column A is the sample. Each element named on row 1 receives its concentration."
    workbook.save(path)


def _header_columns(sheet) -> dict[str, int]:
    found = {}
    for column in range(1, sheet.max_column + 1):
        value = sheet.cell(1, column).value
        if isinstance(value, str) and value.strip():
            found[value.strip().lower()] = column
    return found
