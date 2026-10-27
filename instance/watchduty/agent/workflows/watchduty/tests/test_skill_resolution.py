"""Offline coverage for Jenkins skill discovery in a synced OpenCode profile."""

import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


PREFLIGHT = Path(__file__).resolve().parents[1] / "preflight" / "01-jenkins-status.py"


class SkillResolutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.profile = self.root / "config" / "instance" / "watchduty" / "agent"
        preflight = self.profile / "workflows" / "watchduty" / "preflight" / PREFLIGHT.name
        preflight.parent.mkdir(parents=True)
        shutil.copyfile(PREFLIGHT, preflight)
        spec = importlib.util.spec_from_file_location("jenkins_preflight", preflight)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def script(self, directory):
        path = directory / "triage-jenkins" / "triage_jenkins.py"
        path.parent.mkdir(parents=True)
        path.write_text("# fixture\n")
        return path

    def test_native_profile_skill_is_found_without_installed_claude_copy(self):
        native = self.script(self.profile / ".opencode" / "skills")
        with patch.dict(os.environ, {"PYTHONPATH": ""}):
            self.assertEqual(self.module._find_skill_script(), native)

    def test_native_profile_wins_over_stale_installed_copy(self):
        native = self.script(self.profile / ".opencode" / "skills")
        installed = self.root / "runner" / ".claude" / "skills"
        self.script(installed)
        with patch.dict(os.environ, {"PYTHONPATH": str(installed)}):
            self.assertEqual(self.module._find_skill_script(), native)

    def test_missing_skill_is_reported_without_using_unrelated_paths(self):
        with patch.dict(os.environ, {"PYTHONPATH": str(self.root / "missing")}):
            self.assertIsNone(self.module._find_skill_script())


if __name__ == "__main__":
    unittest.main()
