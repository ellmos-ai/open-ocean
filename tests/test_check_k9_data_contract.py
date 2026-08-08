import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.check_k9_data_contract import create_database, extract_operations, validate_contract


ROOT = Path(__file__).parent.parent
CONTRACT = ROOT / "architecture" / "bach-k9-data-contract.v1.json"


class K9DataContractTests(unittest.TestCase):
    def test_contract_has_complete_nonaccepted_operation_matrices(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

        self.assertEqual([], validate_contract(contract))
        self.assertEqual(
            {"backup", "cleanup", "disable", "enable", "init", "pull", "push", "status", "sync"},
            {item["name"] for item in contract["profiles"]["dbsync"]["operations"]},
        )
        self.assertEqual(
            {"create", "delete", "list", "load"},
            {item["name"] for item in contract["profiles"]["snapshot"]["operations"]},
        )
        self.assertTrue(
            all(
                item["parity"] == "not-accepted"
                for profile in contract["profiles"].values()
                for item in profile["operations"]
            )
        )

    def test_operation_extraction_is_static_and_literal(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "handler.py"
            path.write_text(
                """
class ExampleHandler:
    @property
    def profile_name(self):
        return "example"
    def get_operations(self):
        return {"zeta": "Z", "alpha": "A"}
""",
                encoding="utf-8",
            )

            self.assertEqual(["alpha", "zeta"], extract_operations(path, "example"))

    def test_sql_fixtures_are_anonymized_and_form_the_expected_start_state(self):
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        fixture = contract["fixtures"]
        payload = "\n".join(
            (ROOT / fixture[key]).read_text(encoding="utf-8")
            for key in ("source_sql", "target_sql")
        )
        forbidden = ("C:\\Users", "OneDrive", "bach.db", "@")
        self.assertTrue(all(value not in payload for value in forbidden))

        with tempfile.TemporaryDirectory() as temp_name:
            source = Path(temp_name) / "source.sqlite"
            target = Path(temp_name) / "target.sqlite"
            create_database(source, ROOT / fixture["source_sql"])
            create_database(target, ROOT / fixture["target_sql"])
            connection = sqlite3.connect(source)
            try:
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM items").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM secrets").fetchone()[0])
            finally:
                connection.close()
            connection = sqlite3.connect(target)
            try:
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM items").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM secrets").fetchone()[0])
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
