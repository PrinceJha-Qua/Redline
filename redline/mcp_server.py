"""Redline as MCP tools, so a coding or drafting agent can check citations before it writes them.

    redline mcp                  # stdio, for Claude Code and other local agents
    redline serve                # also served over HTTP at /mcp
"""
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from . import service

# MCP over HTTP only answers requests addressed to these hosts (protection against DNS rebinding).
# A deployment adds its own name: REDLINE_ALLOWED_HOSTS="redline.example.org,redline.example.org:*"
_HOSTS = ["127.0.0.1", "127.0.0.1:*", "localhost", "localhost:*", "[::1]:*"] + \
         [h.strip() for h in os.getenv("REDLINE_ALLOWED_HOSTS", "").split(",") if h.strip()]

mcp = FastMCP("redline", stateless_http=True, json_response=True,
              transport_security=TransportSecuritySettings(allowed_hosts=_HOSTS),
              instructions="Check US case citations against a citation graph of every Supreme Court case "
                           "(1754-2014) and every F.3d appeals case (1990-2019). Call check_citations on any "
                           "text before relying on its citations. FABRICATED means the citation cannot exist; "
                           "UNVERIFIABLE means it is outside coverage, not that it is fake.")
mcp.settings.streamable_http_path = "/"


@mcp.tool()
def check_citations(text: str) -> dict:
    """Check every case citation in `text`. Returns a verdict per citation (VERIFIED, FABRICATED,
    UNVERIFIABLE), its status (good law, caution, overruled), the reason, and what it stands on."""
    result = service.check_text(text)
    for c in result["citations"]:
        c.pop("evidence", None)
    return result


@mcp.tool()
def get_case(case_id: str) -> dict:
    """One case by id (such as US:467:837 or F3d:925:1291): status, what overruled it, what it cites
    and what cites it."""
    return service.get_case(case_id) or {"error": f"No case with id {case_id}."}


@mcp.tool()
def search_cases(query: str, limit: int = 10) -> list:
    """Find cases by name, such as "Chevron" or "Loper Bright"."""
    return service.search(query, limit)


@mcp.tool()
def coverage() -> dict:
    """What Redline holds: reporters, volumes, years, counts and sources."""
    return service.get_coverage()
