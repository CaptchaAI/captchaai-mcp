"""Tests for CAPTCHA catalog metadata and argument validation/dispatch."""

from __future__ import annotations

import pytest
from captchaai import supported_types
from fastmcp.exceptions import ToolError

from captchaai_mcp.catalog import CATALOG, build_call, describe_captchas


def test_catalog_covers_all_eight_token_types() -> None:
    expected = {
        "recaptcha_v2",
        "recaptcha_v3",
        "turnstile",
        "cloudflare_challenge",
        "geetest",
        "captchafox",
        "friendly_captcha",
        "lemin",
    }
    assert set(CATALOG.keys()) == expected
    sdk_names = set(supported_types().keys())
    for spec in CATALOG.values():
        assert all(name in sdk_names for name in spec.registry_names)


def test_describe_captchas_combines_mcp_and_sdk_metadata() -> None:
    info = describe_captchas()
    assert set(info.keys()) == set(CATALOG.keys())

    assert info["cloudflare_challenge"]["requires_proxy"] is True
    assert info["cloudflare_challenge"]["returns_user_agent"] is True
    assert info["captchafox"]["requires_proxy"] is True
    assert info["captchafox"]["returns_user_agent"] is True
    assert info["turnstile"]["requires_proxy"] is False
    assert info["turnstile"]["returns_user_agent"] is False
    # Enterprise variants mean recaptcha_v2 / recaptcha_v3 can return user_agent.
    assert info["recaptcha_v2"]["returns_user_agent"] is True
    assert info["recaptcha_v3"]["returns_user_agent"] is True
    assert info["turnstile"]["supported_proxy_types"] == ["HTTP", "HTTPS"]


def test_build_call_unknown_type_raises_tool_error() -> None:
    with pytest.raises(ToolError, match="Unknown captcha_type"):
        build_call("unknown_type", {"website_url": "https://example.com"})


def test_build_call_missing_required_args_raises_tool_error() -> None:
    with pytest.raises(ToolError, match="website_key, action"):
        build_call("recaptcha_v3", {"website_url": "https://example.com", "website_key": "  "})


def test_build_call_inapplicable_arg_raises_tool_error() -> None:
    with pytest.raises(ToolError, match="Arguments not supported for 'turnstile': gt"):
        build_call(
            "turnstile",
            {"website_url": "https://example.com", "website_key": "0xkey", "gt": "bad"},
        )


def test_build_call_rejects_true_flag_on_unsupported_type() -> None:
    with pytest.raises(ToolError, match="invisible"):
        build_call(
            "turnstile",
            {"website_url": "https://example.com", "website_key": "0xkey", "invisible": True},
        )


def test_build_call_ignores_default_false_flags_on_other_types() -> None:
    method, kwargs = build_call(
        "turnstile",
        {
            "website_url": "https://example.com",
            "website_key": "0xkey",
            "invisible": False,
            "enterprise": False,
        },
    )
    assert method == "turnstile"
    assert kwargs == {"url": "https://example.com", "sitekey": "0xkey"}


@pytest.mark.parametrize(
    ("args", "match"),
    [
        (
            {"website_url": "https://example.com", "website_key": "k", "proxy": "1.2.3.4:80"},
            "proxytype is required",
        ),
        (
            {"website_url": "https://example.com", "website_key": "k", "proxytype": "HTTP"},
            "proxy is required",
        ),
    ],
)
def test_build_call_rejects_mismatched_proxy_and_proxytype(args: dict, match: str) -> None:
    with pytest.raises(ToolError, match=match):
        build_call("turnstile", args)


@pytest.mark.parametrize("bad_proxytype", ["SOCKS4", "SOCKS5", "FTP"])
def test_build_call_rejects_unsupported_proxytype(bad_proxytype: str) -> None:
    with pytest.raises(ToolError, match="Unsupported proxytype"):
        build_call(
            "turnstile",
            {
                "website_url": "https://example.com",
                "website_key": "k",
                "proxy": "u:p@1.2.3.4:8080",
                "proxytype": bad_proxytype,
            },
        )
