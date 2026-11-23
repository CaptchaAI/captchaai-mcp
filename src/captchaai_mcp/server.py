"""FastMCP server definition, lazy client holder, and token/browser-mode MCP tools."""

from __future__ import annotations

import asyncio
import dataclasses
import os
from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypeVar
from urllib.parse import urlparse

from captchaai import AsyncCaptchaAI, CaptchaAIError, RECAPTCHA_INIT_HOOK_JS
from captchaai.browser.adapter import parse_playwright_proxy, require_async_playwright
from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.lifespan import lifespan

from captchaai_mcp.catalog import build_call, describe_captchas, validate_proxy_pair
from captchaai_mcp.errors import to_tool_error

_T = TypeVar("_T")
_BROWSER_INSTALL_HINT = (
    'Browser mode requires optional dependencies. Install with: '
    'pip install "captchaai-mcp[browser]" && playwright install chromium'
)
_MAX_WAIT_TIMEOUT_MS = 60_000.0
_MAX_CLOSE_DELAY_S = 30.0

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


def _validate_browser_url(url: str) -> str:
    """Allow only http/https URLs with a host to prevent file:// or non-HTTP navigation."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ToolError("url must be a valid http:// or https:// URL.")
    return cleaned


def _validate_browser_timeouts(wait_timeout: float, close_delay: float = 0.0) -> None:
    if not (0.0 <= wait_timeout <= _MAX_WAIT_TIMEOUT_MS):
        raise ToolError(f"wait_timeout must be between 0 and {int(_MAX_WAIT_TIMEOUT_MS)} ms.")
    if not (0.0 <= close_delay <= _MAX_CLOSE_DELAY_S):
        raise ToolError(f"close_delay must be between 0 and {int(_MAX_CLOSE_DELAY_S)} seconds.")


def _require_playwright() -> Callable[[], Any]:
    try:
        return require_async_playwright()
    except ImportError as exc:
        raise ToolError(_BROWSER_INSTALL_HINT) from exc


def _map_browser_error(exc: Exception) -> ToolError:
    if isinstance(exc, ToolError):
        return exc
    if isinstance(exc, CaptchaAIError):
        return to_tool_error(exc)
    if isinstance(exc, ImportError):
        return ToolError(_BROWSER_INSTALL_HINT)
    if type(exc).__module__.startswith("playwright"):
        msg = str(exc)
        if "Executable doesn't exist" in msg:
            return ToolError(
                "Chromium browser binary is not installed. Run: playwright install chromium"
            )
        if "Timeout" in type(exc).__name__ or "Timeout" in msg:
            return ToolError(
                "Browser operation timed out while loading the page. "
                "Increase wait_timeout or check network/proxy connectivity."
            )
        first_line = msg.splitlines()[0].strip() if msg else type(exc).__name__
        return ToolError(f"BrowserError: {first_line}")
    raise exc


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
            "CaptchaAI token-mode and optional Playwright browser-mode captcha solving. "
            "Call get_supported_captchas() first to inspect token-mode parameters, or use "
            "get_captchas_params() / solve_url() when captchaai-mcp[browser] is installed."
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

    @mcp.tool(annotations={"readOnlyHint": True, "openWorldHint": True})
    async def get_captchas_params(
        ctx: Context,
        url: str,
        headless: bool = True,
        wait_timeout: float = 3000.0,
        proxy: str | None = None,
        proxytype: ProxyTypeLiteral | None = None,
    ) -> dict[str, Any]:
        """Open a URL in Playwright Chromium and extract CaptchaParams for every detected CAPTCHA.

        Requires optional browser dependencies: `pip install "captchaai-mcp[browser]"` and
        `playwright install chromium`.

        Args:
            url: Full http:// or https:// URL of the page to inspect.
            headless: Run Chromium in headless mode (default True).
            wait_timeout: Milliseconds to wait after domcontentloaded for CAPTCHA widgets to render (0-60000).
            proxy: Optional proxy string in "user:pass@host:port" format.
            proxytype: Proxy protocol when proxy is set ("HTTP" or "HTTPS").
        """
        clean_url = _validate_browser_url(url)
        _validate_browser_timeouts(wait_timeout)
        norm_proxy, norm_proxytype = validate_proxy_pair(proxy, proxytype)
        async_playwright = _require_playwright()
        pw_proxy = parse_playwright_proxy(norm_proxy, norm_proxytype)

        async def _extract(client: AsyncCaptchaAI) -> dict[str, Any]:
            async with async_playwright() as p:
                launch_kwargs: dict[str, Any] = {"headless": headless}
                if pw_proxy is not None:
                    launch_kwargs["proxy"] = pw_proxy
                browser = await p.chromium.launch(**launch_kwargs)
                try:
                    context = await browser.new_context()
                    # Register init hook before page load so JS-only reCAPTCHA callbacks are captured.
                    await context.add_init_script(RECAPTCHA_INIT_HOOK_JS)
                    page = await context.new_page()
                    await page.goto(clean_url, wait_until="domcontentloaded")
                    if wait_timeout > 0:
                        await page.wait_for_timeout(wait_timeout)
                    params_list = await client.get_captchas_params(page)
                    final_url = str(page.url)
                finally:
                    await browser.close()
            return {
                "url": final_url,
                "count": len(params_list),
                "captchas": [dataclasses.asdict(item) for item in params_list],
            }

        try:
            return await _call(ctx, _extract)
        except Exception as exc:
            raise _map_browser_error(exc) from exc

    @mcp.tool(annotations={"readOnlyHint": False, "openWorldHint": True})
    async def solve_url(
        ctx: Context,
        url: str,
        headless: bool = True,
        wait_timeout: float = 3000.0,
        close_delay: float = 0.0,
        autofill: bool = True,
        throw_on_error: bool = False,
        default_v3_action: str = "verify",
        proxy: str | None = None,
        proxytype: ProxyTypeLiteral | None = None,
    ) -> dict[str, Any]:
        """Open a URL in Playwright Chromium, detect all supported CAPTCHAs, solve them, and optionally inject tokens.

        Requires optional browser dependencies: `pip install "captchaai-mcp[browser]"` and
        `playwright install chromium`.

        Args:
            url: Full http:// or https:// URL of the page to solve.
            headless: Run Chromium in headless mode (default True).
            wait_timeout: Milliseconds to wait after domcontentloaded for CAPTCHA widgets to render (0-60000).
            close_delay: Seconds to keep the browser open after solving before closing (0-30).
            autofill: When True (default), inject solved tokens/cookies into the page; when False, solve without injecting.
            throw_on_error: When True, fail immediately on the first solve error; when False, return per-CAPTCHA error fields.
            default_v3_action: Fallback action name for reCAPTCHA v3 widgets when none is detected on the page.
            proxy: Optional proxy string in "user:pass@host:port" format.
            proxytype: Proxy protocol when proxy is set ("HTTP" or "HTTPS").
        """
        clean_url = _validate_browser_url(url)
        _validate_browser_timeouts(wait_timeout, close_delay)
        norm_proxy, norm_proxytype = validate_proxy_pair(proxy, proxytype)
        _require_playwright()

        try:
            results = await _call(
                ctx,
                lambda client: client.solve_url(
                    url=clean_url,
                    headless=headless,
                    wait_timeout=wait_timeout,
                    close_delay=close_delay,
                    autofill=autofill,
                    throw_on_error=throw_on_error,
                    default_v3_action=default_v3_action,
                    proxy=norm_proxy,
                    proxytype=norm_proxytype,
                ),
            )
        except Exception as exc:
            raise _map_browser_error(exc) from exc

        serialized = [
            {
                "params": dataclasses.asdict(item.params),
                "result": (
                    {
                        "task_id": item.result.task_id,
                        "solution": item.result.solution,
                        "user_agent": item.result.user_agent,
                    }
                    if item.result is not None
                    else None
                ),
                "injected": item.injected,
                "error": item.error,
            }
            for item in results
        ]
        return {
            "url": clean_url,
            "count": len(serialized),
            "solved_count": sum(1 for r in results if r.result is not None and r.error is None),
            "results": serialized,
        }

    return mcp
