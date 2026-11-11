"""CLI entry point for `python -m captchaai_mcp` and the `captchaai-mcp` script."""

from __future__ import annotations

import argparse

from captchaai_mcp.server import create_server


def main() -> None:
    """Parse CLI arguments and run the CaptchaAI MCP server."""
    parser = argparse.ArgumentParser(
        description="CaptchaAI MCP Server — expose token-mode captcha solving to AI agents.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="stdio",
        help="Transport protocol: stdio (default) or streamable-http.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind for streamable-http transport (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind for streamable-http transport (default: 8000).",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="CaptchaAI API key. Falls back to CAPTCHAAI_API_KEY env var.",
    )
    parser.add_argument(
        "--name",
        default="captchaai",
        help="Server name advertised to MCP clients (default: captchaai).",
    )

    args = parser.parse_args()
    server = create_server(api_key=args.api_key, name=args.name)

    if args.transport == "stdio":
        server.run()
    else:
        server.run(transport="http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
