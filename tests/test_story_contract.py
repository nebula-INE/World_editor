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
        self.assertIn("\\n",self.fixture["chapters"][0]["scenes"][0]["blocks"][2]["text"])
    def test_unknown_version_rejected(self):
        with self.assertRaisesRegex(ValueError,"未対応"): parse_story(dict(self.fixture,schema_version=99))
    def test_duplicate_ids_and_bad_order_rejected(self):
        bad=json.loads(json.dumps(self.fixture)); bad["chapters"][0]["scenes"][0]["blocks"][1]["id"]="block_001"
        with self.assertRaisesRegex(ValueError,"重複"): parse_story(bad)
        bad=json.loads(json.dumps(self.fixture)); bad["chapters"][0]["scenes"][0]["blocks"][0]["order"]=4
        with self.assertRaisesRegex(ValueError,"配列位置"): parse_story(bad)
    def test_broken_refs_reported_without_mutating_document(self):
        before=json.loads(json.dumps(self.fixture))
        findings=validate_story_references(self.fixture,{"ent_8f07c23f5f99"})
        self.assertEqual([x["entity_id"] for x in findings],["ent_681ee300008e"])
        self.assertEqual(self.fixture,before)

if __name__=="__main__": unittest.main()
