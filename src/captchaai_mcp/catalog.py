"""Catalog of supported token-mode CAPTCHA types and SDK call dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from captchaai import SUPPORTED_PROXY_TYPES, supported_types
from fastmcp.exceptions import ToolError

_COMMON_ARGS = ("cookies", "user_agent", "proxy", "proxytype")
_PROXY_ONLY_ARGS = ("proxy", "proxytype")
_ARG_TO_SDK_KWARG = {
    "website_url": "url",
    "website_key": "sitekey",
}


@dataclass(frozen=True)
class PublicType:
    """Definition of one public token-mode CAPTCHA type exposed by MCP."""

    sdk_method: str
    description: str
    registry_names: tuple[str, ...]
    required: tuple[str, ...]
    optional: tuple[str, ...]
    variants: dict[str, str]


CATALOG: dict[str, PublicType] = {
    "recaptcha_v2": PublicType(
        sdk_method="recaptcha_v2",
        description="Google reCAPTCHA v2 checkbox, invisible, or Enterprise.",
        registry_names=("recaptcha_v2", "recaptcha_v2_invisible", "recaptcha_v2_enterprise"),
        required=("website_url", "website_key"),
        optional=("invisible", "enterprise", "action", *_COMMON_ARGS),
        variants={
            "invisible": "Invisible reCAPTCHA v2 widget",
            "enterprise": "reCAPTCHA v2 Enterprise (returns user_agent to reuse)",
        },
    ),
    "recaptcha_v3": PublicType(
        sdk_method="recaptcha_v3",
        description="Google reCAPTCHA v3 score-based challenge (standard or Enterprise).",
        registry_names=("recaptcha_v3", "recaptcha_v3_enterprise"),
        required=("website_url", "website_key", "action"),
        optional=("enterprise", "min_score", *_COMMON_ARGS),
        variants={
            "enterprise": "reCAPTCHA v3 Enterprise (returns user_agent to reuse)",
        },
    ),
    "turnstile": PublicType(
        sdk_method="turnstile",
        description="Cloudflare Turnstile widget.",
        registry_names=("turnstile",),
        required=("website_url", "website_key"),
        optional=_COMMON_ARGS,
        variants={},
    ),
    "cloudflare_challenge": PublicType(
        sdk_method="cloudflare_challenge",
        description="Cloudflare interstitial challenge page (returns cf_clearance + user_agent).",
        registry_names=("cloudflare_challenge",),
        required=("website_url", "proxy", "proxytype"),
        optional=("cookies", "user_agent"),
        variants={},
    ),
    "geetest": PublicType(
        sdk_method="geetest",
        description="GeeTest v3 slide/puzzle challenge (returns dict with challenge/validate/seccode).",
        registry_names=("geetest",),
        required=("website_url", "gt", "challenge"),
        optional=_COMMON_ARGS,
        variants={},
    ),
    "captchafox": PublicType(
        sdk_method="captchafox",
        description="CaptchaFox slider challenge (proxy required; returns user_agent to reuse).",
        registry_names=("captchafox",),
        required=("website_url", "website_key", "proxy", "proxytype"),
        optional=("cookies", "user_agent"),
        variants={},
    ),
    "friendly_captcha": PublicType(
        sdk_method="friendly_captcha",
        description="Friendly Captcha proof-of-work challenge.",
        registry_names=("friendly_captcha",),
        required=("website_url", "website_key"),
        optional=("version", *_PROXY_ONLY_ARGS),
        variants={},
    ),
    "lemin": PublicType(
        sdk_method="lemin",
        description="Lemin puzzle challenge (returns dict with answer and challenge_uuid).",
        registry_names=("lemin",),
        required=("website_url", "captcha_id", "div_id"),
        optional=("api_server", *_PROXY_ONLY_ARGS),
        variants={},
    ),
}


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def validate_proxy_pair(
    proxy: str | None,
    proxytype: str | None,
) -> tuple[str | None, str | None]:
    """Validate optional proxy/proxytype pair and return normalized `(proxy, proxytype)`."""
    has_proxy = not _is_missing(proxy)
    has_proxytype = not _is_missing(proxytype)
    if has_proxy and not has_proxytype:
        raise ToolError("proxytype is required when proxy is set (HTTP or HTTPS).")
    if has_proxytype and not has_proxy:
        raise ToolError("proxy is required when proxytype is set (format: 'user:pass@host:port').")
    if not has_proxy:
        return None, None

    normalized_proxytype = str(proxytype).strip().upper()
    if normalized_proxytype not in SUPPORTED_PROXY_TYPES:
        supported = ", ".join(SUPPORTED_PROXY_TYPES)
        raise ToolError(
            f"Unsupported proxytype {proxytype!r}. Supported values: {supported}."
        )
    return str(proxy).strip(), normalized_proxytype


def build_call(captcha_type: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Validate MCP arguments and build `(sdk_method_name, sdk_kwargs)`.

    Raises ToolError before any network call if `captcha_type` is unknown,
    required arguments are missing, proxy/proxytype are mismatched, or arguments
    not supported by the chosen type are supplied.
    """
    spec = CATALOG.get(captcha_type)
    if spec is None:
        supported = ", ".join(CATALOG)
        raise ToolError(f"Unknown captcha_type {captcha_type!r}. Supported: {supported}.")

    allowed = set(spec.required) | set(spec.optional)

    # Reject inapplicable arguments rather than silently dropping them, while
    # skipping default False on boolean flags (SDK defaults to False as well).
    provided: dict[str, Any] = {}
    for key, value in args.items():
        if value is None:
            continue
        if key in ("invisible", "enterprise") and value is False:
            continue
        provided[key] = value

    inapplicable = sorted(key for key in provided if key not in allowed)
    if inapplicable:
        raise ToolError(
            f"Arguments not supported for {captcha_type!r}: {', '.join(inapplicable)}. "
            "Call get_supported_captchas() to see valid parameters."
        )

    missing = [key for key in spec.required if _is_missing(provided.get(key))]
    if missing:
        raise ToolError(
            f"Missing required arguments for {captcha_type!r}: {', '.join(missing)}. "
            "Call get_supported_captchas() for parameter details."
        )

    norm_proxy, norm_proxytype = validate_proxy_pair(
        provided.get("proxy"), provided.get("proxytype")
    )
    if norm_proxy is not None:
        provided["proxy"] = norm_proxy
        provided["proxytype"] = norm_proxytype

    sdk_kwargs = {_ARG_TO_SDK_KWARG.get(key, key): value for key, value in provided.items()}
    return spec.sdk_method, sdk_kwargs


def describe_captchas() -> dict[str, dict[str, Any]]:
    """Return per-type metadata combining MCP parameters with live SDK registry facts."""
    sdk_info = supported_types()
    out: dict[str, dict[str, Any]] = {}
    for name, spec in CATALOG.items():
        entries = [sdk_info[reg] for reg in spec.registry_names if reg in sdk_info]
        out[name] = {
            "description": spec.description,
            "required_args": list(spec.required),
            "optional_args": list(spec.optional),
            "variants": dict(spec.variants),
            "requires_proxy": any(item["requires_proxy"] for item in entries),
            "returns_user_agent": any(item["returns_user_agent"] for item in entries),
            "supported_proxy_types": list(SUPPORTED_PROXY_TYPES),
        }
    return out
