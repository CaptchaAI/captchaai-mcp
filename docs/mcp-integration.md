# MCP Client Integration Guide

This guide explains how to connect the **CaptchaAI MCP Server** (`captchaai-mcp`) to AI coding assistants and development tools using the Model Context Protocol (MCP).

`captchaai-mcp` exposes four tools to your AI assistant:

- `get_supported_captchas` — inspect supported challenge types and required arguments (no API key needed)
- `get_threads` — check account thread limits and free concurrency
- `get_balance` — check account balance
- `solve_captcha` — solve token-mode challenges (`recaptcha_v2`, `recaptcha_v3`, `turnstile`, `cloudflare_challenge`, `geetest`, `captchafox`, `friendly_captcha`, `lemin`)

## Prerequisites

1. Obtain a CaptchaAI API key from [captchaai.com](https://captchaai.com/).
2. Have either [`uv`](https://docs.astral.sh/uv/) (`uvx` recommended for zero-install execution) or Python `>=3.10` with `pip install captchaai-mcp` available.

> [!NOTE]
> Always pass your API key via the `CAPTCHAAI_API_KEY` environment variable rather than `--api-key` on multi-user machines so the key does not appear in OS process listings (`ps`).

---

## Claude Code

You can register `captchaai-mcp` with the `claude` CLI or via a project `.mcp.json` file.

### Option A: CLI (`stdio` — Recommended)

```bash
claude mcp add --transport stdio captchaai \
  --env CAPTCHAAI_API_KEY=YOUR_32_CHAR_API_KEY \
  -- uvx captchaai-mcp
```

Add `--scope user` if you want it available across all projects:

```bash
claude mcp add --scope user --transport stdio captchaai \
  --env CAPTCHAAI_API_KEY=YOUR_32_CHAR_API_KEY \
  -- uvx captchaai-mcp
```

If you installed via `pip install captchaai-mcp` instead of `uv`:

```bash
claude mcp add --transport stdio captchaai \
  --env CAPTCHAAI_API_KEY=YOUR_32_CHAR_API_KEY \
  -- captchaai-mcp
```

### Option B: Project `.mcp.json` (Shared Config Without Hardcoding Secrets)

Create `.mcp.json` at the root of your repository and keep `CAPTCHAAI_API_KEY` in your shell environment:

```json
{
  "mcpServers": {
    "captchaai": {
      "command": "uvx",
      "args": ["captchaai-mcp"],
      "env": {
        "CAPTCHAAI_API_KEY": "${CAPTCHAAI_API_KEY}"
      }
    }
  }
}
```

### Option C: Local HTTP Transport

Start the server locally, then attach Claude Code over HTTP:

```bash
export CAPTCHAAI_API_KEY="YOUR_32_CHAR_API_KEY"
uvx captchaai-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

```bash
claude mcp add --transport http captchaai http://127.0.0.1:8000/mcp
```

### Verify in Claude Code

```bash
claude mcp list
```

Inside an interactive Claude Code session, run `/mcp` to confirm `captchaai` is connected and inspect its tools.

---

## OpenAI Codex (CLI & IDE Extension)

Codex shares MCP settings between the CLI and IDE extension via `~/.codex/config.toml` (global) or `.codex/config.toml` (project-scoped in trusted repositories).

### Option A: CLI (`codex mcp add`)

```bash
codex mcp add captchaai \
  --env CAPTCHAAI_API_KEY=YOUR_32_CHAR_API_KEY \
  -- uvx captchaai-mcp
```

Or if installed with `pip install captchaai-mcp`:

```bash
codex mcp add captchaai \
  --env CAPTCHAAI_API_KEY=YOUR_32_CHAR_API_KEY \
  -- captchaai-mcp
```

### Option B: Manual Configuration in `~/.codex/config.toml`

Add the following to `~/.codex/config.toml` (or `.codex/config.toml`):

```toml
[mcp_servers.captchaai]
command = "uvx"
args = ["captchaai-mcp"]
# Optional: solve_captcha typically blocks 10–80s while workers solve a challenge;
# increase tool_timeout_sec above Codex's 60s default to avoid premature timeouts.
tool_timeout_sec = 180

[mcp_servers.captchaai.env]
CAPTCHAAI_API_KEY = "YOUR_32_CHAR_API_KEY"
```

### Option C: Streamable HTTP in Codex

```bash
codex mcp add captchaai --url http://127.0.0.1:8000/mcp
```

Or in `~/.codex/config.toml`:

```toml
[mcp_servers.captchaai]
url = "http://127.0.0.1:8000/mcp"
tool_timeout_sec = 180
```

### Verify in Codex

```bash
codex mcp list
```

Inside a Codex session, run `/mcp` to verify `captchaai` is active.

---

## Other AI Editors & MCP Clients

### Cursor

Add to `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (project):

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

### Claude Desktop

Add to your `claude_desktop_config.json`:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux:** `~/.config/Claude/claude_desktop_config.json`

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

### VS Code / GitHub Copilot

Add to `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "captchaai": {
      "type": "stdio",
      "command": "uvx",
      "args": ["captchaai-mcp"],
      "env": {
        "CAPTCHAAI_API_KEY": "${input:captchaai-api-key}"
      }
    }
  },
  "inputs": [
    {
      "id": "captchaai-api-key",
      "type": "promptString",
      "description": "CaptchaAI API Key",
      "password": true
    }
  ]
}
```

### Windsurf

Add to `~/.codeium/windsurf/mcp_config.json`:

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

### Antigravity

Add to `~/.gemini/config/mcp_config.json` (or manage via MCP Servers UI):

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

---

## Running From a Local Source Checkout

If you are developing locally or modifying `captchaai-mcp`, replace `uvx captchaai-mcp` with:

```json
{
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
```

Or with CLI tools (`claude mcp add` / `codex mcp add`):

```bash
claude mcp add --transport stdio captchaai \
  --env CAPTCHAAI_API_KEY=YOUR_32_CHAR_API_KEY \
  -- uv run --directory /path/to/captchaai-mcp captchaai-mcp
```

---

## Streamable HTTP Deployment Notes

When running `captchaai-mcp --transport streamable-http`:

- The server defaults to `--host 127.0.0.1` and `--port 8000` (endpoint `/mcp`) without built-in authentication middleware.
- Keep it bound to `127.0.0.1` for local use, or place it behind an authenticating TLS reverse proxy when exposing it to other hosts.

---

## Quick Verification After Connecting

Once connected in your AI tool, try asking:

1. `"List supported CaptchaAI challenge types."` (invokes `get_supported_captchas` without spending credits)
2. `"Check my CaptchaAI thread capacity and balance."` (invokes `get_threads` and `get_balance`)
