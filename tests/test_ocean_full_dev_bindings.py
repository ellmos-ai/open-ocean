"""Portable acceptance tests for OCEAN's shipped Full Dev integration overlay."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.resolve_bundles import (
    ResolvedComponent,
    load_component_bindings,
    resolve_module,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FULL_DEV_BINDINGS = REPO_ROOT / "architecture" / "ocean-full-dev.component-bindings.v1.json"


class ShippedFullDevBindingTests(unittest.TestCase):
    def test_automation_registry_resolves_through_automation_master_provider(self):
        """Removing the explicit crosswalk must reopen the required Full Dev gap."""
        with tempfile.TemporaryDirectory() as temporary:
            catalog = Path(temporary) / "modules.catalog.json"
            catalog.write_text(
                json.dumps({
                    "modules": [{
                        "id": "automation-master",
                        "source_of_truth": {
                            "type": "git-repository",
                            "repository": "https://github.com/dev-bricks/automation-master.git",
                        },
                        "resolved_source": "automation-master",
                        "provides": ["automation.registry"],
                    }],
                }),
                encoding="utf-8",
            )
            component = ResolvedComponent(
                ref="module:automation-registry",
                kind="module",
                requirement="required",
            )

            resolve_module(
                component,
                catalog,
                load_component_bindings(FULL_DEV_BINDINGS),
            )

        self.assertEqual(component.detail["catalog_id"], "automation-master")
        self.assertTrue(component.detail["catalog_repository_matches_binding"])
        self.assertEqual(
            component.detail["binding"]["required_provides"],
            ["automation.registry"],
        )
        self.assertFalse(component.detail["binding"]["provider_verified"])

    def test_automation_runtime_is_a_distinct_logical_role_of_the_pinned_provider(self):
        """FULL OCEAN must close the runtime gap without merging role ownership."""
        with tempfile.TemporaryDirectory() as temporary:
            catalog = Path(temporary) / "modules.catalog.json"
            catalog.write_text(
                json.dumps({
                    "modules": [{
                        "id": "automation-master",
                        "source_of_truth": {
                            "type": "git-repository",
                            "repository": "https://github.com/dev-bricks/automation-master.git",
                        },
                        "resolved_source": "automation-master",
                        "provides": [
                            "automation.registry",
                            "automation.runtime.observe",
                            "automation.runtime.receipt",
                            "automation.runtime.statistics",
                        ],
                    }],
                }),
                encoding="utf-8",
            )
            bindings = load_component_bindings(FULL_DEV_BINDINGS)
            component = ResolvedComponent(
                ref="module:automation-runtime",
                kind="module",
                requirement="required",
            )

            resolve_module(component, catalog, bindings)

        runtime = bindings["bindings"]["module:automation-runtime"]
        registry = bindings["bindings"]["module:automation-registry"]
        self.assertEqual(component.detail["catalog_id"], "automation-master")
        self.assertTrue(component.detail["catalog_repository_matches_binding"])
        self.assertEqual(
            runtime["required_provides"],
            [
                "automation.runtime.observe",
                "automation.runtime.receipt",
                "automation.runtime.statistics",
            ],
        )
        self.assertEqual(runtime["catalog_id"], registry["catalog_id"])
        self.assertEqual(runtime["repository"], registry["repository"])
        self.assertNotEqual(runtime["placement_id"], registry["placement_id"])
        self.assertFalse(component.detail["binding"]["provider_verified"])


if __name__ == "__main__":
    unittest.main()
