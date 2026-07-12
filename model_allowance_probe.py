#!/usr/bin/env python3
"""Probe one Metaculus-proxy model without exposing secrets or model output."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Awaitable, Callable

DEFAULT_MODEL = "metaculus/gpt-4o-mini"


def classify_error(exc: BaseException) -> str:
    """Return a stable error category without returning provider text."""
    text = str(exc).lower()
    if "allowance" in text:
        return "NO_MODEL_ALLOWANCE"
    if "401" in text or "unauthorized" in text or "authentication" in text:
        return "AUTHENTICATION_FAILED"
    if "429" in text or "rate limit" in text:
        return "RATE_LIMITED"
    if "timeout" in text or isinstance(exc, TimeoutError):
        return "TIMEOUT"
    return "PROVIDER_ERROR"


async def _invoke_model(model: str) -> None:
    from forecasting_tools import GeneralLlm

    llm = GeneralLlm(
        model=model,
        temperature=0,
        timeout=30,
        allowed_tries=1,
    )
    await llm.invoke("Reply with the single word OK.")


async def probe(
    model: str = DEFAULT_MODEL,
    *,
    invoke: Callable[[str], Awaitable[None]] = _invoke_model,
) -> dict[str, object]:
    """Return only operational metadata; never return a token or LLM response."""
    if not os.getenv("METACULUS_TOKEN", "").strip():
        return {
            "schema_version": "metaculus_model_allowance_probe.v1",
            "model": model,
            "ok": False,
            "verdict": "BLOCKED",
            "error_category": "TOKEN_MISSING",
            "secret_values_exposed": False,
        }

    try:
        await invoke(model)
    except Exception as exc:  # provider exceptions vary by forecasting-tools version
        return {
            "schema_version": "metaculus_model_allowance_probe.v1",
            "model": model,
            "ok": False,
            "verdict": "BLOCKED",
            "error_category": classify_error(exc),
            "secret_values_exposed": False,
        }

    return {
        "schema_version": "metaculus_model_allowance_probe.v1",
        "model": model,
        "ok": True,
        "verdict": "ALLOWED",
        "error_category": None,
        "secret_values_exposed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=[DEFAULT_MODEL], default=DEFAULT_MODEL)
    args = parser.parse_args(argv)
    report = asyncio.run(probe(args.model))
    print(json.dumps(report, sort_keys=True))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
