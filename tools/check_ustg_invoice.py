"""Validate the ustg-invoice-check contract, fixtures and dispute letters.

The checker validates schema and fixture conformance only for the
ustg-invoice-check slice (S10, BACH task 1516): it verifies the contract
structure, applies the seven mandatory invoice statements of § 14 Abs. 4
UStG to synthetic invoices and confirms the generated dispute letter. It
performs no live cutover, no runtime wiring and provides no legal or
fiscal advice.
"""

import argparse
import json
import re
import sys
from pathlib import Path

EXPECTED_SCHEMA = "ellmos.open-ocean-bach-ustg-invoice-check.v1"
EXPECTED_INVOICE_SCHEMA = "ellmos.open-ocean-ustg-invoice.v1"
EXPECTED_EXPECTED_SCHEMA = "ellmos.open-ocean-ustg-invoice-check-expected.v1"
EXPECTED_CHECK_SCOPE = "ustg-invoice-check"
EXPECTED_STATUS = "ustg-invoice-check-schema-specified-fixtures-green-no-live-cutover"
EXPECTED_TICKET = "T-20260920-823767362"
EXPECTED_SLICE = "S10"
EXPECTED_TASK = 1516
EXPECTED_COMPONENTS = ["doc_handler", "finance_assist"]
EXPECTED_STATEMENT_COUNT = 7
EXPECTED_LEGAL_REFERENCES = [
    "§ 14 Abs. 4 Nr. 1 UStG",
    "§ 14 Abs. 4 Nr. 2 UStG",
    "§ 14 Abs. 4 Nr. 3 UStG",
    "§ 14 Abs. 4 Nr. 4 UStG",
    "§ 14 Abs. 4 Nr. 5 UStG",
    "§ 14 Abs. 4 Nr. 6 UStG",
    "§ 14 Abs. 4 Nr. 7 UStG",
]
REQUIRED_TOP_KEYS = [
    "schema",
    "status",
    "recorded_at",
    "claim_boundary",
    "hold",
    "provenance",
    "check_scope",
    "components",
    "invoice_schema",
    "required_invoice_fields",
    "mandatory_statements",
    "dispute_loop",
    "fixtures",
    "classification",
    "next_gates",
]
STATEMENT_KEYS = [
    "statement_id",
    "legal_reference",
    "label",
    "fields",
    "rule",
    "remedy",
]
VALID_RULES = [
    "all-fields-required",
    "line-items-required",
    "required",
    "any-field-required",
]
BANNED_STRINGS = ("@", "C:\\Users", "OneDrive", "bach.db")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LINE_ITEM_FIELDS = ["quantity", "description"]
DISPUTE_LOOP_TRIGGER = "one_or_more_missing_mandatory_statements"
EXPECTED_LETTER_PARTS = ["empfehlung", "ruege"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _banned_problems(obj):
    text = json.dumps(obj, sort_keys=True)
    return [
        f"banned string in payload: {token!r}"
        for token in BANNED_STRINGS
        if token in text
    ]


def _is_missing(value):
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return value is None


def _statement_problems(invoice, statement):
    if not isinstance(statement, dict):
        return []
    statement_id = statement.get("statement_id")
    legal_reference = statement.get("legal_reference")
    prefix = f"missing invoice field for {statement_id} ({legal_reference})"
    fields = statement.get("fields")
    rule = statement.get("rule")
    problems = []
    if rule == "any-field-required":
        if all(_is_missing(invoice.get(field)) for field in fields):
            problems.append(prefix + ": " + " or ".join(fields))
    elif rule == "line-items-required":
        for field in fields:
            if _is_missing(invoice.get(field)):
                problems.append(f"{prefix}: {field}")
        items = invoice.get(fields[0]) if fields else None
        if isinstance(items, list):
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    problems.append(
                        f"{prefix}: line item {index} must be a JSON object"
                    )
                    continue
                for sub_field in LINE_ITEM_FIELDS:
                    if _is_missing(item.get(sub_field)):
                        problems.append(
                            f"{prefix}: line item {index}: {sub_field}"
                        )
    else:
        for field in fields:
            if _is_missing(invoice.get(field)):
                problems.append(f"{prefix}: {field}")
    return problems


def validate_invoice(invoice, contract):
    if not isinstance(invoice, dict):
        return ["invoice must be a JSON object"]
    problems = []
    schema = invoice.get("schema")
    if schema != contract.get("invoice_schema"):
        problems.append(f"invoice schema mismatch: {schema!r}")
    for statement in contract.get("mandatory_statements", []):
        problems.extend(_statement_problems(invoice, statement))
    problems.extend(_banned_problems(invoice))
    return problems


def generate_dispute_letter(invoice, contract):
    if not isinstance(invoice, dict):
        return ""
    deficient_statements = [
        statement
        for statement in contract.get("mandatory_statements", [])
        if _statement_problems(invoice, statement)
    ]
    if not deficient_statements:
        return ""
    lines = [
        "Bestreitungsschreiben - formelle Mängelrüge (Rechnungsprüfung)",
        "",
        "Sehr geehrte Damen und Herren,",
        "",
    ]
    sequential_number = invoice.get("sequential_number")
    if not _is_missing(sequential_number):
        lines.append(f"Gegenstand: Rechnungsnr. {sequential_number}")
        lines.append("")
    lines.append(
        "die vorliegende Rechnung genügt nicht den formalen Anforderungen "
        "des § 14 Abs. 4 UStG und wird im Umfang der fehlenden Pflichtangaben "
        "formell bestritten, bis eine ordnungsgemäße Rechnung vorliegt. "
        "Es fehlen folgende Pflichtangaben:"
    )
    lines.append("")
    for position, statement in enumerate(deficient_statements, start=1):
        header = f"{position}. {statement['label']} ({statement['legal_reference']})"
        lines.append(header)
        lines.append(
            "   Rüge: Die Rechnung weist diese Pflichtangabe nicht aus und "
            "genügt damit nicht den formalen Anforderungen des "
            "§ 14 Abs. 4 UStG."
        )
        lines.append(f"   Empfehlung: {statement['remedy']}")
    lines.append("")
    lines.append(
        "Ohne ordnungsgemäße Rechnung bleibt der Vorsteuerabzug "
        "ausgeschlossen (§ 15 Abs. 1 Satz 1 Nr. 1 UStG). Wir bitten um "
        "Rechnungsberichtigung nach § 14 Abs. 7 UStG; für Sonderfälle "
        "verbleibt es bei § 14 Abs. 4 Nr. 8 UStG."
    )
    lines.append("")
    lines.append("Mit freundlichen Grüßen")
    lines.append("")
    lines.append(
        "Automatisch erzeugtes Schema-Prüfartefakt des ustg-invoice-check "
        "(Slice S10, BACH task 1516). Dieses Schreiben ist ein "
        "Prüfartefakt ohne Rechtswirkung und keine Steuer- oder "
        "Rechtsberatung."
    )
    return "\n".join(lines)


def validate_contract(contract):
    if not isinstance(contract, dict):
        return ["contract must be a JSON object"]
    problems = []
    schema = contract.get("schema")
    if schema != EXPECTED_SCHEMA:
        problems.append(f"schema mismatch: {schema!r}")
    for key in REQUIRED_TOP_KEYS:
        if key not in contract:
            problems.append(f"missing top-level key: {key}")
    hold = contract.get("hold")
    if not isinstance(hold, dict):
        problems.append("hold must be a JSON object")
    else:
        if hold.get("bach_mode") != "read-only":
            problems.append(f"hold bach_mode mismatch: {hold.get('bach_mode')!r}")
        hold_rule = hold.get("rule")
        if not isinstance(hold_rule, str) or not hold_rule.strip():
            problems.append("hold rule must be a non-empty string")
    status = contract.get("status")
    if status != EXPECTED_STATUS:
        problems.append(f"status mismatch: {status!r}")
    check_scope = contract.get("check_scope")
    if check_scope != EXPECTED_CHECK_SCOPE:
        problems.append(f"check_scope mismatch: {check_scope!r}")
    invoice_schema = contract.get("invoice_schema")
    if invoice_schema != EXPECTED_INVOICE_SCHEMA:
        problems.append(f"invoice_schema mismatch: {invoice_schema!r}")
    recorded_at = contract.get("recorded_at")
    if not isinstance(recorded_at, str) or not DATE_RE.match(recorded_at):
        problems.append(f"recorded_at must be YYYY-MM-DD: {recorded_at!r}")
    claim_boundary = contract.get("claim_boundary")
    if not isinstance(claim_boundary, str) or not claim_boundary.strip():
        problems.append("claim_boundary must be a non-empty string")
    provenance = contract.get("provenance")
    if not isinstance(provenance, dict):
        problems.append("provenance must be a JSON object")
    else:
        ticket = provenance.get("ticket")
        if ticket != EXPECTED_TICKET:
            problems.append(f"provenance ticket mismatch: {ticket!r}")
        slice_name = provenance.get("slice")
        if slice_name != EXPECTED_SLICE:
            problems.append(f"provenance slice mismatch: {slice_name!r}")
        task = provenance.get("task")
        if task != EXPECTED_TASK:
            problems.append(f"provenance task mismatch: {task!r}")
    components = contract.get("components")
    if components != EXPECTED_COMPONENTS:
        problems.append(f"components mismatch: {components!r}")
    statements = contract.get("mandatory_statements")
    legal_references = []
    field_union = []
    if not isinstance(statements, list):
        problems.append("mandatory_statements must be a list")
    else:
        if len(statements) != EXPECTED_STATEMENT_COUNT:
            problems.append(
                "mandatory_statements must have "
                f"{EXPECTED_STATEMENT_COUNT} entries, got {len(statements)}"
            )
        statement_ids = []
        for statement in statements:
            if not isinstance(statement, dict):
                problems.append("mandatory statement must be a JSON object")
                continue
            for key in STATEMENT_KEYS:
                if key not in statement:
                    problems.append(f"mandatory statement missing key: {key}")
            statement_id = statement.get("statement_id")
            if isinstance(statement_id, str) and statement_id.strip():
                if statement_id in statement_ids:
                    problems.append(f"duplicate statement_id: {statement_id}")
                statement_ids.append(statement_id)
            else:
                problems.append(
                    f"statement_id must be a non-empty string: {statement_id!r}"
                )
            legal_reference = statement.get("legal_reference")
            if isinstance(legal_reference, str) and legal_reference.strip():
                legal_references.append(legal_reference)
            else:
                problems.append(
                    "legal_reference must be a non-empty string: "
                    f"{legal_reference!r}"
                )
            rule = statement.get("rule")
            if rule not in VALID_RULES:
                problems.append(f"invalid rule for {statement_id}: {rule!r}")
            fields = statement.get("fields")
            fields_ok = (
                isinstance(fields, list)
                and len(fields) > 0
                and all(
                    isinstance(field, str) and field.strip() for field in fields
                )
            )
            if not fields_ok:
                problems.append(
                    f"fields must be a non-empty string list: {fields!r}"
                )
            else:
                field_union.extend(fields)
            for text_key in ("label", "remedy"):
                text_value = statement.get(text_key)
                if not isinstance(text_value, str) or not text_value.strip():
                    problems.append(
                        f"{text_key} must be a non-empty string: {text_value!r}"
                    )
        if sorted(legal_references) != sorted(EXPECTED_LEGAL_REFERENCES):
            problems.append(
                f"legal references mismatch: {sorted(legal_references)!r}"
            )
    required_fields = contract.get("required_invoice_fields")
    if (
        not isinstance(required_fields, list)
        or not all(isinstance(field, str) for field in required_fields)
    ):
        problems.append("required_invoice_fields must be a list of strings")
    elif sorted(required_fields) != sorted(field_union):
        problems.append(
            "required_invoice_fields must match the statement field union"
        )
    dispute_loop = contract.get("dispute_loop")
    if not isinstance(dispute_loop, dict):
        problems.append("dispute_loop must be a JSON object")
    else:
        trigger = dispute_loop.get("trigger")
        if trigger != DISPUTE_LOOP_TRIGGER:
            problems.append(f"dispute_loop trigger mismatch: {trigger!r}")
        letter_parts = dispute_loop.get("letter_parts")
        if (
            not isinstance(letter_parts, list)
            or not all(isinstance(part, str) for part in letter_parts)
            or sorted(letter_parts) != EXPECTED_LETTER_PARTS
        ):
            problems.append(
                f"dispute_loop letter_parts mismatch: {letter_parts!r}"
            )
        if dispute_loop.get("complete_invoice_letter") != "":
            problems.append("dispute_loop complete_invoice_letter must be empty")
        resolution = dispute_loop.get("resolution")
        if not isinstance(resolution, str) or not resolution.strip():
            problems.append("dispute_loop resolution must be a non-empty string")
    fixtures = contract.get("fixtures")
    if not isinstance(fixtures, dict):
        problems.append("fixtures must be a JSON object")
    else:
        valid_invoice = fixtures.get("valid_invoice")
        if not isinstance(valid_invoice, str) or not valid_invoice.strip():
            problems.append("fixtures valid_invoice must be a path string")
        deficient_invoices = fixtures.get("deficient_invoices")
        if (
            not isinstance(deficient_invoices, list)
            or len(deficient_invoices) != EXPECTED_STATEMENT_COUNT
            or not all(isinstance(name, str) for name in deficient_invoices)
        ):
            problems.append(
                "fixtures deficient_invoices must be a list of "
                f"{EXPECTED_STATEMENT_COUNT} path strings"
            )
        expected = fixtures.get("expected")
        if not isinstance(expected, str) or not expected.strip():
            problems.append("fixtures expected must be a path string")
    classification = contract.get("classification")
    if not isinstance(classification, dict):
        problems.append("classification must be a JSON object")
    else:
        parity = classification.get("parity")
        if parity != "not-accepted":
            problems.append(f"classification parity mismatch: {parity!r}")
        if classification.get("live_cutover") is not False:
            problems.append("classification live_cutover must be false")
    next_gates = contract.get("next_gates")
    if not isinstance(next_gates, list) or len(next_gates) < 3:
        problems.append("next_gates must be a list with at least 3 entries")
    problems.extend(_banned_problems(contract))
    return problems


def check_expected(contract, repo_root):
    fixtures = contract.get("fixtures")
    if not isinstance(fixtures, dict):
        return ["contract fixtures must be a JSON object"]
    problems = []
    expected_rel = fixtures.get("expected")
    if not isinstance(expected_rel, str) or not expected_rel.strip():
        return ["contract fixtures must define expected"]
    expected_path = repo_root / expected_rel
    if not expected_path.exists():
        return [f"expected fixture missing: {expected_path}"]
    expected = load_json(expected_path)
    statements = contract.get("mandatory_statements")
    if not isinstance(statements, list):
        return ["contract mandatory_statements must be a list"]
    statement_ids = [
        statement.get("statement_id") for statement in statements
    ]
    expected_schema = expected.get("schema")
    if expected_schema != EXPECTED_EXPECTED_SCHEMA:
        problems.append(f"expected schema mismatch: {expected_schema!r}")
    expected_count = expected.get("mandatory_statement_count")
    if expected_count != len(statements):
        problems.append(
            f"expected mandatory_statement_count mismatch: {expected_count!r}"
        )
    expected_valid = expected.get("valid_invoice")
    valid_rel = fixtures.get("valid_invoice")
    if not isinstance(expected_valid, dict):
        problems.append("expected valid_invoice must be a JSON object")
    elif not isinstance(valid_rel, str):
        problems.append("contract fixtures must define valid_invoice")
    else:
        valid_path = repo_root / valid_rel
        if not valid_path.exists():
            problems.append(f"valid invoice fixture missing: {valid_path}")
        else:
            valid_invoice = load_json(valid_path)
            valid_problems = validate_invoice(valid_invoice, contract)
            if len(valid_problems) != expected_valid.get("problem_count"):
                problems.append(
                    "expected valid problem_count mismatch: "
                    f"{expected_valid.get('problem_count')!r}"
                )
            valid_letter = generate_dispute_letter(valid_invoice, contract)
            if valid_letter != expected_valid.get("dispute_letter"):
                problems.append("expected valid dispute_letter mismatch")
    expected_deficient = expected.get("deficient_invoice")
    if not isinstance(expected_deficient, dict):
        problems.append("expected deficient_invoice must be a JSON object")
    else:
        expected_deficient_count = expected_deficient.get("problem_count")
        letter_contains = expected_deficient.get("dispute_letter_contains")
        for rel_path in fixtures.get("deficient_invoices", []):
            deficient_path = repo_root / rel_path
            if not deficient_path.exists():
                problems.append(
                    f"deficient invoice fixture missing: {deficient_path}"
                )
                continue
            deficient_invoice = load_json(deficient_path)
            if not isinstance(deficient_invoice, dict):
                problems.append(
                    f"deficient invoice must be a JSON object: {rel_path}"
                )
                continue
            deficient_for = deficient_invoice.get("deficient_for")
            if deficient_for not in statement_ids:
                problems.append(
                    f"deficient_for not in contract: {deficient_for!r}"
                )
                continue
            invoice_problems = validate_invoice(deficient_invoice, contract)
            if not invoice_problems:
                problems.append(
                    f"deficient invoice must have problems: {rel_path}"
                )
                continue
            if not any(deficient_for in problem for problem in invoice_problems):
                problems.append(
                    f"deficient invoice missing statement problem: {rel_path}"
                )
            for problem in invoice_problems:
                if deficient_for not in problem:
                    problems.append(f"unexpected extra problem: {problem}")
            if len(invoice_problems) != expected_deficient_count:
                problems.append(
                    f"expected deficient problem_count mismatch for {rel_path}: "
                    f"{len(invoice_problems)} != {expected_deficient_count!r}"
                )
            letter = generate_dispute_letter(deficient_invoice, contract)
            if not letter:
                problems.append(f"dispute letter missing: {rel_path}")
            if isinstance(letter_contains, list):
                for fragment in letter_contains:
                    if fragment not in letter:
                        problems.append(
                            "dispute letter missing fragment "
                            f"{fragment!r}: {rel_path}"
                        )
    expected_loop = expected.get("dispute_loop")
    if not isinstance(expected_loop, dict):
        problems.append("expected dispute_loop must be a JSON object")
    else:
        expected_trigger = expected_loop.get("trigger")
        if expected_trigger != DISPUTE_LOOP_TRIGGER:
            problems.append(
                f"expected dispute_loop trigger mismatch: {expected_trigger!r}"
            )
        letters_per_invoice = expected_loop.get("letters_per_deficient_invoice")
        if letters_per_invoice != 1:
            problems.append(
                "expected letters_per_deficient_invoice mismatch: "
                f"{letters_per_invoice!r}"
            )
    return problems


def run_all(contract_path):
    path = Path(contract_path)
    if not path.exists():
        repo_root = Path(__file__).resolve().parent.parent
        path = repo_root / contract_path
    if not path.exists():
        return [f"contract not found: {contract_path}"]
    contract = load_json(path)
    contract_root = path.resolve().parent.parent
    problems = []
    problems.extend(validate_contract(contract))
    fixtures = contract.get("fixtures")
    if isinstance(fixtures, dict) and isinstance(
        fixtures.get("valid_invoice"), str
    ):
        valid_path = contract_root / fixtures["valid_invoice"]
        if not valid_path.exists():
            problems.append(f"valid invoice fixture missing: {valid_path}")
        else:
            valid_invoice = load_json(valid_path)
            for problem in validate_invoice(valid_invoice, contract):
                problems.append(f"valid invoice fixture problem: {problem}")
    else:
        problems.append("contract fixtures must define valid_invoice")
    problems.extend(check_expected(contract, contract_root))
    return problems


def main():
    parser = argparse.ArgumentParser(
        description="Validate the ustg-invoice-check contract and fixtures."
    )
    parser.add_argument(
        "--contract",
        default="architecture/bach-ustg-invoice-check-contract.v1.json",
        help="path to the ustg-invoice-check contract JSON",
    )
    args = parser.parse_args()
    problems = run_all(args.contract)
    if problems:
        print("ustg-invoice-check check: FAILED")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        "ustg-invoice-check check: PASSED "
        "(schema+fixture conformance, not legal validation of real invoices)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())