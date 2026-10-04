# ruff: noqa: E402
"""Tests for the ustg-invoice-check checker (slice S10, task 1516)."""

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKER_PATH = ROOT / "tools" / "check_ustg_invoice.py"

_spec = importlib.util.spec_from_file_location(
    "check_ustg_invoice", str(CHECKER_PATH)
)
checker = importlib.util.module_from_spec(_spec)
sys.modules["check_ustg_invoice"] = checker
_spec.loader.exec_module(checker)

BANNED_STRINGS = checker.BANNED_STRINGS
EXPECTED_EXPECTED_SCHEMA = checker.EXPECTED_EXPECTED_SCHEMA
check_expected = checker.check_expected
generate_dispute_letter = checker.generate_dispute_letter
load_json = checker.load_json
run_all = checker.run_all
validate_contract = checker.validate_contract
validate_invoice = checker.validate_invoice

CONTRACT_PATH = ROOT / "architecture" / "bach-ustg-invoice-check-contract.v1.json"
CONTRACT = load_json(CONTRACT_PATH)
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "ustg_invoice"


def _valid_invoice():
    return load_json(ROOT / CONTRACT["fixtures"]["valid_invoice"])


def _deficient_invoices():
    return [
        load_json(ROOT / rel_path)
        for rel_path in CONTRACT["fixtures"]["deficient_invoices"]
    ]


class UstgInvoiceCheckTests(unittest.TestCase):
    maxDiff = None

    def test_a_contract_shape(self):
        self.assertEqual(validate_contract(CONTRACT), [])

    def test_b_no_banned_strings_in_fixture_files(self):
        fixture_paths = sorted(FIXTURE_DIR.glob("*.json"))
        self.assertTrue(fixture_paths)
        for fixture_path in fixture_paths:
            text = fixture_path.read_text(encoding="utf-8")
            for token in BANNED_STRINGS:
                self.assertNotIn(token, text)

    def test_c_valid_invoice_is_green(self):
        self.assertEqual(validate_invoice(_valid_invoice(), CONTRACT), [])

    def test_d_seven_mandatory_statements_in_contract(self):
        statements = CONTRACT["mandatory_statements"]
        self.assertEqual(len(statements), 7)
        references = [statement["legal_reference"] for statement in statements]
        self.assertEqual(len(set(references)), 7)
        for number in range(1, 8):
            self.assertIn(f"§ 14 Abs. 4 Nr. {number} UStG", references)

    def test_e_each_missing_statement_negative(self):
        for statement in CONTRACT["mandatory_statements"]:
            invoice = _valid_invoice()
            for field in statement["fields"]:
                invoice.pop(field)
            if statement["rule"] == "all-fields-required":
                expected_count = len(statement["fields"])
            else:
                expected_count = 1
            problems = validate_invoice(invoice, CONTRACT)
            self.assertEqual(len(problems), expected_count)
            self.assertIn(statement["statement_id"], problems[0])
            self.assertIn(statement["legal_reference"], problems[0])

    def test_f_tax_identification_or_rule(self):
        invoice = _valid_invoice()
        invoice.pop("vat_id")
        self.assertEqual(validate_invoice(invoice, CONTRACT), [])
        invoice = _valid_invoice()
        invoice.pop("tax_number")
        self.assertEqual(validate_invoice(invoice, CONTRACT), [])

    def test_g_line_item_field_negative(self):
        invoice = _valid_invoice()
        invoice["line_items"][0].pop("description")
        problems = validate_invoice(invoice, CONTRACT)
        self.assertEqual(len(problems), 1)
        self.assertIn("nr2_goods", problems[0])
        self.assertTrue(generate_dispute_letter(invoice, CONTRACT))

    def test_h_dispute_letter_empty_on_complete_invoice(self):
        self.assertEqual(generate_dispute_letter(_valid_invoice(), CONTRACT), "")

    def test_i_dispute_letter_per_deficiency(self):
        statements = {
            statement["statement_id"]: statement
            for statement in CONTRACT["mandatory_statements"]
        }
        for invoice in _deficient_invoices():
            letter = generate_dispute_letter(invoice, CONTRACT)
            self.assertTrue(letter)
            statement = statements[invoice["deficient_for"]]
            self.assertIn(statement["legal_reference"], letter)
            self.assertIn(statement["label"], letter)
            self.assertIn(statement["remedy"], letter)
            self.assertIn("Bestreitungsschreiben", letter)
            self.assertIn("§ 15 Abs. 1 Satz 1 Nr. 1 UStG", letter)
            self.assertIn("§ 14 Abs. 4 Nr. 8 UStG", letter)

    def test_j_expected_fixture_fields(self):
        expected = load_json(ROOT / CONTRACT["fixtures"]["expected"])
        self.assertEqual(expected["schema"], EXPECTED_EXPECTED_SCHEMA)
        self.assertEqual(expected["mandatory_statement_count"], 7)
        self.assertEqual(expected["valid_invoice"]["problem_count"], 0)
        self.assertEqual(expected["valid_invoice"]["dispute_letter"], "")

    def test_k_check_expected_and_run_all(self):
        self.assertEqual(check_expected(CONTRACT, ROOT), [])
        self.assertEqual(run_all(CONTRACT_PATH), [])


if __name__ == "__main__":
    unittest.main()
