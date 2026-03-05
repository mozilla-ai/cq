"""CRAIC MCP server entry point."""

from fastmcp import FastMCP

mcp = FastMCP("craic")


def main() -> None:
    """Start the CRAIC MCP server."""
    mcp.run()
