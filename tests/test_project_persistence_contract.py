"""Cross-platform .axral.json v1 persistence codec tests."""

import json
import unittest
from pathlib import Path

from core.events import Effect, Event
from core.models import LAYER_HIERARCHY, stable_entity_id, stable_relation_id
from core.project import build_project, parse_project


class ProjectPersistenceContractTests(unittest.TestCase):
    def project_fixture(self):
        relation_id = stable_relation_id("主人公->東京#0")
        event = Event(
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
        )
        return build_project(
            text="[主人公:Character]\n[東京:Location]\n主人公 -> 東京 : 移動",
            events=[event],
            graph_positions={
                stable_entity_id("主人公"): {"x": 123.5, "y": -40},
                stable_entity_id("東京"): {"x": 600, "y": 240},
            },
            timeline={
                "mode": True,
                "timestamp": 42,
                "visible_layers": ["Su-ken", "Kan-ken"],
            },
            ignored_candidates=[[3, "主人公", "東京", "移動"]],
        )

    def test_shared_golden_fixture_is_readable_by_desktop_codec(self):
        fixture_path = Path(__file__).parent / "fixtures" / "axral-project-v1.json"
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        restored = parse_project(payload)
        self.assertEqual(restored["text"], payload["text"])
        self.assertEqual([event.to_dict() for event in restored["events"]], payload["events"])
        self.assertEqual(
            restored["events"][0].effects[0].target_id,
            stable_relation_id("主人公->東京#0"),
        )
        self.assertEqual(restored["graph_positions"], payload["graph_positions"])
        self.assertEqual(restored["timeline"], payload["timeline"])
        self.assertEqual(restored["ignored_candidates"], [(3, "主人公", "東京", "移動")])

    def test_shared_golden_fixture_survives_desktop_codec_round_trip(self):
        fixture_path = Path(__file__).parent / "fixtures" / "axral-project-v1.json"
        original = json.loads(fixture_path.read_text(encoding="utf-8"))
        restored = parse_project(original)
        rebuilt = build_project(
            text=restored["text"],
            events=restored["events"],
            graph_positions=restored["graph_positions"],
            timeline=restored["timeline"],
            ignored_candidates=restored["ignored_candidates"],
        )
        self.assertEqual(rebuilt, original)

    def test_json_round_trip_uses_application_codec_and_preserves_v1_fields(self):
        project = self.project_fixture()
        restored_payload = json.loads(json.dumps(project, ensure_ascii=False))
        restored = parse_project(restored_payload)
        self.assertEqual(restored["text"], project["text"])
        self.assertEqual(len(restored["events"]), 1)
        self.assertEqual(
            restored["events"][0].effects[0].target_id,
            stable_relation_id("主人公->東京#0"),
        )
        self.assertEqual(restored["events"][0].to_dict(), project["events"][0])
        self.assertEqual(restored["graph_positions"], project["graph_positions"])
        self.assertEqual(restored["timeline"], project["timeline"])
        self.assertEqual(restored["ignored_candidates"], [(3, "主人公", "東京", "移動")])

    def test_ignored_candidate_signature_contract(self):
        valid = [3, "主人公", "東京", "移動"]
        invalid = [
            [3, "主人公", "東京"],
            ["3", "主人公", "東京", "移動"],
            [3, "主人公", "東京", None],
            [True, "主人公", "東京", "移動"],
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


    def test_timeline_fields_normalize_like_web_codec(self):
        project = self.project_fixture()
        project["timeline"] = {
            "mode": "true",
            "timestamp": float("nan"),
            "visible_layers": ["Su-ken", 42, None],
        }
        restored = parse_project(project)
        self.assertEqual(
            restored["timeline"],
            {"mode": False, "timestamp": 0, "visible_layers": ["Su-ken"]},
        )

        project.pop("timeline")
        restored_without_timeline = parse_project(project)
        self.assertEqual(
            restored_without_timeline["timeline"],
            {"mode": False, "timestamp": 0, "visible_layers": LAYER_HIERARCHY},
        )

    def test_project_codec_rejects_invalid_required_fields_and_positions(self):
        project = self.project_fixture()
        invalid_payloads = [
            {**project, "schema_version": 2},
            {**project, "text": None},
            {**project, "events": [None]},
            {
                **project,
                "graph_positions": {
                    stable_entity_id("主人公"): {"x": float("nan"), "y": 0}
                },
            },
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    parse_project(payload)



    def test_event_and_effect_validation_matches_web_codec(self):
        base = self.project_fixture()
        original_event = base["events"][0]

        invalid_events = []
        for field, value in [
            ("id", None),
            ("timestamp", True),
            ("timestamp", float("nan")),
            ("type", 7),
            ("participants", ["主人公", 3]),
            ("participants", {}),
            ("effects", {}),
            ("is_snapshot_point", "true"),
            ("schema_version", True),
            ("schema_version", 1.5),
            ("metadata", []),
        ]:
            invalid_events.append({**original_event, field: value})

        invalid_effects = [
            {"kind": 4},
            {"kind": "relation_status", "target_id": 42},
            {"kind": "relation_status", "payload": []},
            None,
        ]
        for effect in invalid_effects:
            invalid_events.append({**original_event, "effects": [effect]})

        for event in invalid_events:
            payload = {**base, "events": [event]}
            with self.subTest(event=event):
                with self.assertRaises(ValueError):
                    parse_project(payload)

    def test_legacy_event_optional_fields_are_normalized(self):
        project = self.project_fixture()
        event = {
            "id": "evt_legacy",
            "timestamp": 3,
            "type": "移動",
        }
        project["events"] = [event]
        restored = parse_project(project)["events"][0]
        self.assertEqual(restored.participants, [])
        self.assertEqual(restored.effects, [])
        self.assertFalse(restored.is_snapshot_point)
        self.assertEqual(restored.schema_version, Event("x", 0, "x").schema_version)
        self.assertEqual(restored.metadata, {})

if __name__ == "__main__":
    unittest.main()
