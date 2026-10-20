import json
import unittest
from pathlib import Path
from core.story_editing import (
    add_chapter, rename_chapter, reorder_chapter, delete_chapter,
    add_scene, rename_scene, reorder_scene, delete_scene,
    add_block, update_block, reorder_block, delete_block,
)

class StoryEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=json.loads((Path(__file__).parent/"fixtures"/"axral-story-v1.json").read_text(encoding="utf-8"))
    def test_chapter_operations_are_immutable_and_normalize_order(self):
        added=add_chapter(self.fixture,"chapter_002","第二章")
        self.assertEqual(len(self.fixture["chapters"]),1)
        self.assertEqual(rename_chapter(added,"chapter_002","第二章・改")["chapters"][1]["title"],"第二章・改")
        moved=reorder_chapter(added,"chapter_002",0)
        self.assertEqual([(x["id"],x["order"]) for x in moved["chapters"]],[("chapter_002",0),("chapter_001",1)])
        self.assertEqual(len(delete_chapter(added,"chapter_002")["chapters"]),1)
    def test_scene_and_block_operations(self):
        story=add_chapter(self.fixture,"chapter_002","第二章")
        story=add_scene(story,"chapter_002","scene_002","雨上がり")
        story=rename_scene(story,"scene_002","雨上がり・改")
        story=add_block(story,"scene_002",{"id":"block_005","type":"prose","text":"空が明るくなる。"})
        story=update_block(story,"block_005",{"text":"空が少しずつ明るくなる。"})
        self.assertEqual(story["chapters"][1]["scenes"][0]["blocks"][0]["text"],"空が少しずつ明るくなる。")
        self.assertEqual(delete_block(story,"block_005")["chapters"][1]["scenes"][0]["blocks"],[])
        self.assertEqual(delete_scene(story,"scene_002")["chapters"][1]["scenes"],[])
    def test_reordering_and_invalid_edits_fail_closed(self):
        story=add_chapter(self.fixture,"chapter_002","第二章")
        story=add_scene(story,"chapter_002","scene_002","追加")
        story=add_scene(story,"chapter_002","scene_003","追加2")
        story=reorder_scene(story,"scene_003",0)
        self.assertEqual([s["id"] for s in story["chapters"][1]["scenes"]],["scene_003","scene_002"])
        story=add_block(story,"scene_003",{"id":"block_005","type":"prose","text":"A"})
        story=add_block(story,"scene_003",{"id":"block_006","type":"dialogue","text":"B"})
        story=reorder_block(story,"block_006",0)
        self.assertEqual([b["id"] for b in story["chapters"][1]["scenes"][0]["blocks"]],["block_006","block_005"])
        with self.assertRaisesRegex(ValueError,"範囲外"): reorder_chapter(story,"chapter_001",8)
        with self.assertRaisesRegex(ValueError,"重複"): add_chapter(self.fixture,"chapter_001","重複ID")

if __name__=="__main__": unittest.main()
