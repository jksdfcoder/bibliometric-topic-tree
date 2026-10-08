"""Inventory gate for component adoption.

The brief requires an adopt row to carry a commit, entry points, license
paths, and verification evidence. Empty values are not evidence.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
INVENTORY = ROOT / "docs/decisions/component_inventory.json"

REQUIRED = (
    "repository_url",
    "commit",
    "entry_points",
    "license_paths",
    "model_revision",
    "training_provenance",
    "verified_functions",
    "gaps",
    "minimal_changes",
    "verification_evidence",
    "decision",
)
DECISIONS = {"adopt", "candidate", "reject"}
SHA = re.compile(r"^[0-9a-f]{40}$")


def adopt_fields_present(row):
    return bool(
        row["commit"]
        and row["entry_points"]
        and row["license_paths"]
        and row["verification_evidence"]
    )


class ComponentInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(INVENTORY.read_text())
        cls.rows = cls.payload["components"]

    def test_brief_adopt_rows_have_commit_entry_license_and_evidence(self):
        rows = self.rows
        for row in rows:
            if row["decision"] == "adopt":
                assert row["commit"] and row["entry_points"] and row["license_paths"]
                assert row["verification_evidence"]

    def test_required_fields_and_known_decisions(self):
        self.assertGreater(len(self.rows), 0)
        ids = []
        for row in self.rows:
            missing = [key for key in REQUIRED if key not in row]
            self.assertEqual(missing, [], row.get("id"))
            self.assertIn(row["decision"], DECISIONS)
            self.assertTrue(row.get("id"))
            ids.append(row["id"])
        self.assertEqual(len(ids), len(set(ids)))

    def test_adopt_rows_are_full_shas_with_a_passed_probe(self):
        for row in self.rows:
            if row["decision"] != "adopt":
                continue
            self.assertTrue(adopt_fields_present(row), row["id"])
            self.assertRegex(row["commit"], SHA)
            self.assertIsInstance(row["entry_points"], list)
            self.assertTrue(all(isinstance(item, str) and item for item in row["entry_points"]))
            self.assertIsInstance(row["license_paths"], list)
            self.assertTrue(all(isinstance(item, str) and item for item in row["license_paths"]))
            self.assertFalse(
                any(path.upper().startswith("README") for path in row["license_paths"]),
                row["id"],
            )
            evidence = row["verification_evidence"]
            self.assertIsInstance(evidence, dict)
            self.assertEqual(evidence.get("probe_status"), "passed")
            self.assertTrue(evidence.get("command"))
            self.assertTrue(evidence.get("device"))
            self.assertIn("network_required", evidence)
            self.assertIsNone(evidence.get("failure"))

    def test_empty_adopt_fields_do_not_pass_the_gate(self):
        filled = {
            "commit": "a" * 40,
            "entry_points": ["pkg.entry"],
            "license_paths": ["LICENSE"],
            "verification_evidence": {"probe_status": "passed"},
        }
        self.assertTrue(adopt_fields_present(filled))
        for key, empty in (
            ("commit", ""),
            ("entry_points", []),
            ("license_paths", []),
            ("verification_evidence", ""),
            ("verification_evidence", {}),
        ):
            broken = dict(filled)
            broken[key] = empty
            self.assertFalse(adopt_fields_present(broken), key)


if __name__ == "__main__":
    unittest.main()
