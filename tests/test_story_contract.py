import json
import unittest
from pathlib import Path
from core.story import parse_story, serialize_story, validate_story_references

class StoryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=json.loads((Path(__file__).parent/"fixtures"/"axral-story-v1.json").read_text(encoding="utf-8"))
    def test_round_trip_preserves_japanese_ids_order_and_newlines(self):
        self.assertEqual(json.loads(serialize_story(parse_story(self.fixture))),self.fixture)
        self.assertIn("\n",self.fixture["chapters"][0]["scenes"][0]["blocks"][2]["text"])
    def test_unknown_version_rejected(self):
        with self.assertRaisesRegex(ValueError,"未対応"): parse_story(dict(self.fixture,schema_version=99))
    def test_boolean_schema_version_rejected(self):
        with self.assertRaisesRegex(ValueError,"未対応"): parse_story(dict(self.fixture,schema_version=True))
    def test_non_string_kind_rejected_as_validation_error(self):
        for invalid_kind in ([], {}, 1, None):
            with self.subTest(kind=invalid_kind):
                with self.assertRaisesRegex(ValueError, "kindは対応"):
                    parse_story(dict(self.fixture, kind=invalid_kind))
    def test_non_string_block_type_rejected_as_validation_error(self):
        for invalid_type in ([], {}, 1, None):
            with self.subTest(block_type=invalid_type):
                bad=json.loads(json.dumps(self.fixture))
                bad["chapters"][0]["scenes"][0]["blocks"][0]["type"]=invalid_type
                with self.assertRaisesRegex(ValueError, "ブロック種別"):
                    parse_story(bad)
    def test_duplicate_ids_and_bad_order_rejected(self):
        bad=json.loads(json.dumps(self.fixture)); bad["chapters"][0]["scenes"][0]["blocks"][1]["id"]="block_001"
        with self.assertRaisesRegex(ValueError,"重複"): parse_story(bad)
        bad=json.loads(json.dumps(self.fixture)); bad["chapters"][0]["scenes"][0]["blocks"][0]["order"]=4
        with self.assertRaisesRegex(ValueError,"配列位置"): parse_story(bad)
    def test_empty_speaker_id_is_ignored_by_reference_validation(self):
        payload=json.loads(json.dumps(self.fixture))
        payload["chapters"][0]["scenes"][0]["blocks"][3]["character_id"]=""
        known={"ent_8f07c23f5f99"}
        self.assertEqual(
            validate_story_references(payload,known),
            validate_story_references(self.fixture,known),
        )
    def test_broken_refs_reported_without_mutating_document(self):
        before=json.loads(json.dumps(self.fixture))
        findings=validate_story_references(self.fixture,{"ent_8f07c23f5f99"})
        self.assertEqual([x["entity_id"] for x in findings],["ent_681ee300008e"])
        self.assertEqual(self.fixture,before)

if __name__=="__main__": unittest.main()
