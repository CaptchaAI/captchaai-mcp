"""Unit tests for optional Playwright browser-mode MCP tools."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from captchaai import (
    CaptchaParams,
    PageSolveResult,
    RECAPTCHA_INIT_HOOK_JS,
    SolveResult,
    UnsolvableError,
)
from fastmcp import Client
from fastmcp.exceptions import ToolError

from captchaai_mcp.server import create_server


class FakePage:
    def __init__(self, events: list[tuple]) -> None:
        self.events = events
        self.url = "about:blank"

    async def goto(self, url: str, *, wait_until: str) -> None:
        self.events.append(("goto", url, wait_until))
        self.url = url

    async def wait_for_timeout(self, ms: float) -> None:
        self.events.append(("wait_for_timeout", ms))


class FakeContext:
    def __init__(self, events: list[tuple]) -> None:
        self.events = events

    async def add_init_script(self, script: str) -> None:
        self.events.append(("add_init_script", script))

    async def new_page(self) -> FakePage:
        self.events.append(("new_page",))
        return FakePage(self.events)


class FakeBrowser:
    def __init__(self, events: list[tuple]) -> None:
        self.events = events
        self.closed = False

    async def new_context(self) -> FakeContext:
        self.events.append(("new_context",))
        return FakeContext(self.events)

    async def close(self) -> None:
        self.closed = True
        self.events.append(("close",))


def _make_fake_playwright(events: list[tuple], *, browser_holder: dict | None = None):
    class FakeChromium:
        async def launch(self, **kwargs) -> FakeBrowser:
            events.append(("launch", kwargs))
            browser = FakeBrowser(events)
            if browser_holder is not None:
                browser_holder["browser"] = browser
            return browser

    class FakePlaywrightCM:
        chromium = FakeChromium()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    return lambda: FakePlaywrightCM()


class TestGetCaptchasParams:
    async def test_extracts_params_with_init_hook_proxy_and_cleanup(
        self, monkeypatch: pytest.MonkeyPatch, patched_sdk_create, fake_client
    ) -> None:
        events: list[tuple] = []
        holder: dict = {}
        monkeypatch.setattr(
            "captchaai_mcp.server.require_async_playwright",
            lambda: _make_fake_playwright(events, browser_holder=holder),
        )

        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            result = await client.call_tool(
                "get_captchas_params",
                {
                    "url": "https://example.com/login",
                    "headless": False,
                    "wait_timeout": 1500.0,
                    "proxy": "user:pass@1.2.3.4:8080",
                    "proxytype": "HTTP",
                },
            )

        assert result.data == {
            "url": "https://example.com/login",
            "count": 1,
            "captchas": [
                {
                    "captcha_type": "recaptcha_v2",
                    "pageurl": "https://example.com/login",
                    "sitekey": "site-v2-key",
                    "action": None,
                    "invisible": False,
                    "enterprise": False,
                    "s": None,
                    "cdata": None,
                    "container_id": "rc-box",
                    "callback": "onCaptcha",
                    "binded_button_id": None,
                    "user_agent": "Mozilla/5.0 Fake",
                }
            ],
        }
        assert events[0] == (
            "launch",
            {
                "headless": False,
                "proxy": {
                    "server": "http://1.2.3.4:8080",
                    "username": "user",
                    "password": "pass",
                },
            },
        )
        assert ("add_init_script", RECAPTCHA_INIT_HOOK_JS) in events
        assert events.index(("add_init_script", RECAPTCHA_INIT_HOOK_JS)) < events.index(
            ("goto", "https://example.com/login", "domcontentloaded")
        )
        assert ("wait_for_timeout", 1500.0) in events
        assert holder["browser"].closed is True

    async def test_closes_browser_when_extraction_fails(
        self, monkeypatch: pytest.MonkeyPatch, patched_sdk_create, fake_client
    ) -> None:
        events: list[tuple] = []
        holder: dict = {}
        monkeypatch.setattr(
            "captchaai_mcp.server.require_async_playwright",
            lambda: _make_fake_playwright(events, browser_holder=holder),
        )
        fake_client.get_captchas_params = AsyncMock(side_effect=UnsolvableError("extract fail"))

        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            with pytest.raises(ToolError, match="UnsolvableError: extract fail"):
                await client.call_tool("get_captchas_params", {"url": "https://example.com"})

        assert holder["browser"].closed is True


class TestSolveUrl:
    @pytest.mark.parametrize("autofill", [True, False])
    async def test_forwards_autofill_and_options(
        self,
        monkeypatch: pytest.MonkeyPatch,
        patched_sdk_create,
        fake_client,
        autofill: bool,
    ) -> None:
        monkeypatch.setattr("captchaai_mcp.server.require_async_playwright", lambda: object())
        server = create_server(api_key="k" * 32)

        async with Client(server) as client:
            result = await client.call_tool(
                "solve_url",
                {
                    "url": "https://example.com/form",
                    "headless": True,
                    "wait_timeout": 2000.0,
                    "close_delay": 1.5,
                    "autofill": autofill,
                    "throw_on_error": True,
                    "default_v3_action": "checkout",
                    "proxy": "u:p@1.2.3.4:8080",
                    "proxytype": "HTTPS",
                },
            )

        assert fake_client.calls == [
            (
                "solve_url",
                {
                    "url": "https://example.com/form",
                    "headless": True,
                    "wait_timeout": 2000.0,
                    "close_delay": 1.5,
                    "autofill": autofill,
                    "throw_on_error": True,
                    "default_v3_action": "checkout",
                    "proxy": "u:p@1.2.3.4:8080",
                    "proxytype": "HTTPS",
                },
            )
        ]
        assert result.data["url"] == "https://example.com/form"
        assert result.data["count"] == 1
        assert result.data["solved_count"] == 1
        assert result.data["results"][0]["injected"] is autofill
        assert result.data["results"][0]["result"] == {
            "task_id": "77777",
            "solution": "solved-token",
            "user_agent": None,
        }

    async def test_serializes_partial_errors_without_leaking_raw_fields(
        self, monkeypatch: pytest.MonkeyPatch, patched_sdk_create, fake_client
    ) -> None:
        monkeypatch.setattr("captchaai_mcp.server.require_async_playwright", lambda: object())
        fake_client.solve_url = AsyncMock(
            return_value=[
                PageSolveResult(
                    params=CaptchaParams(captcha_type="turnstile", pageurl="https://example.com"),
                    result=SolveResult(
                        task_id="1",
                        solution="tok",
                        user_agent="UA",
                        raw={"secret": "internal"},
                        raw_text="raw",
                    ),
                    injected=True,
                ),
                PageSolveResult(
                    params=CaptchaParams(captcha_type="recaptcha_v3", pageurl="https://example.com"),
                    result=None,
                    injected=False,
                    error="UnsolvableError: failed",
                ),
            ]
        )

        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            result = await client.call_tool("solve_url", {"url": "https://example.com"})

        assert result.data["count"] == 2
        assert result.data["solved_count"] == 1
        assert set(result.data["results"][0]["result"]) == {"task_id", "solution", "user_agent"}
        assert result.data["results"][1]["result"] is None
        assert result.data["results"][1]["error"] == "UnsolvableError: failed"


class TestValidationAndBrowserErrors:
    @pytest.mark.parametrize("tool_name", ["get_captchas_params", "solve_url"])
    async def test_missing_playwright_returns_install_hint(
        self, monkeypatch: pytest.MonkeyPatch, patched_sdk_create, tool_name: str
    ) -> None:
        def _missing():
            raise ImportError("No module named 'playwright'")

        monkeypatch.setattr("captchaai_mcp.server.require_async_playwright", _missing)
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            with pytest.raises(ToolError, match=r'pip install "captchaai-mcp\[browser\]"'):
                await client.call_tool(tool_name, {"url": "https://example.com"})

        assert patched_sdk_create == []

    @pytest.mark.parametrize("tool_name", ["get_captchas_params", "solve_url"])
    @pytest.mark.parametrize(
        "bad_url",
        ["file:///etc/passwd", "javascript:alert(1)", "ftp://example.com", "   ", "https://"],
    )
    async def test_rejects_non_http_urls_before_sdk_or_browser(
        self, patched_sdk_create, tool_name: str, bad_url: str
    ) -> None:
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            with pytest.raises(ToolError, match="http:// or https://"):
                await client.call_tool(tool_name, {"url": bad_url})

        assert patched_sdk_create == []

    @pytest.mark.parametrize("tool_name", ["get_captchas_params", "solve_url"])
    async def test_rejects_mismatched_proxy_and_bad_timeout(
        self, patched_sdk_create, tool_name: str
    ) -> None:
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            with pytest.raises(ToolError, match="proxytype is required"):
                await client.call_tool(
                    tool_name,
                    {"url": "https://example.com", "proxy": "u:p@1.2.3.4:8080"},
                )
            with pytest.raises(ToolError, match="wait_timeout must be between"):
                await client.call_tool(
                    tool_name,
                    {"url": "https://example.com", "wait_timeout": 90_000.0},
                )

        assert patched_sdk_create == []

    async def test_rejects_out_of_range_close_delay(self, patched_sdk_create) -> None:
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            with pytest.raises(ToolError, match="close_delay must be between"):
                await client.call_tool(
                    "solve_url", {"url": "https://example.com", "close_delay": 60.0}
                )

        assert patched_sdk_create == []

    async def test_maps_playwright_missing_chromium_and_timeout(
        self, monkeypatch: pytest.MonkeyPatch, patched_sdk_create, fake_client
    ) -> None:
        monkeypatch.setattr("captchaai_mcp.server.require_async_playwright", lambda: object())
        FakePlaywrightError = type(
            "Error", (Exception,), {"__module__": "playwright._impl._errors"}
        )
        FakeTimeoutError = type(
            "TimeoutError", (Exception,), {"__module__": "playwright._impl._errors"}
        )

        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            fake_client.solve_url = AsyncMock(
                side_effect=FakePlaywrightError("Executable doesn't exist at /tmp/chrome")
            )
            with pytest.raises(ToolError, match="playwright install chromium"):
                await client.call_tool("solve_url", {"url": "https://example.com"})

            fake_client.solve_url = AsyncMock(
                side_effect=FakeTimeoutError("Page.goto: Timeout 30000ms exceeded.")
            )
            with pytest.raises(ToolError, match="Browser operation timed out"):
                await client.call_tool("solve_url", {"url": "https://example.com"})
