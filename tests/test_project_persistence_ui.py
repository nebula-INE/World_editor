"""Qt UI integration tests for the .axral.json v1 open/save path."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from main import MainWindow


class DesktopProjectUiRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(__file__).parent
        self.fixture_path = self.root / "fixtures" / "axral-project-v1.json"
        self.fixture = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self.window = MainWindow()
        self.addCleanup(self.window.close)

    def _open(self, path):
        with patch("main.QFileDialog.getOpenFileName", return_value=(str(path), "")), patch(
            "main.QMessageBox.critical"
        ) as critical, patch("main.QMessageBox.question", return_value=1):
            self.window._open_project()
        return critical

    def _save(self, path):
        with patch("main.QFileDialog.getSaveFileName", return_value=(str(path), "")), patch(
            "main.QMessageBox.information"
        ):
            self.window._save_project()
        return json.loads(path.read_text(encoding="utf-8"))

    def test_desktop_ui_open_save_preserves_shared_v1_fixture(self):
        self._open(self.fixture_path)
        self.window._debounce.stop()
        self.window._reparse()

        saved_path = Path(self.temp_dir.name) / "desktop-roundtrip.axral.json"
        saved = self._save(saved_path)
        self.assertEqual(saved, self.fixture)

    def test_malformed_project_does_not_replace_open_document_or_state(self):
        self._open(self.fixture_path)
        self.window._debounce.stop()
        self.window._reparse()

        malformed_path = Path(self.temp_dir.name) / "malformed.axral.json"
        malformed_path.write_text('{"format": "axral-world-project", "schema_version": 99}', encoding="utf-8")
        with patch("main.QFileDialog.getOpenFileName", return_value=(str(malformed_path), "")), patch(
            "main.QMessageBox.critical"
        ) as critical:
            self.window._open_project()
        critical.assert_called_once()

        saved_path = Path(self.temp_dir.name) / "after-malformed.axral.json"
        saved = self._save(saved_path)
        self.assertEqual(saved, self.fixture)


if __name__ == "__main__":
    unittest.main()
