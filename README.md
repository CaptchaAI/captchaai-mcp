# CaptchaAI MCP Server

Official Model Context Protocol (MCP) server for [CaptchaAI](https://captchaai.com/), built with [FastMCP](https://gofastmcp.com/) and backed by the official [`captchaai`](https://github.com/CaptchaAI/captchaai-python) Python SDK.

Exposes **token-mode** (pure API, no browser required) tools so AI assistants and automation agents can inspect account capacity, check supported CAPTCHA types, and solve challenges.

- **Website:** https://captchaai.com/
- **API Documentation:** https://docs.captchaai.com/
- **Repository:** https://github.com/CaptchaAI/captchaai-mcp

## Tools

| Tool | Description | API Key Needed |
|---|---|---|
| `get_supported_captchas` | List the 8 token-mode CAPTCHA types with required/optional arguments and proxy/UA notes | No |
| `get_threads` | Get account thread usage (`threads`, `working_threads`, `free_threads`) | Yes |
| `get_balance` | Get account balance string (`balance`) | Yes |
| `solve_captcha` | Solve a CAPTCHA in token mode and return `task_id`, `solution`, and `user_agent` | Yes |

## Supported `captcha_type` Values

- `recaptcha_v2` (supports `invisible=True` and `enterprise=True`)
- `recaptcha_v3` (requires `action`; supports `enterprise=True` and `min_score`)
- `turnstile`
- `cloudflare_challenge` (requires `proxy` + `proxytype` (`"HTTP"` or `"HTTPS"`); returns `user_agent`)
- `geetest` (requires `gt` + `challenge`; returns `{challenge, validate, seccode}`)
- `captchafox` (requires `proxy` + `proxytype` (`"HTTP"` or `"HTTPS"`); returns `user_agent`)
- `friendly_captcha`
- `lemin` (requires `captcha_id` + `div_id`; returns `{answer, challenge_uuid}`)

## Installation

Install directly from PyPI with `pip` or run via `uvx`:

```bash
pip install captchaai-mcp
```

Or run from a local clone:

```bash
git clone https://github.com/CaptchaAI/captchaai-mcp.git
cd captchaai-mcp
uv sync
```

Set your API key:

```bash
export CAPTCHAAI_API_KEY="YOUR_32_CHAR_API_KEY"
```

## Running

```bash
# STDIO (default — for Claude Desktop, Cursor, Windsurf, etc.)
uvx captchaai-mcp
# or from source:
uv run captchaai-mcp

# Streamable HTTP (serves at http://127.0.0.1:8000/mcp)
uvx captchaai-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

> [!NOTE]
> Prefer `CAPTCHAAI_API_KEY` in the environment over `--api-key` on multi-user hosts so the key is not visible in process listings. When using `--transport streamable-http`, bind to loopback or place it behind an authenticating TLS reverse proxy.

### MCP Client Configuration (Claude Desktop / Cursor / Antigravity)

Using `uvx` (recommended):

```json
{
  "mcpServers": {
    "captchaai": {
      "command": "uvx",
      "args": ["captchaai-mcp"],
      "env": {
        "CAPTCHAAI_API_KEY": "YOUR_32_CHAR_API_KEY"
      }
    }
  }
}
```

Or from a local checkout:

```json
{
  "mcpServers": {
    "captchaai": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/captchaai-mcp",
        "captchaai-mcp"
      ],
      "env": {
        "CAPTCHAAI_API_KEY": "YOUR_32_CHAR_API_KEY"
      }
    }
  }
}
```

## Development & Tests

```bash
# Run MCP server tests
uv run pytest -q

# Inspect the MCP server manifest
uv run fastmcp inspect src/captchaai_mcp/server.py:create_server
```

## License

MIT — see [LICENSE](LICENSE).
