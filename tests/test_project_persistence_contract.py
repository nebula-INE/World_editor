"""Cross-platform .axral.json v1 persistence contract tests."""

import json
import unittest

from core.events import Effect, Event
from core.models import stable_entity_id, stable_relation_id


class ProjectPersistenceContractTests(unittest.TestCase):
    def project_fixture(self):
        relation_id = stable_relation_id("主人公->東京#0")
        return {
            "format": "axral-world-project",
            "schema_version": 1,
            "text": "[主人公:Character]\n[東京:Location]\n主人公 -> 東京 : 移動",
            "events": [
                Event(
                    id="evt_contract_001",
                    timestamp=42,
                    type="移動",
                    participants=[stable_entity_id("主人公")],
                    effects=[
                        Effect(
                            kind="relation_status",
                            target_id=relation_id,
                            payload={"status": "hypothetical"},
                        )
                    ],
                    is_snapshot_point=True,
                    metadata={"note": "日本語のEvent"},
                ).to_dict()
            ],
            "graph_positions": {
                stable_entity_id("主人公"): {"x": 123.5, "y": -40},
                stable_entity_id("東京"): {"x": 600, "y": 240},
            },
            "timeline": {
                "mode": True,
                "timestamp": 42,
                "visible_layers": ["Su-ken", "Kan-ken"],
            },
            "ignored_candidates": [[3, "主人公", "東京", "移動"]],
        }

    def test_json_round_trip_preserves_all_v1_fields(self):
        project = self.project_fixture()
        restored = json.loads(json.dumps(project, ensure_ascii=False))
        self.assertEqual(restored["format"], "axral-world-project")
        self.assertEqual(restored["schema_version"], 1)
        self.assertEqual(restored["text"], project["text"])
        self.assertEqual(restored["events"], project["events"])
        self.assertEqual(
            restored["events"][0]["effects"][0]["target_id"],
            stable_relation_id("主人公->東京#0"),
        )
        self.assertEqual(restored["graph_positions"], project["graph_positions"])
        self.assertEqual(restored["timeline"], project["timeline"])
        self.assertEqual(restored["ignored_candidates"], project["ignored_candidates"])

    def test_ignored_candidate_signature_contract(self):
        valid = [3, "主人公", "東京", "移動"]
        invalid = [
            [3, "主人公", "東京"],
            ["3", "主人公", "東京", "移動"],
            [3, "主人公", "東京", None],
        ]

        def is_portable_signature(value):
            return (
                isinstance(value, list)
                and len(value) == 4
                and isinstance(value[0], int)
                and not isinstance(value[0], bool)
                and all(isinstance(part, str) for part in value[1:])
            )

        self.assertTrue(is_portable_signature(valid))
        for signature in invalid:
            with self.subTest(signature=signature):
                self.assertFalse(is_portable_signature(signature))


if __name__ == "__main__":
    unittest.main()
