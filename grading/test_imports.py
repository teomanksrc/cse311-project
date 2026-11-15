"""Unit tests for the import parser (no database needed)."""

from decimal import Decimal
from io import BytesIO

from django.test import SimpleTestCase
from openpyxl import Workbook

from grading.imports import MAX_FILE_SIZE, read_rows, validate_import

ASSESSMENTS = {"Midterm": 1, "Project": 2}
ENROLLMENTS = {"111": (10, 100), "222": (20, 200)}


def check(rows):
    return validate_import(rows, ASSESSMENTS, ENROLLMENTS)


class ReadRowsTests(SimpleTestCase):
    def test_csv_with_bom_and_comma(self):
        rows, error = read_rows("a.csv", "﻿student_number,Midterm\n111,90\n".encode("utf-8"))
        self.assertIsNone(error)
        self.assertEqual(rows, [["student_number", "Midterm"], ["111", "90"]])

    def test_csv_with_semicolon(self):
        rows, _ = read_rows("a.csv", b"student_number;Midterm;Project\n111;90;85,5\n")
        self.assertEqual(rows[1], ["111", "90", "85,5"])

    def test_xlsx(self):
        book = Workbook()
        book.active.append(["student_number", "Midterm"])
        book.active.append([111.0, 90.5])
        buffer = BytesIO()
        book.save(buffer)
        rows, error = read_rows("a.xlsx", buffer.getvalue())
        self.assertIsNone(error)
        self.assertEqual(rows, [["student_number", "Midterm"], ["111", "90.5"]])

    def test_unreadable_files(self):
        self.assertIsNotNone(read_rows("a.xlsx", b"not a zip")[1])
        self.assertIsNotNone(read_rows("a.csv", b"\xff\xfe\x00bad")[1])
        self.assertIsNotNone(read_rows("a.txt", b"x")[1])

    def test_too_large(self):
        self.assertIn("too large", read_rows("a.csv", b"x" * (MAX_FILE_SIZE + 1))[1])


class ValidateImportTests(SimpleTestCase):
    def test_happy_path_skips_blank_cells(self):
        grades, errors = check([["student_number", "Midterm", "Project"], ["111", "90", ""], ["222", "", "70.5"]])
        self.assertEqual(errors, [])
        self.assertEqual(
            [(g["enrollment_id"], g["assessment_id"], g["score"]) for g in grades],
            [(10, 1, Decimal("90")), (20, 2, Decimal("70.5"))],
        )

    def test_comma_decimal_accepted(self):
        grades, errors = check([["student_number", "Midterm"], ["111", "85,5"]])
        self.assertEqual((errors, grades[0]["score"]), ([], Decimal("85.5")))

    def test_empty_file(self):
        self.assertEqual(check([]), ([], ["The file is empty."]))
        self.assertEqual(check([[""], []])[1], ["The file is empty."])

    def test_missing_student_number_column(self):
        grades, errors = check([["Midterm", "Project"], ["90", "80"]])
        self.assertEqual(grades, [])
        self.assertIn("student_number", errors[0])

    def test_header_only(self):
        self.assertEqual(len(check([["student_number", "Midterm"]])[1]), 1)

    def test_collects_every_error_with_row_numbers(self):
        _, errors = check(
            [
                ["student_number", "Midterm", "Quiz"],
                ["111", "abc", ""],
                ["999", "50", ""],
                ["111", "50", ""],
                ["222", "101", ""],
                ["222", "-1", ""],
            ]
        )
        text = "\n".join(errors)
        self.assertIn("Row 1: unknown assessment column 'Quiz'", text)
        self.assertIn("Row 2, column Midterm", text)
        self.assertIn("Row 3: student 999 is not enrolled", text)
        self.assertIn("Row 4: student 111 appears more than once", text)
        self.assertIn("Row 5, column Midterm", text)
        self.assertIn("Row 6: student 222 appears more than once", text)
        self.assertEqual(len(errors), 6)
