"""End-to-end in-memory MCP tool, validation, error, and lifecycle tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from captchaai import InvalidKeyError, UnsolvableError
from fastmcp import Client
from fastmcp.exceptions import ToolError

from captchaai_mcp.server import create_server


class TestRegistrationAndSchema:
    async def test_server_exposes_six_tools_with_descriptions(self) -> None:
        server = create_server(api_key="test-key")
        async with Client(server) as client:
            tools = await client.list_tools()

        names = {tool.name for tool in tools}
        assert names == {
            "get_threads",
            "get_balance",
            "solve_captcha",
            "get_supported_captchas",
            "get_captchas_params",
            "solve_url",
        }
        for tool in tools:
            assert tool.description, f"Tool {tool.name} is missing a description"

        solve_tool = next(t for t in tools if t.name == "solve_captcha")
        captcha_enum = solve_tool.input_schema["properties"]["captcha_type"]["enum"]
        assert set(captcha_enum) == {
            "recaptcha_v2",
            "recaptcha_v3",
            "turnstile",
            "cloudflare_challenge",
            "geetest",
            "captchafox",
            "friendly_captcha",
            "lemin",
        }
        proxytype_schema = solve_tool.input_schema["properties"]["proxytype"]
        proxytype_enum = next(
            branch["enum"] for branch in proxytype_schema["anyOf"] if "enum" in branch
        )
        assert proxytype_enum == ["HTTP", "HTTPS"]

        solve_url_tool = next(t for t in tools if t.name == "solve_url")
        assert solve_url_tool.input_schema["properties"]["autofill"]["type"] == "boolean"
        assert solve_url_tool.input_schema["properties"]["autofill"]["default"] is True


class TestAccountAndDiscoveryTools:
    async def test_get_supported_captchas_works_without_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CAPTCHAAI_API_KEY", raising=False)
        server = create_server(api_key=None)

        async with Client(server) as client:
            result = await client.call_tool("get_supported_captchas", {})

        captchas = result.data["captchas"]
        assert len(captchas) == 8
        assert captchas["recaptcha_v3"]["required_args"] == [
            "website_url",
            "website_key",
            "action",
        ]
        assert captchas["cloudflare_challenge"]["requires_proxy"] is True

    async def test_get_threads_returns_counts_and_free_threads(
        self, patched_sdk_create
    ) -> None:
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            result = await client.call_tool("get_threads", {})

        assert result.data == {"threads": 10, "working_threads": 2, "free_threads": 8}

    @pytest.mark.parametrize("raw_balance", ["12.34", "unlimited"])
    async def test_get_balance_returns_raw_string(
        self, patched_sdk_create, fake_client, raw_balance: str
    ) -> None:
        fake_client.balance = raw_balance
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            result = await client.call_tool("get_balance", {})

        assert result.data == {"balance": raw_balance}


class TestSolveCaptchaDispatch:
    @pytest.mark.parametrize(
        ("args", "expected_method", "expected_kwargs", "expected_solution", "expected_ua"),
        [
            (
                {
                    "captcha_type": "recaptcha_v2",
                    "website_url": "https://example.com",
                    "website_key": "site-v2",
                    "invisible": True,
                    "enterprise": True,
                    "action": "verify",
                },
                "recaptcha_v2",
                {
                    "url": "https://example.com",
                    "sitekey": "site-v2",
                    "invisible": True,
                    "enterprise": True,
                    "action": "verify",
                },
                "token-for-recaptcha_v2",
                "Mozilla/5.0 Solver",
            ),
            (
                {
                    "captcha_type": "recaptcha_v3",
                    "website_url": "https://example.com",
                    "website_key": "site-v3",
                    "action": "login",
                    "min_score": 0.7,
                },
                "recaptcha_v3",
                {
                    "url": "https://example.com",
                    "sitekey": "site-v3",
                    "action": "login",
                    "min_score": 0.7,
                },
                "token-for-recaptcha_v3",
                None,
            ),
            (
                {
                    "captcha_type": "turnstile",
                    "website_url": "https://example.com",
                    "website_key": "0xturn",
                },
                "turnstile",
                {"url": "https://example.com", "sitekey": "0xturn"},
                "token-for-turnstile",
                None,
            ),
            (
                {
                    "captcha_type": "cloudflare_challenge",
                    "website_url": "https://example.com",
                    "proxy": "u:p@1.2.3.4:8080",
                    "proxytype": "HTTP",
                },
                "cloudflare_challenge",
                {
                    "url": "https://example.com",
                    "proxy": "u:p@1.2.3.4:8080",
                    "proxytype": "HTTP",
                },
                "token-for-cloudflare_challenge",
                "Mozilla/5.0 Solver",
            ),
            (
                {
                    "captcha_type": "geetest",
                    "website_url": "https://example.com",
                    "gt": "gt-1",
                    "challenge": "ch-1",
                },
                "geetest",
                {"url": "https://example.com", "gt": "gt-1", "challenge": "ch-1"},
                {"challenge": "c", "validate": "v", "seccode": "s"},
                None,
            ),
            (
                {
                    "captcha_type": "captchafox",
                    "website_url": "https://example.com",
                    "website_key": "cf-key",
                    "proxy": "u:p@1.2.3.4:8080",
                    "proxytype": "HTTPS",
                },
                "captchafox",
                {
                    "url": "https://example.com",
                    "sitekey": "cf-key",
                    "proxy": "u:p@1.2.3.4:8080",
                    "proxytype": "HTTPS",
                },
                "token-for-captchafox",
                "Mozilla/5.0 Solver",
            ),
            (
                {
                    "captcha_type": "friendly_captcha",
                    "website_url": "https://example.com",
                    "website_key": "fc-key",
                    "version": "2",
                },
                "friendly_captcha",
                {"url": "https://example.com", "sitekey": "fc-key", "version": "2"},
                "token-for-friendly_captcha",
                None,
            ),
            (
                {
                    "captcha_type": "lemin",
                    "website_url": "https://example.com",
                    "captcha_id": "cid",
                    "div_id": "lemin-box",
                    "api_server": "https://api.lemin.example",
                },
                "lemin",
                {
                    "url": "https://example.com",
                    "captcha_id": "cid",
                    "div_id": "lemin-box",
                    "api_server": "https://api.lemin.example",
                },
                {"answer": "a", "challenge_uuid": "u"},
                None,
            ),
        ],
    )
    async def test_solve_captcha_dispatches_all_types(
        self,
        patched_sdk_create,
        fake_client,
        args: dict,
        expected_method: str,
        expected_kwargs: dict,
        expected_solution,
        expected_ua: str | None,
    ) -> None:
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            result = await client.call_tool("solve_captcha", args)

        assert result.data == {
            "captcha_type": args["captcha_type"],
            "task_id": "99999",
            "solution": expected_solution,
            "user_agent": expected_ua,
        }
        assert fake_client.calls == [(expected_method, expected_kwargs)]

    async def test_validation_error_runs_before_sdk_create(
        self, patched_sdk_create, fake_client
    ) -> None:
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            with pytest.raises(ToolError, match="Missing required arguments"):
                await client.call_tool(
                    "solve_captcha",
                    {"captcha_type": "geetest", "website_url": "https://example.com"},
                )

        assert patched_sdk_create == []
        assert fake_client.calls == []


class TestLifecycleAndErrors:
    async def test_missing_api_key_raises_clear_tool_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CAPTCHAAI_API_KEY", raising=False)
        server = create_server(api_key=None)
        async with Client(server) as client:
            with pytest.raises(ToolError, match="CAPTCHAAI_API_KEY is not set"):
                await client.call_tool("get_balance", {})

    async def test_client_is_lazy_cached_and_closed_on_shutdown(
        self, patched_sdk_create, fake_client
    ) -> None:
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            # No client created on server startup or get_supported_captchas.
            await client.call_tool("get_supported_captchas", {})
            assert patched_sdk_create == []

            # Concurrent initial calls create only one client.
            await asyncio.gather(
                client.call_tool("get_threads", {}),
                client.call_tool("get_balance", {}),
                client.call_tool("get_threads", {}),
            )
            assert len(patched_sdk_create) == 1
            assert fake_client.closed is False

        assert fake_client.closed is True

    async def test_failed_create_is_not_cached(
        self, monkeypatch: pytest.MonkeyPatch, fake_client
    ) -> None:
        attempts = {"count": 0}

        async def flaky_create(**kwargs):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise InvalidKeyError("Key not found")
            return fake_client

        monkeypatch.setattr("captchaai_mcp.server.AsyncCaptchaAI.create", flaky_create)
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            with pytest.raises(ToolError, match="InvalidKeyError"):
                await client.call_tool("get_balance", {})

            result = await client.call_tool("get_balance", {})
            assert result.data == {"balance": "12.34"}
            assert attempts["count"] == 2

    async def test_sdk_error_during_tool_call_becomes_tool_error(
        self, patched_sdk_create, fake_client
    ) -> None:
        fake_client.turnstile = AsyncMock(side_effect=UnsolvableError("not solvable"))
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            with pytest.raises(ToolError, match="UnsolvableError: not solvable"):
                await client.call_tool(
                    "solve_captcha",
                    {
                        "captcha_type": "turnstile",
                        "website_url": "https://example.com",
                        "website_key": "0xkey",
                    },
                )

    async def test_unexpected_exception_details_are_masked(
        self, patched_sdk_create, fake_client
    ) -> None:
        fake_client.get_balance = AsyncMock(side_effect=RuntimeError("internal secret path"))
        server = create_server(api_key="k" * 32)
        async with Client(server) as client:
            with pytest.raises(ToolError) as exc_info:
                await client.call_tool("get_balance", {})

        assert "internal secret path" not in str(exc_info.value)
