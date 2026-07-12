from __future__ import annotations

import os
import unittest
from unittest import mock

import model_allowance_probe


class ModelAllowanceProbeTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_token_fails_closed(self) -> None:
        with mock.patch.dict(os.environ, {"METACULUS_TOKEN": ""}, clear=False):
            report = await model_allowance_probe.probe()
        self.assertFalse(report["ok"])
        self.assertEqual(report["error_category"], "TOKEN_MISSING")

    async def test_success_does_not_return_secret_or_model_output(self) -> None:
        secret = "s" * 40

        async def succeed(model: str) -> None:
            self.assertEqual(model, model_allowance_probe.DEFAULT_MODEL)

        with mock.patch.dict(os.environ, {"METACULUS_TOKEN": secret}, clear=False):
            report = await model_allowance_probe.probe(invoke=succeed)
        self.assertTrue(report["ok"])
        self.assertNotIn(secret, str(report))
        self.assertNotIn("OK", str(report))

    async def test_allowance_failure_is_sanitized(self) -> None:
        secret = "s" * 40

        async def fail(model: str) -> None:
            raise RuntimeError(f"allowance denied secret={secret}")

        with mock.patch.dict(os.environ, {"METACULUS_TOKEN": secret}, clear=False):
            report = await model_allowance_probe.probe(invoke=fail)
        self.assertFalse(report["ok"])
        self.assertEqual(report["error_category"], "NO_MODEL_ALLOWANCE")
        self.assertNotIn(secret, str(report))


if __name__ == "__main__":
    unittest.main()
