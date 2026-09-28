import json
import tempfile
import textwrap
import unittest
from pathlib import Path

from tools.check_task_union_contract import (
    create_database,
    extract_transit_assignments,
    git_head,
    inspect_task_master,
    query,
    run_union_fixture,
    validate_contract,
)


ROOT = Path(__file__).parent.parent
CONTRACT = json.loads(
    (ROOT / "architecture" / "bach-task-union-contract.v1.json").read_text(encoding="utf-8")
)
SOURCE_SQL = ROOT / "tests" / "fixtures" / "task_union" / "source.sql"
EXPECTED = ROOT / "tests" / "fixtures" / "task_union" / "expected.json"

BANNED_STRINGS = ("@", "C:\\Users", "OneDrive", "bach.db")

EVENT_KINDS = {
    "task_created",
    "categorized",
    "deferred",
    "claim_requested",
    "claim_granted",
    "claim_released",
    "completed",
    "cancelled",
    "reopened",
    "tombstoned",
    "scope_migration_started",
    "scope_migration_committed",
    "scope_migration_rolled_back",
    "conflict_resolved",
}


class TaskUnionContractTests(unittest.TestCase):
    def test_a_contract_validates_clean(self):
        self.assertEqual([], validate_contract(CONTRACT))

    def test_b_fixtures_carry_no_live_environment_markers(self):
        for path in (SOURCE_SQL, EXPECTED):
            text = path.read_text(encoding="utf-8")
            for banned in BANNED_STRINGS:
                self.assertNotIn(banned, text, f"{path} contains banned marker {banned!r}")

    def test_c_source_sql_builds_five_row_backlog_and_empty_event_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "fixture.db"
            conn = create_database(db_path, SOURCE_SQL.read_text(encoding="utf-8"))
            backlog_count = query(conn, "SELECT COUNT(*) FROM backlog")[0][0]
            self.assertEqual(5, backlog_count)
            statuses = {row[0] for row in query(conn, "SELECT status FROM backlog")}
            self.assertLessEqual(
                statuses, {"pending", "in_progress", "done", "blocked", "deferred"}
            )
            event_count = query(conn, "SELECT COUNT(*) FROM union_events")[0][0]
            self.assertEqual(0, event_count)
            conn.close()

    def test_d_extract_transit_assignments_reads_literal_constants(self):
        module_source = textwrap.dedent(
            """\
            CONTRACT_VERSION = "v1alpha1"
            VALID_EVENT_KINDS = {
                "task_created",
                "categorized",
                "deferred",
                "claim_requested",
                "claim_granted",
                "claim_released",
                "completed",
                "cancelled",
                "reopened",
                "tombstoned",
                "scope_migration_started",
                "scope_migration_committed",
                "scope_migration_rolled_back",
                "conflict_resolved",
            }


            def compute_logical_task_id(source, local_id):
                return str(source) + ":" + str(local_id)
            """
        )
        with tempfile.TemporaryDirectory() as tmp:
            module_path = Path(tmp) / "models.py"
            module_path.write_text(module_source, encoding="utf-8")
            assignments = extract_transit_assignments(module_path)
        self.assertEqual("v1alpha1", assignments["CONTRACT_VERSION"])
        self.assertEqual(EVENT_KINDS, set(assignments["VALID_EVENT_KINDS"]))

    def test_e_union_fixture_projection_matches_expected_document(self):
        self.assertEqual([], run_union_fixture(CONTRACT, ROOT))


if __name__ == "__main__":
    unittest.main()
