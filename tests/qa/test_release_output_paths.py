"""Fast, pure filesystem-policy tests. Never opens a port, app or real library."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[2] / "scripts/qa/release-gate.py"
spec = importlib.util.spec_from_file_location("release_gate", MODULE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

class OutputRootPolicy(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="n3lx-release-policy-")
        self.addCleanup(self.scratch.cleanup)
        base = Path(self.scratch.name)
        self.outputs = base / "N3LX_Stem-Releases"
        self.qa = self.outputs / "release-gate-qa"
        self.runtime = base / "N3LX_Stem"
        self.qa.mkdir(parents=True)
        self.runtime.mkdir()

    def test_sibling_reports_under_same_release_root_is_allowed(self):
        self.assertEqual(
            gate.validate_output_root(self.outputs,self.qa,self.runtime),
            self.outputs.resolve())

    def test_output_inside_worktree_is_blocked(self):
        output = self.qa / "reports"
        output.mkdir()
        with self.assertRaises(ValueError):
            gate.validate_output_root(output,self.qa,self.runtime)

    def test_output_inside_runtime_is_blocked(self):
        output = self.runtime / "reports"
        output.mkdir()
        with self.assertRaises(ValueError):
            gate.validate_output_root(output,self.qa,self.runtime)

    def test_output_which_contains_runtime_is_blocked(self):
        with self.assertRaises(ValueError):
            gate.validate_output_root(self.outputs.parent,self.qa,self.runtime)

    def test_missing_root_is_blocked(self):
        with self.assertRaises(ValueError):
            gate.validate_output_root(self.outputs/"missing",self.qa,self.runtime)

    def test_direct_symlink_alias_is_blocked(self):
        alias = self.outputs.parent / "release-alias"
        try:
            alias.symlink_to(self.outputs,target_is_directory=True)
        except (OSError,NotImplementedError):
            self.skipTest("OS does not permit symlinks for current test user")
        with self.assertRaises(ValueError):
            gate.validate_output_root(alias,self.qa,self.runtime)

if __name__ == "__main__":
    unittest.main(verbosity=2)
