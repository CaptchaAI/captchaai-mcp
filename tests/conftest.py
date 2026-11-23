"""Shared test fixtures for CaptchaAI MCP server tests."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from captchaai import CaptchaParams, PageSolveResult, SolveResult


class FakeAsyncCaptchaAI:
    """In-memory fake of AsyncCaptchaAI recording all SDK method calls."""

    def __init__(self, *, balance: str = "12.34", threads: int = 10, working: int = 2) -> None:
        self.balance = balance
        self.threads = threads
        self.working = working
        self.closed = False
        self.calls: list[tuple[str, dict]] = []

        self.threads_info = AsyncMock(side_effect=self._threads_info)
        self.get_balance = AsyncMock(side_effect=self._get_balance)
        self.get_captchas_params = AsyncMock(side_effect=self._get_captchas_params)
        self.solve_url = AsyncMock(side_effect=self._solve_url)
        self.aclose = AsyncMock(side_effect=self._aclose)

        for method in (
            "recaptcha_v2",
            "recaptcha_v3",
            "turnstile",
            "cloudflare_challenge",
            "geetest",
            "captchafox",
            "friendly_captcha",
            "lemin",
        ):
            setattr(self, method, AsyncMock(side_effect=self._make_solver(method)))

    async def _threads_info(self) -> dict[str, int]:
        self.calls.append(("threads_info", {}))
        return {"threads": self.threads, "working_threads": self.working}

    async def _get_balance(self) -> str:
        self.calls.append(("get_balance", {}))
        return self.balance

    async def _aclose(self) -> None:
        self.closed = True

    async def _get_captchas_params(self, page) -> list[CaptchaParams]:
        self.calls.append(("get_captchas_params", {"page_url": str(page.url)}))
        return [
            CaptchaParams(
                captcha_type="recaptcha_v2",
                pageurl=str(page.url),
                sitekey="site-v2-key",
                container_id="rc-box",
                callback="onCaptcha",
                user_agent="Mozilla/5.0 Fake",
            )
        ]

    async def _solve_url(self, **kwargs) -> list[PageSolveResult]:
        self.calls.append(("solve_url", dict(kwargs)))
        params = CaptchaParams(
            captcha_type="turnstile",
            pageurl=kwargs["url"],
            sitekey="0xturnstile",
        )
        return [
            PageSolveResult(
                params=params,
                result=SolveResult(task_id="77777", solution="solved-token", user_agent=None),
                injected=bool(kwargs.get("autofill", True)),
            )
        ]

    def _make_solver(self, method: str):
        async def _solve(**kwargs) -> SolveResult:
            self.calls.append((method, dict(kwargs)))
            if method == "geetest":
                solution: str | dict = {"challenge": "c", "validate": "v", "seccode": "s"}
            elif method == "lemin":
                solution = {"answer": "a", "challenge_uuid": "u"}
            else:
                solution = f"token-for-{method}"

            ua = (
                "Mozilla/5.0 Solver"
                if method in ("cloudflare_challenge", "captchafox")
                or kwargs.get("enterprise")
                else None
            )
            return SolveResult(task_id="99999", solution=solution, user_agent=ua)

        return _solve


@pytest.fixture
def fake_client() -> FakeAsyncCaptchaAI:
    """Return a fresh FakeAsyncCaptchaAI instance."""
    return FakeAsyncCaptchaAI()


@pytest.fixture
def patched_sdk_create(monkeypatch: pytest.MonkeyPatch, fake_client: FakeAsyncCaptchaAI):
    """Patch AsyncCaptchaAI.create to return `fake_client` and record create calls."""
    create_calls: list[dict] = []

    async def fake_create(**kwargs):
        await asyncio.sleep(0)
        create_calls.append(kwargs)
        return fake_client

    monkeypatch.setattr("captchaai_mcp.server.AsyncCaptchaAI.create", fake_create)
    return create_calls
