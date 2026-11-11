"""Tests for SDK exception -> FastMCP ToolError mapping."""

from __future__ import annotations

import pytest
from captchaai import (
    APIError,
    CaptchaAIError,
    InvalidKeyError,
    NetworkError,
    NoThreadsError,
    ProxyError,
    ThreadLimitError,
    TimeoutError,
    UnsolvableError,
    ValidationError,
)
from fastmcp.exceptions import ToolError

from captchaai_mcp.errors import to_tool_error


@pytest.mark.parametrize(
    ("exc", "expected_hint"),
    [
        (InvalidKeyError("bad key"), "CAPTCHAAI_API_KEY"),
        (ValidationError("missing sitekey"), "get_supported_captchas"),
        (ThreadLimitError("busy"), "get_threads"),
        (NoThreadsError("0 threads"), "captchaai.com"),
        (UnsolvableError("unsolvable"), "verify website_key/website_url"),
        (ProxyError("bad proxy"), "user:pass@host:port"),
        (TimeoutError("timed out"), "retry"),
        (NetworkError("connection refused"), "Could not reach CaptchaAI"),
        (APIError("oops"), "Unexpected API response"),
        (CaptchaAIError("generic"), "CaptchaAIError: generic"),
    ],
)
def test_to_tool_error_includes_exception_name_and_hint(
    exc: CaptchaAIError, expected_hint: str
) -> None:
    err = to_tool_error(exc)
    assert isinstance(err, ToolError)
    text = str(err)
    assert type(exc).__name__ in text
    assert str(exc) in text
    assert expected_hint in text
