import json
import tempfile
import unittest
from pathlib import Path

from core.story_file import load_story_file, save_story_file


class StoryFileIOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "axral-story-v1.json").read_text(encoding="utf-8")
        )

    def test_save_and_reload_standalone_story_preserves_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.axral-story.json"
            returned = save_story_file(path, self.fixture)
            self.assertEqual(returned, path)
            self.assertEqual(load_story_file(path), self.fixture)
            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))

    def test_invalid_story_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.axral-story.json"
            original = '{"keep":"existing content"}'
            path.write_text(original, encoding="utf-8")
            invalid = dict(self.fixture, schema_version=999)
            with self.assertRaisesRegex(ValueError, "未対応"):
                save_story_file(path, invalid)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_rejects_world_project_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "existing.axral.json"
            path.write_text('{"must":"remain untouched"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "物語ファイル"):
                save_story_file(path, self.fixture)
            self.assertEqual(path.read_text(encoding="utf-8"), '{"must":"remain untouched"}')
            with self.assertRaisesRegex(ValueError, "物語ファイル"):
                load_story_file(path)

    def test_invalid_json_is_reported_without_silent_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "broken.axral-story.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "読み込めません"):
                load_story_file(path)


if __name__ == "__main__":
    unittest.main()
