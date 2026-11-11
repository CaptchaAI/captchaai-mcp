"""FastMCP server definition, lazy client holder, and token-mode MCP tools."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypeVar

from captchaai import AsyncCaptchaAI, CaptchaAIError
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.lifespan import lifespan

from captchaai_mcp.catalog import build_call, describe_captchas
from captchaai_mcp.errors import to_tool_error

_T = TypeVar("_T")

CaptchaTypeLiteral = Literal[
    "recaptcha_v2",
    "recaptcha_v3",
    "turnstile",
    "cloudflare_challenge",
    "geetest",
    "captchafox",
    "friendly_captcha",
    "lemin",
]
ProxyTypeLiteral = Literal["HTTP", "HTTPS"]


class ClientHolder:
    """Lazily builds and caches one AsyncCaptchaAI instance for the server lifetime."""

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key
        self._client: AsyncCaptchaAI | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> AsyncCaptchaAI:
        """Return the cached AsyncCaptchaAI client, creating it on first use."""
        async with self._lock:
            if self._client is None:
                if not self._api_key:
                    raise ToolError("CAPTCHAAI_API_KEY is not set (or pass --api-key).")
                try:
                    self._client = await AsyncCaptchaAI.create(api_key=self._api_key)
                except CaptchaAIError as exc:
                    raise to_tool_error(exc) from exc
            return self._client

    async def aclose(self) -> None:
        """Close the cached client if it was created."""
        if self._client is not None:
            client = self._client
            self._client = None
            await client.aclose()


async def _call(ctx: Context, fn: Callable[[AsyncCaptchaAI], Awaitable[_T]]) -> _T:
    """Retrieve the shared SDK client, run `fn`, and map SDK errors to ToolError."""
    holder: ClientHolder = ctx.lifespan_context["holder"]
    client = await holder.get()
    try:
        return await fn(client)
    except CaptchaAIError as exc:
        raise to_tool_error(exc) from exc


def create_server(api_key: str | None = None, name: str = "captchaai") -> FastMCP:
    """Create and configure the CaptchaAI FastMCP server."""
    import captchaai_mcp

    resolved_key = api_key if api_key is not None else os.environ.get("CAPTCHAAI_API_KEY")
    holder = ClientHolder(resolved_key)

    @lifespan
    async def app_lifespan(server: FastMCP):
        try:
            yield {"holder": holder}
        finally:
            await holder.aclose()

    mcp = FastMCP(
        name,
        version=captchaai_mcp.__version__,
        lifespan=app_lifespan,
        mask_error_details=True,
        instructions=(
            "CaptchaAI token-mode captcha solving. "
            "Call get_supported_captchas() first to inspect required and optional parameters per type."
        ),
    )

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    async def get_threads(ctx: Context) -> dict[str, int]:
        """Get CaptchaAI thread usage: total threads, active working_threads, and free_threads."""
        info = await _call(ctx, lambda client: client.threads_info())
        return {
            "threads": info["threads"],
            "working_threads": info["working_threads"],
            "free_threads": info["threads"] - info["working_threads"],
        }

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    async def get_balance(ctx: Context) -> dict[str, str]:
        """Get the CaptchaAI account balance as returned by the API."""
        balance = await _call(ctx, lambda client: client.get_balance())
        return {"balance": balance}

    @mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True, "openWorldHint": False})
    def get_supported_captchas() -> dict[str, dict[str, Any]]:
        """List all supported token-mode CAPTCHA types with required/optional arguments and capabilities.

        Works without an API key.
        """
        return {"captchas": describe_captchas()}

    @mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": True})
    async def solve_captcha(
        ctx: Context,
        captcha_type: CaptchaTypeLiteral,
        website_url: str,
        website_key: str | None = None,
        action: str | None = None,
        min_score: float | None = None,
        invisible: bool = False,
        enterprise: bool = False,
        gt: str | None = None,
        challenge: str | None = None,
        captcha_id: str | None = None,
        div_id: str | None = None,
        api_server: str | None = None,
        version: str | None = None,
        cookies: str | None = None,
        user_agent: str | None = None,
        proxy: str | None = None,
        proxytype: ProxyTypeLiteral | None = None,
    ) -> dict[str, Any]:
        """Solve a CAPTCHA in token mode (no browser) and return the solved token or payload.

        Blocks until solved (typically 10-80s). Call get_supported_captchas() first to check
        which arguments are required for the chosen captcha_type. When `user_agent` is returned
        (Enterprise, Cloudflare Challenge, CaptchaFox), reuse it when submitting the token.

        Args:
            captcha_type: CAPTCHA challenge type (e.g. "recaptcha_v2", "recaptcha_v3", "turnstile").
            website_url: Full URL of the page containing the CAPTCHA.
            website_key: Site key (data-sitekey) for reCAPTCHA, Turnstile, CaptchaFox, or Friendly Captcha.
            action: Action name (required for recaptcha_v3; optional `sa=` for Enterprise v2).
            min_score: Minimum score threshold (0.0-1.0) for recaptcha_v3.
            invisible: Enable invisible mode (recaptcha_v2 only).
            enterprise: Enable Enterprise mode (recaptcha_v2 or recaptcha_v3).
            gt: GeeTest public `gt` parameter (required for geetest).
            challenge: GeeTest `challenge` parameter (required for geetest).
            captcha_id: Lemin captcha identifier (required for lemin).
            div_id: Lemin target container element ID (required for lemin).
            api_server: Optional Lemin API server URL.
            version: Optional Friendly Captcha version string.
            cookies: Optional cookies forwarded to the solver ("KEY1:Val1;KEY2:Val2;").
            user_agent: Optional User-Agent string forwarded to the solver.
            proxy: Proxy string in "user:pass@host:port" format (required for cloudflare_challenge and captchafox).
            proxytype: Proxy protocol when proxy is set ("HTTP" or "HTTPS").
        """
        args: dict[str, Any] = {
            "website_url": website_url,
            "website_key": website_key,
            "action": action,
            "min_score": min_score,
            "invisible": invisible,
            "enterprise": enterprise,
            "gt": gt,
            "challenge": challenge,
            "captcha_id": captcha_id,
            "div_id": div_id,
            "api_server": api_server,
            "version": version,
            "cookies": cookies,
            "user_agent": user_agent,
            "proxy": proxy,
            "proxytype": proxytype,
        }
        method_name, sdk_kwargs = build_call(captcha_type, args)
        result = await _call(ctx, lambda client: getattr(client, method_name)(**sdk_kwargs))
        return {
            "captcha_type": captcha_type,
            "task_id": result.task_id,
            "solution": result.solution,
            "user_agent": result.user_agent,
        }

    return mcp
