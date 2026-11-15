"""Bulk grade import: read a CSV / XLSX file and validate it. No request or database access here.

File format: the first column header is ``student_number``, every other header is the name of an
assessment of the offering. One row per student; a cell is a number 0-100 or blank (blank = keep as is).
"""

import csv
from decimal import Decimal, InvalidOperation
from io import BytesIO

from openpyxl import load_workbook

MAX_FILE_SIZE = 1024 * 1024  # 1 MB


def parse_score(raw):
    """Return (score, error). Blank means 'no grade'."""
    raw = raw.strip()
    if raw == "":
        return None, None
    try:
        score = Decimal(raw)
    except InvalidOperation:
        return None, "Not a number"
    if not score.is_finite() or not Decimal("0") <= score <= Decimal("100"):
        return None, "Must be between 0 and 100"
    return score, None


def _cell_to_text(value):
    """Turn an Excel cell value into text. Numbers such as 20260001.0 lose the '.0'."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_rows(filename, data):
    """Return (rows, error). rows is a list of lists of text; the first row is the header."""
    if len(data) > MAX_FILE_SIZE:
        return None, "The file is too large (limit is 1 MB)."
    name = filename.lower()
    try:
        if name.endswith(".csv"):
            text = data.decode("utf-8-sig")
            lines = text.splitlines()
            # Turkish Excel exports use ';' as the delimiter.
            first = lines[0] if lines else ""
            delimiter = ";" if first.count(";") > first.count(",") else ","
            rows = [[cell.strip() for cell in row] for row in csv.reader(lines, delimiter=delimiter)]
        elif name.endswith(".xlsx"):
            workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
            rows = [[_cell_to_text(cell) for cell in row] for row in workbook.active.iter_rows(values_only=True)]
        else:
            return None, "Unsupported file type. Upload a .csv or .xlsx file."
    except Exception:  # any parser failure means the file is unreadable
        return None, "The file could not be read. Is it a valid .csv or .xlsx file?"
    return rows, None


def validate_import(rows, assessment_ids, enrollments):
    """Check the rows and return (grades, errors).

    assessment_ids: {assessment name: assessment id}
    enrollments: {student number: (enrollment id, student id)}
    grades: list of dicts with enrollment_id, student_id, assessment_id, score (blank cells are skipped).
    errors: list of messages, each starting with the row number (the header is row 1).
    """
    rows = [(number, row) for number, row in enumerate(rows, start=1)]
    if not any(any(cell for cell in row) for _, row in rows):
        return [], ["The file is empty."]

    header = rows[0][1]
    if not header or header[0].lower() != "student_number":
        return [], ["Row 1: the first column must be named student_number."]

    errors = []
    columns = []  # (column index, assessment id) for every known assessment column
    seen_names = set()
    for index, name in enumerate(header[1:], start=1):
        if name == "":
            continue  # ignore blank headers (Excel often adds empty columns)
        if name not in assessment_ids:
            errors.append(f"Row 1: unknown assessment column '{name}'.")
        elif name in seen_names:
            errors.append(f"Row 1: assessment column '{name}' appears more than once.")
        else:
            seen_names.add(name)
            columns.append((index, assessment_ids[name]))

    grades = []
    seen_students = set()
    data_rows = 0
    for number, row in rows[1:]:
        if not any(row):
            continue  # skip blank lines
        data_rows += 1
        student_number = row[0]
        if student_number == "":
            errors.append(f"Row {number}: student_number is empty.")
            continue
        if student_number not in enrollments:
            errors.append(f"Row {number}: student {student_number} is not enrolled in this offering.")
            continue
        if student_number in seen_students:
            errors.append(f"Row {number}: student {student_number} appears more than once.")
            continue
        seen_students.add(student_number)
        enrollment_id, student_id = enrollments[student_number]
        for index, assessment_id in columns:
            raw = row[index].replace(",", ".") if index < len(row) else ""  # accept 85,5 as 85.5
            score, error = parse_score(raw)
            if error:
                errors.append(f"Row {number}, column {header[index]}: '{raw}' - {error.lower()}.")
            elif score is not None:
                grades.append(
                    {
                        "enrollment_id": enrollment_id,
                        "student_id": student_id,
                        "assessment_id": assessment_id,
                        "score": score,
                    }
                )

    if data_rows == 0:
        errors.append("The file has a header but no student rows.")
    return grades, errors
