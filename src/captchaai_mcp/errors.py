"""Map CaptchaAI SDK exceptions to structured FastMCP ToolError instances."""

from __future__ import annotations

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

_HINTS: dict[type[CaptchaAIError], str] = {
    InvalidKeyError: "Check CAPTCHAAI_API_KEY or --api-key.",
    ValidationError: "Fix the arguments; see get_supported_captchas().",
    ThreadLimitError: "All threads busy; check get_threads() and retry later.",
    NoThreadsError: "Account has no threads; check your plan at captchaai.com.",
    UnsolvableError: "Workers could not solve it; verify website_key/website_url and retry.",
    ProxyError: "Proxy failed; check proxy format 'user:pass@host:port' and proxytype.",
    TimeoutError: "Solve took too long; retry.",
    NetworkError: "Could not reach CaptchaAI; retry.",
    APIError: "Unexpected API response.",
}


def to_tool_error(exc: CaptchaAIError) -> ToolError:
    """Convert a CaptchaAI SDK exception into an agent-readable ToolError."""
    hint = next((text for cls, text in _HINTS.items() if isinstance(exc, cls)), "")
    message = f"{type(exc).__name__}: {exc}".rstrip(".")
    if hint:
        message = f"{message}. {hint}"
    return ToolError(message)
