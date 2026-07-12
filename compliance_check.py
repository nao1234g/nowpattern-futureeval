#!/usr/bin/env python3
"""Fail-closed, secret-safe readiness audit for NowpatternFutureEval.

The audit verifies the repository's autonomous execution contract before a
GitHub Actions job is allowed to contact Metaculus.  It never prints secret
values, lengths, hashes, or prefixes.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
from pathlib import Path

REQUIRED_TOURNAMENT_ID = "33022"
REQUIRED_QUESTION_TYPES = (
    "BinaryQuestion",
    "MultipleChoiceQuestion",
    "NumericQuestion",
)
PROVIDER_KEYS = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


def _check(name: str, ok: bool, detail: str) -> dict[str, object]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _configured_general_llm_models(source: str) -> list[str]:
    """Return literal GeneralLlm(model=...) values from executable syntax."""
    tree = ast.parse(source)
    models: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "GeneralLlm":
            continue
        for keyword in node.keywords:
            if (
                keyword.arg == "model"
                and isinstance(keyword.value, ast.Constant)
                and isinstance(keyword.value.value, str)
            ):
                models.append(keyword.value.value)
    return models


def audit(root: Path, *, require_secrets: bool = False) -> dict[str, object]:
    main_path = root / "main.py"
    live_path = root / ".github" / "workflows" / "run_bot_on_tournament.yaml"
    test_path = root / ".github" / "workflows" / "test_bot.yaml"
    canary_path = root / ".github" / "workflows" / "live_canary.yaml"
    probe_path = root / "model_allowance_probe.py"
    missing = [
        str(p.relative_to(root))
        for p in (main_path, live_path, test_path, canary_path, probe_path)
        if not p.exists()
    ]
    if missing:
        checks = [_check("required_files", False, "missing=" + ",".join(missing))]
        return _report(checks, require_secrets=require_secrets)

    main = main_path.read_text(encoding="utf-8")
    live = live_path.read_text(encoding="utf-8")
    test = test_path.read_text(encoding="utf-8")
    canary = canary_path.read_text(encoding="utf-8")
    configured_models = _configured_general_llm_models(main)
    checks = [
        _check(
            "question_formats",
            all(name in main for name in REQUIRED_QUESTION_TYPES),
            "binary+multiple_choice+numeric required for Summer 2026",
        ),
        _check(
            "reasoned_reports",
            "ReasonedPrediction" in main and "extra_metadata_in_explanation=True" in main,
            "forecast report includes a published rationale/comment",
        ),
        _check(
            "metaculus_proxy_model_pin",
            configured_models.count("openrouter/openrouter/free") == 4
            and not any(model.startswith("metaculus/") for model in configured_models)
            and "metaculus/gpt-4o-search-preview" not in configured_models,
            "all four bot purposes use the single preflighted zero-cost router",
        ),
        _check(
            "model_allowance_preflight",
            "poetry run python model_allowance_probe.py" in test
            and test.index("model_allowance_probe.py") < test.index("--mode test_questions"),
            "one-call allowance probe runs before any test question is processed",
        ),
        _check(
            "dedupe",
            "skip_previously_forecasted_questions=True" in main,
            "scheduled tournament runs skip previously forecasted questions",
        ),
        _check(
            "pinned_tournament",
            "FUTUREEVAL_TOURNAMENT_ID" in main
            and REQUIRED_TOURNAMENT_ID in main
            and "args.tournament_id" in main
            and f'FUTUREEVAL_TOURNAMENT_ID: "{REQUIRED_TOURNAMENT_ID}"' in live,
            "Summer 2026 tournament id is pinned to 33022",
        ),
        _check(
            "test_first",
            "--mode test_questions" in test and "bot-testing-area" in main,
            "manual smoke test targets the official bot-testing-area",
        ),
        _check(
            "deterministic_binary_parser",
            "extract_last_probability(reasoning)" in main
            and "BinaryPrediction" not in main,
            "binary forecasts do not depend on a second LLM producing JSON",
        ),
        _check(
            "live_one_question_canary",
            "I_ACKNOWLEDGE_LIVE_SUBMISSION" in canary
            and "--mode live_canary --tournament-id 33022" in canary
            and "eligible_questions[:1]" in main,
            "manual LIVE canary is explicit and limited to one supported unforecasted question",
        ),
        _check(
            "live_default_off",
            "if: vars.FUTUREEVAL_LIVE_ENABLED == 'true'" in live,
            "scheduled LIVE execution requires an explicit repository variable",
        ),
        _check(
            "scheduler",
            'cron: "7,27,47 * * * *"' in live
            and "group: ${{ github.workflow }}" in live
            and "cancel-in-progress: false" in live,
            "20-minute schedule is serialized",
        ),
        _check(
            "secret_indirection",
            "secrets.METACULUS_TOKEN" in live and "secrets.METACULUS_TOKEN" in test,
            "workflows reference GitHub Secrets rather than a literal token",
        ),
        _check(
            "no_token_literal",
            re.search(r"(?i)(metaculus_token\s*[=:]\s*)[A-Za-z0-9]{40}", main + live + test) is None,
            "no 40-character token literal appears in audited files",
        ),
    ]

    token_ready = bool(os.getenv("METACULUS_TOKEN", "").strip())
    provider_ready = any(bool(os.getenv(name, "").strip()) for name in PROVIDER_KEYS)
    checks.append(
        _check(
            "metaculus_secret_ready",
            token_ready if require_secrets else True,
            "required at runtime; value is never inspected or emitted",
        )
    )
    checks.append(
        _check(
            "forecast_provider_ready",
            provider_ready if require_secrets else True,
            "external provider configured" if provider_ready else "provider secret required at runtime",
        )
    )
    return _report(checks, require_secrets=require_secrets)


def _report(checks: list[dict[str, object]], *, require_secrets: bool) -> dict[str, object]:
    ok = all(bool(row["ok"]) for row in checks)
    return {
        "schema_version": "nowpattern_futureeval_compliance.v1",
        "tournament_id": REQUIRED_TOURNAMENT_ID,
        "mode": "RUNTIME" if require_secrets else "CONFIG",
        "ok": ok,
        "verdict": "READY" if ok else "BLOCKED",
        "checks": checks,
        "secret_values_exposed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-secrets", action="store_true")
    args = parser.parse_args(argv)
    report = audit(Path(__file__).resolve().parent, require_secrets=args.require_secrets)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"FutureEval compliance: {report['verdict']} ({report['mode']})")
        for row in report["checks"]:
            print(f"  {'PASS' if row['ok'] else 'FAIL'} {row['name']}: {row['detail']}")
    return 2 if args.check and not report["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
