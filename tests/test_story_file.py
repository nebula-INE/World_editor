import json
import tempfile
import unittest
from pathlib import Path

from core.story_file import load_story_file, save_story_file, STORY_FILE_SUFFIX


class StoryFileIOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(
            (Path(__file__).parent / "fixtures" / "axral-story-v1.json").read_text(
                encoding="utf-8"
            )
        )

    def test_save_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("sample" + STORY_FILE_SUFFIX)
            saved = save_story_file(path, self.fixture)
            self.assertEqual(saved, path)
            self.assertEqual(load_story_file(path), self.fixture)

    def test_invalid_story_does_not_replace_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("existing" + STORY_FILE_SUFFIX)
            original = '{"existing":"content"}\n'
            path.write_text(original, encoding="utf-8")
            invalid = dict(self.fixture, schema_version=999)

            with self.assertRaises(ValueError):
                save_story_file(path, invalid)

            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_malformed_json_is_reported_as_validation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ("broken" + STORY_FILE_SUFFIX)
            path.write_text('{"format":', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "物語ファイルを読み込めませんでした"):
                load_story_file(path)

    def test_wrong_extension_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "story.json"
            path.write_text(json.dumps(self.fixture), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "axral-story.json"):
                load_story_file(path)


if __name__ == "__main__":
    unittest.main()
