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
    def test_account_projection_pipeline_has_exact_publish_and_verify_pins(self):
        with tempfile.TemporaryDirectory() as temporary:
            catalog = Path(temporary) / "modules.catalog.json"
            catalog.write_text(
                json.dumps(
                    {
                        "modules": [
                            {
                                "id": "accounts-core",
                                "source_of_truth": {
                                    "type": "git-repository",
                                    "repository": "https://github.com/ellmos-ai/accounts-core",
                                },
                                "resolved_source": "accounts-core",
                                "provides": ["accounts.transit.projection"],
                            },
                            {
                                "id": "sqlite-transit-sync",
                                "source_of_truth": {
                                    "type": "git-repository",
                                    "repository": "https://github.com/ellmos-ai/sqlite-transit-sync",
                                },
                                "resolved_source": "sqlite-transit-sync",
                                "provides": ["projection.readonly.verify"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            bindings = load_component_bindings(FULL_DEV_BINDINGS)
            accounts = ResolvedComponent(
                ref="module:accounts-core", kind="module", requirement="recommended"
            )
            verifier = ResolvedComponent(
                ref="module:sqlite-transit-sync",
                kind="module",
                requirement="recommended",
            )
            resolve_module(accounts, catalog, bindings)
            resolve_module(verifier, catalog, bindings)

        self.assertTrue(accounts.detail["catalog_repository_matches_binding"])
        self.assertTrue(verifier.detail["catalog_repository_matches_binding"])
        self.assertEqual(
            accounts.detail["binding"]["commit"],
            "588ab7d2db274621c5982a3234f2fb540627f664",
        )
        self.assertEqual(
            verifier.detail["binding"]["commit"],
            "d9d517d6711fa9597c960c127cf6476f3af9d072",
        )
        self.assertEqual(
            accounts.detail["binding"]["required_provides"],
            ["accounts.transit.projection"],
        )
        self.assertEqual(
            verifier.detail["binding"]["required_provides"],
            ["projection.readonly.verify"],
        )

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
