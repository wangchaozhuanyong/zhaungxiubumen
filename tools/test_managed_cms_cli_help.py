"""Help must not touch domain evidence, credentials, or external actions."""

import builtins
import contextlib
import io
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

from tools.managed_cms_cli import build_parser


class IssuerHelpTests(unittest.TestCase):
    def test_module_help_is_also_metadata_free(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-B", "-m", "tools.managed_cms_permit_issuer", "--help"],
                                cwd=root, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--policy-decision-id", result.stdout)

    def test_help_before_workflow_or_catalog_import_even_with_dispatch_flag(self):
        real_import = builtins.__import__
        seen = []

        def guarded_import(name, *args, **kwargs):
            if "workflow_control" in name or name.startswith(("tools.native_", "tools.professional_", "paid_three_page")):
                raise AssertionError("Help attempted a domain/evidence import: " + name)
            seen.append(name)
            return real_import(name, *args, **kwargs)

        script = Path(__file__).with_name("managed_cms_permit_issuer.py")
        for args in [["--help"], ["-h"], ["--issue-and-dispatch", "--help"]]:
            with self.subTest(args=args), patch.object(sys, "argv", [str(script), *args]), \
                    patch.object(sys, "path", [str(script.parent), *sys.path]), \
                    patch("builtins.__import__", side_effect=guarded_import), \
                    contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as done:
                    runpy.run_path(str(script), run_name="__main__")
                self.assertEqual(done.exception.code, 0)
                self.assertIn("--policy-decision-id", output.getvalue())
                self.assertIn("--parent-permit-id", output.getvalue())
        self.assertNotIn("workflow_control", seen)

    def test_execution_parser_still_requires_all_proofs_and_exact_target(self):
        parser = build_parser("test", target_choices=["exact-original-target"])
        valid = ["--target", "exact-original-target", "--operation", "publish",
                 "--dry-run-run-id", "123", "--operations-decision", "original.json",
                 "--policy-decision-id", "original-policy", "--github-actor-id", "456"]
        self.assertEqual(parser.parse_args(valid).target, "exact-original-target")
        for invalid in [valid[2:], ["--target", "other-target", *valid[2:]], valid[:-2]]:
            with self.subTest(invalid=invalid), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as denied:
                    parser.parse_args(invalid)
                self.assertNotEqual(denied.exception.code, 0)


if __name__ == "__main__":
    unittest.main()
