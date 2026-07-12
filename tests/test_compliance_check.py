from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import compliance_check


ROOT = Path(__file__).resolve().parents[1]


class ComplianceCheckTests(unittest.TestCase):
    def test_repository_config_is_ready(self) -> None:
        report = compliance_check.audit(ROOT)
        self.assertTrue(report["ok"], report)
        self.assertFalse(report["secret_values_exposed"])

    def test_runtime_fails_closed_without_token(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"METACULUS_TOKEN": "", "OPENROUTER_API_KEY": ""},
            clear=False,
        ):
            report = compliance_check.audit(ROOT, require_secrets=True)
        self.assertFalse(report["ok"])
        self.assertEqual(report["verdict"], "BLOCKED")

    def test_runtime_accepts_token_without_exposing_it(self) -> None:
        secret = "x" * 40
        with mock.patch.dict(
            os.environ,
            {"METACULUS_TOKEN": secret, "OPENROUTER_API_KEY": "provider-key"},
            clear=False,
        ):
            report = compliance_check.audit(ROOT, require_secrets=True)
        self.assertTrue(report["ok"], report)
        self.assertNotIn(secret, str(report))

    def test_missing_live_enable_guard_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            shutil.copytree(ROOT / ".github", target / ".github")
            shutil.copy2(ROOT / "main.py", target / "main.py")
            shutil.copy2(ROOT / "model_allowance_probe.py", target / "model_allowance_probe.py")
            live = target / ".github" / "workflows" / "run_bot_on_tournament.yaml"
            live.write_text(
                live.read_text(encoding="utf-8").replace(
                    "if: vars.FUTUREEVAL_LIVE_ENABLED == 'true'", ""
                ),
                encoding="utf-8",
            )
            report = compliance_check.audit(target)
        self.assertFalse(report["ok"])
        failed = {row["name"] for row in report["checks"] if not row["ok"]}
        self.assertIn("live_default_off", failed)

    def test_unallowed_search_model_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            shutil.copytree(ROOT / ".github", target / ".github")
            shutil.copy2(ROOT / "model_allowance_probe.py", target / "model_allowance_probe.py")
            main = (ROOT / "main.py").read_text(encoding="utf-8")
            (target / "main.py").write_text(
                main.replace(
                    'model="openrouter/openrouter/free", temperature=0.1',
                    'model="metaculus/gpt-4o-search-preview", temperature=0.1',
                ),
                encoding="utf-8",
            )
            report = compliance_check.audit(target)
        self.assertFalse(report["ok"])
        failed = {row["name"] for row in report["checks"] if not row["ok"]}
        self.assertIn("metaculus_proxy_model_pin", failed)


if __name__ == "__main__":
    unittest.main()
