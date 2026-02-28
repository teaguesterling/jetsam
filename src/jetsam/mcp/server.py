"""MCP server for jetsam — exposes git workflow tools to agents."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from jetsam.mcp.tools import register_tools

mcp = FastMCP("jetsam", instructions=(
    "jetsam is a git workflow accelerator. "
    "Use workflow tools (status, save, sync, log, diff) for common operations. "
    "Mutating tools (save, sync) return plans that must be confirmed with confirm(). "
    "Use the git tool for any git operation not covered by workflow tools."
))

register_tools(mcp)


def serve_stdio() -> None:
    """Run the MCP server with stdio transport."""
    mcp.run(transport="stdio")


def serve_sse() -> None:
    """Run the MCP server with SSE transport."""
    mcp.run(transport="sse")
